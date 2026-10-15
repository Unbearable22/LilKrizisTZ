"""Private administration API. Bind loopback; use a TLS reverse proxy remotely."""
import hmac
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from .db import dumps
from .documents import package
from .monitor import Monitor


def make_handler(service,token):
    if len(token)<32:
        raise ValueError('ADMIN_API_TOKEN должен содержать не менее 32 символов.')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass  # Do not log personal data or credentials in URL paths.
        def reply(self,status,payload,content_type='application/json; charset=utf-8',name=None):
            body=payload if isinstance(payload,bytes) else dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            if name:
                self.send_header('Content-Disposition',f'attachment; filename="{name}"')
            self.end_headers()
            self.wfile.write(body)
        def do_GET(self):
            self.dispatch()
        def do_POST(self):
            self.dispatch()
        def dispatch(self):
            if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                self.reply(401,{'error':'Требуется авторизация администратора.'})
                return
            try:
                path=urlsplit(self.path).path.strip('/').split('/')
                method=self.command
                p={}
                if method=='POST':
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=1024*1024:
                        raise ValueError('JSON-тело должно быть от 1 байта до 1 МБ.')
                    p=json.loads(self.rfile.read(size))
                    if not isinstance(p,dict):
                        raise ValueError('Ожидается JSON-объект.')
                if method=='GET' and path==['health']:
                    self.reply(200,{'status':'ok','version':'0.1.0'})
                elif path==['municipalities']:
                    if method=='POST':
                        self.reply(201,{'id':service.import_municipality(p)})
                    else:
                        self.reply(200,service.db.rows('SELECT * FROM municipalities'))
                elif path==['rules']:
                    if method=='POST':
                        self.reply(201,{'id':service.import_rule(p)})
                    else:
                        self.reply(200,service.db.rows('SELECT * FROM rules'))
                elif method=='POST' and path==['legal-documents']:
                    self.reply(201,{'id':service.import_legal_document(p)})
                elif method=='POST' and path==['legal-search']:
                    self.reply(200,service.legal_search(p['kind'],p['query']))
                elif path==['sources']:
                    if method=='POST':
                        self.reply(201,{'id':service.source(p)})
                    else:
                        self.reply(200,service.db.rows('SELECT * FROM sources'))
                elif method=='POST' and path==['monitor']:
                    self.reply(200,Monitor(service.db).run())
                elif path==['cases']:
                    if method=='POST':
                        owner=p.pop('owner_id',None)
                        if isinstance(owner,bool) or not isinstance(owner,int) or owner<=0:
                            raise ValueError('Нужен положительный owner_id Telegram.')
                        self.reply(201,{'id':service.create_case(owner,p)})
                    else:
                        self.reply(200,service.db.rows('SELECT * FROM cases ORDER BY id DESC'))
                elif len(path)>=2 and path[0]=='cases':
                    cid=int(path[1])
                    if method=='GET' and len(path)==2:
                        self.reply(200,service.case(cid))
                    elif method=='POST' and len(path)==2:
                        case=service.case(cid)
                        self.reply(200,{'id':service.update_case(cid,case['owner_id'],p)})
                    elif method=='POST' and path[2:]==['analyze']:
                        self.reply(200,service.analyze(cid))
                    elif method=='GET' and path[2:]==['documents']:
                        self.reply(200,package(service,cid),'application/zip',f'case-{cid}.zip')
                    else:
                        self.reply(404,{'error':'Маршрут не найден.'})
                elif method=='GET' and path==['notifications']:
                    self.reply(200,service.db.rows('SELECT * FROM notifications ORDER BY id DESC'))
                else:
                    self.reply(404,{'error':'Маршрут не найден.'})
            except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as exc:
                self.reply(400,{'error':str(exc)[:300]})
            except Exception:
                self.reply(500,{'error':'Внутренняя ошибка. Проверьте журнал сервиса.'})
    return Handler

def serve(service,settings,host='127.0.0.1',port=8080):
    server=ThreadingHTTPServer((host,port),make_handler(service,settings.admin_token))
    server.daemon_threads=True
    print(f'Administration API: http://{host}:{port}',flush=True)
    server.serve_forever()
