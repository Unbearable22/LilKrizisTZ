"""Bounded SQLite FTS index; successful verification alone refreshes a record."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from .trusted_sources import validate_source_url

class SourceIndex:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS fragments(id TEXT PRIMARY KEY,url TEXT NOT NULL,payload TEXT NOT NULL,checked_at TEXT NOT NULL); CREATE VIRTUAL TABLE IF NOT EXISTS fragment_search USING fts5(id UNINDEXED,title,text,tokenize="unicode61"); PRAGMA user_version=1;')
    def connect(self):return sqlite3.connect(self.path,timeout=5)
    def upsert(self,document):
        validate_source_url(document.url)
        if document.applicability not in ('current','guidance'):return
        if sum(len(f['text']) for f in document.fragments)>200000:raise ValueError('Document too large')
        changed=False
        with self.connect() as db:
            old={row[0] for row in db.execute('SELECT id FROM fragments WHERE url=?',(document.url,))}
            new_ids=set()
            for row in db.execute('SELECT id FROM fragments WHERE url=?',(document.url,)).fetchall():db.execute('DELETE FROM fragment_search WHERE id=?',row)
            db.execute('DELETE FROM fragments WHERE url=?',(document.url,))
            for n,part in enumerate(document.fragments):
                digest=hashlib.sha256((document.revision+'|'+part['text']).encode()).hexdigest()
                fid='idx_'+hashlib.sha256(document.url.encode()).hexdigest()[:16]+':'+digest[:16]+':'+str(n)
                f={'id':fid,'document_id':fid.split(':')[0],'source_url':document.url,'title':document.title,'publisher':document.publisher,'source_kind':document.source_kind,'extraction_status':'verified_current' if document.applicability=='current' else 'verified_guidance','version':document.revision,'last_checked_at':document.checked_at,'retrieved_at':document.checked_at,'page_hash':digest,'demo':False,**part}
                new_ids.add(fid)
                db.execute('INSERT INTO fragments VALUES(?,?,?,?)',(fid,document.url,json.dumps(f,ensure_ascii=False),document.checked_at))
                db.execute('INSERT INTO fragment_search VALUES(?,?,?)',(fid,document.title,part['text']))
            changed=bool(old and old!=new_ids)
            db.execute('DELETE FROM fragment_search WHERE id IN (SELECT id FROM fragments WHERE checked_at<?)',((datetime.now(timezone.utc)-timedelta(days=30)).isoformat(),))
            db.execute('DELETE FROM fragments WHERE checked_at<?',((datetime.now(timezone.utc)-timedelta(days=30)).isoformat(),))
        if changed:
            journal=self.path.with_suffix('.changes.jsonl')
            if journal.exists() and journal.stat().st_size>1024*1024:journal.write_text('')
            with journal.open('a',encoding='utf-8') as stream:stream.write(json.dumps({'url':document.url,'checked_at':document.checked_at,'removed':sorted(old-new_ids),'added':sorted(new_ids-old)})+'\n')
        # Compact bounded cache, never silently grow indefinitely.
        if self.path.stat().st_size>200*1024*1024:
            with self.connect() as db:
                db.execute('DELETE FROM fragment_search');db.execute('DELETE FROM fragments')
            with self.connect() as db:db.execute('VACUUM')
    def read(self,fid,as_of_date):
        with self.connect() as db:row=db.execute('SELECT payload FROM fragments WHERE id=?',(fid,)).fetchone()
        if not row:return None
        f=json.loads(row[0]);checked=datetime.fromisoformat(f['last_checked_at'])
        now=datetime.now(timezone.utc)
        if checked.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()!=as_of_date or not timedelta(0)<=now-checked<=timedelta(hours=24):return None
        return f
    def search(self,query,limit=6,as_of_date=None):
        tokens=re.findall(r'[а-яёa-z0-9]{3,}',query.casefold())[:20]
        if not tokens:return []
        expression=' OR '.join('"'+token+'"*' for token in tokens)
        with self.connect() as db:rows=db.execute('SELECT id FROM fragment_search WHERE fragment_search MATCH ? ORDER BY rank LIMIT ?',(expression,min(24,max(1,limit*4)))).fetchall()
        day=as_of_date or datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
        return [f for row in rows if (f:=self.read(row[0],day))][:limit]
