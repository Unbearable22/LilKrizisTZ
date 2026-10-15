import difflib
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from .db import dumps, now
from .network import fetch_public

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts=[]
        self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'):
            self.skip+=1
        if tag=='a' and not self.skip:
            href=dict(attrs).get('href','')
            if href:
                self.parts.append('[ссылка: '+href+']')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'):
            self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:
            self.parts.append(data)

def extract(data, content_type, charset='utf-8'):
    if data.startswith(b'%PDF'):
        if not shutil.which('pdftotext'):
            raise ValueError('Для PDF установите poppler-utils; сканы требуют OCR и проверки специалистом.')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.pdf'
            p.write_bytes(data)
            result=subprocess.run(['pdftotext','-layout',str(p),'-'],capture_output=True,timeout=30,check=True)
            text=result.stdout.decode('utf-8')
    elif 'html' in content_type or data.lstrip().lower().startswith((b'<!doctype html',b'<html')):
        parser=TextParser()
        parser.feed(data.decode(charset,errors='replace'))
        text=' '.join(parser.parts)
    else:
        text=data.decode(charset,errors='strict')
    text=' '.join(text.split())
    if len(text)<40:
        raise ValueError('Недостаточно извлечённого текста; нужен OCR или другой источник.')
    return text

class Monitor:
    def __init__(self,db,fetcher=fetch_public):
        self.db,self.fetcher=db,fetcher

    def run(self):
        results=[]
        for source in self.db.rows('SELECT * FROM sources ORDER BY id'):
            try:
                results.append(self.check(source))
            except Exception as exc:
                # Persist a concise error, never endpoint credentials or raw request data.
                error = str(exc)[:300] if isinstance(exc,ValueError) else type(exc).__name__
                self.db.execute('UPDATE sources SET last_checked=?,error=? WHERE id=?',(now(),error,source['id']))
                results.append({'source_id':source['id'],'status':'error','error':error})
        return results

    def check(self,source):
        data,ctype,charset=self.fetcher(source['url'])
        content=extract(data,ctype,charset)
        digest=hashlib.sha256(content.encode()).hexdigest()
        old=self.db.rows('SELECT content FROM revisions WHERE source_id=? ORDER BY id DESC LIMIT 1',(source['id'],))
        artifact_dir=self.db.directory/'sources'
        artifact_dir.mkdir(exist_ok=True)
        suffix='.pdf' if data.startswith(b'%PDF') else ('.html' if 'html' in ctype else '.txt')
        artifact=artifact_dir/f'{source["id"]}-{hashlib.sha256(data).hexdigest()}{suffix}'
        artifact.write_bytes(data)
        with self.db.connect() as c:
            existing=c.execute('SELECT id FROM revisions WHERE source_id=? AND digest=?',(source['id'],digest)).fetchone()
            changed=source['digest'] is not None and source['digest']!=digest
            if not existing:
                rid=c.execute('INSERT INTO revisions(source_id,digest,previous_text,content,artifact,created_at) VALUES(?,?,?,?,?,?)',(source['id'],digest,old[0]['content'] if old else None,content,str(artifact),now())).lastrowid
            else:
                rid=existing['id']
            c.execute('UPDATE sources SET digest=?,last_checked=?,error=NULL WHERE id=?',(digest,now(),source['id']))
            if changed:
                # Changed source invalidates verified rules until a specialist imports a new revision.
                if source['kind']=='pzz':
                    if source['municipality_id']:
                        c.execute('UPDATE rules SET active=0 WHERE municipality_id=?',(source['municipality_id'],))
                    else:
                        c.execute('UPDATE rules SET active=0')
                else:
                    c.execute('UPDATE legal_documents SET active=0 WHERE kind=?',(source['kind'],))
                cases=[dict(r) for r in c.execute('SELECT * FROM cases')]
                for case in cases:
                    p=json.loads(case['data'])
                    if source['municipality_id'] and p.get('municipality_id')!=source['municipality_id']:
                        continue
                    explicit=any(v and v.casefold() in content.casefold() for v in (p.get('cadastre'),p.get('address')))
                    before=old[0]['content'] if old else ''
                    delta='\n'.join(difflib.unified_diff(before.split('. '),content.split('. '),fromfile='предыдущая редакция',tofile='новая публикация',n=1))[:3000]
                    alert={'title':'Изменение нормативного источника — требуется проверка','source_title':source['title'],'source_url':source['url'],'client':p['client'],'address':p['address'],'cadastre':p.get('cadastre'),'match':'кадастровый номер/адрес найден в публикации' if explicit else 'предварительный охват по муниципалитету/нормативному акту','notice':'Изменение текста не доказывает изменение применимой нормы. Специалист должен проверить документ и влияние на дело.','diff':delta,'artifact':str(artifact)}
                    c.execute('INSERT OR IGNORE INTO notifications(owner_id,case_id,revision_id,data) VALUES(?,?,?,?)',(case['owner_id'],case['id'],rid,dumps(alert)))
        return {'source_id':source['id'],'status':'changed' if changed else ('baseline' if not old else 'unchanged')}
