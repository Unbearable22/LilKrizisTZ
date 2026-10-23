"""SQLite-backed bounded cache outside Git. Text updates invalidate old fragment IDs."""
import json,sqlite3,hashlib,re
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .consultant_types import SourceError

class ConsultantCache:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.path=self.root/'cache.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS fragments(id TEXT PRIMARY KEY,url TEXT,part INTEGER,hash TEXT,payload TEXT,used TEXT,UNIQUE(url,part))')
            db.execute('CREATE TABLE IF NOT EXISTS pages(url TEXT PRIMARY KEY,payload TEXT,used TEXT)')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:yield db
        finally:db.close()
    def log(self,url,old,new):
        path=self.root/'changes.jsonl'
        if path.exists() and path.stat().st_size>=10*1024*1024:path.replace(self.root/'changes.previous.jsonl')
        with path.open('a') as out:out.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'url':url,'old':old,'new':new})+'\n')
    def put(self,fragment):
        f=dict(fragment);digest=hashlib.sha256(f['text'].encode()).hexdigest();f['sha256']=digest
        # A page hash, when available, invalidates every chunk from its older version.
        page_hash=f.get('page_hash',digest);part=f.get('part_index',0);identity=hashlib.sha256((page_hash+'|'+digest).encode()).hexdigest();fid=f"{f['document_id']}:{identity[:16]}:{part}"
        f['id']=fid;now=datetime.now(timezone.utc).isoformat();payload=json.dumps(f,ensure_ascii=False)
        with self.connect() as db:
            old=db.execute('SELECT hash FROM fragments WHERE url=? LIMIT 1',(f['source_url'],)).fetchone()
            db.execute('DELETE FROM fragments WHERE url=? AND hash!=?',(f['source_url'],page_hash))
            db.execute('INSERT OR REPLACE INTO fragments VALUES(?,?,?,?,?,?)',(fid,f['source_url'],part,page_hash,payload,now))
        if not old or old[0]!=page_hash:self.log(f['source_url'],old[0] if old else None,page_hash)
        return fid
    def read(self,fragment_id,*,as_of_date,now):
        if as_of_date!=now.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat():raise SourceError('source_edition_unknown')
        if not isinstance(fragment_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}:[a-f0-9]{16}:\d+',fragment_id):raise SourceError('source_unknown_fragment')
        with self.connect() as db:
            row=db.execute('SELECT payload FROM fragments WHERE id=?',(fragment_id,)).fetchone()
            if not row:raise SourceError('source_unknown_fragment')
            f=json.loads(row[0]);checked=datetime.fromisoformat(f['last_checked_at'])
            if not timedelta(0)<=now-checked<=timedelta(hours=24):raise SourceError('source_stale')
            if f.get('extraction_status')!='verified_current' or f.get('effective_from') and f['effective_from']>as_of_date:raise SourceError('source_edition_unknown')
            if hashlib.sha256(f['text'].encode()).hexdigest()!=f['sha256']:raise SourceError('source_hash_changed')
            db.execute('UPDATE fragments SET used=? WHERE id=?',(now.isoformat(),fragment_id))
        return f
    def lookup(self,canonical_url):
        with self.connect() as db:row=db.execute('SELECT payload FROM pages WHERE url=?',(canonical_url,)).fetchone()
        return json.loads(row[0]) if row else None
    def put_page(self,page):
        from dataclasses import asdict
        payload=asdict(page);now=datetime.now(timezone.utc).isoformat()
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO pages VALUES(?,?,?)',(page.canonical_url,json.dumps(payload,ensure_ascii=False),now))
    def prune(self,now):
        cutoff=(now-timedelta(days=30)).isoformat()
        with self.connect() as db:
            db.execute('DELETE FROM fragments WHERE used<?',(cutoff,));db.execute('DELETE FROM pages WHERE used<?',(cutoff,))
            size=sum(row[0] or 0 for row in [db.execute('SELECT sum(length(CAST(payload AS BLOB))) FROM fragments').fetchone(),db.execute('SELECT sum(length(CAST(payload AS BLOB))) FROM pages').fetchone()])
            while size>160*1024*1024:
                for table,key in [('fragments','id'),('pages','url')]:db.execute(f'DELETE FROM {table} WHERE {key} IN (SELECT {key} FROM {table} ORDER BY used LIMIT 1)')
                size=sum(row[0] or 0 for row in [db.execute('SELECT sum(length(CAST(payload AS BLOB))) FROM fragments').fetchone(),db.execute('SELECT sum(length(CAST(payload AS BLOB))) FROM pages').fetchone()])
        if self.path.stat().st_size>170*1024*1024:
            with self.connect() as db:db.execute('VACUUM')
