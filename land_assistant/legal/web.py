"""Loopback-only prototype host; not a public multi-tenant deployment."""
import asyncio
import json
import mimetypes
import os
import select
import socket
from contextlib import suppress
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .privacy import public_result
from . import speech

STATIC={'/':'index.html','/chat':'index.html','/index.html':'index.html','/script.js':'script.js','/db.js':'db.js','/styles.css':'styles.css','/legal-api.js':'legal-api.js','/voice.js':'voice.js'}


async def run_connected(awaitable,connection):
    """Cancel downstream async work when the browser closes the HTTP connection."""
    task=asyncio.create_task(awaitable)
    try:
        while not task.done():
            await asyncio.wait({task},timeout=.1)
            if task.done():break
            readable,_,_=select.select([connection],[],[],0)
            if readable and not connection.recv(1,socket.MSG_PEEK):
                raise ConnectionAbortedError('Клиент отключился.')
        return await task
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):await task


def make_web_handler(pipeline,static_root):
    root=Path(static_root).resolve()
    capacity=threading.BoundedSemaphore(2)
    speech_capacity=threading.BoundedSemaphore(1)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup();self.connection.settimeout(10)
        def log_message(self,*args):
            pass
        def reply(self,status,data,ctype='application/json; charset=utf-8'):
            body=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def error(self,status,text):
            self.reply(status,{'status':'error','answer':text,'mode':'demo' if pipeline.demo else 'live','missing_fields':[],'limitations':[]})
        def allowed_host(self):
            host=self.headers.get('Host','')
            expected={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            codespace=os.getenv('CODESPACE_NAME','')
            if codespace:expected.add(f'{codespace}-{self.server.server_port}.app.github.dev')
            return host in expected
        def do_GET(self):
            if not self.allowed_host():self.error(403,'Неподдерживаемый адрес локального сервера.');return
            path=urlsplit(self.path).path
            if path=='/api/legal-help/config':
                self.reply(200,{'mode':'demo' if pipeline.demo else 'live','max_question_length':8000,'notice':'Демонстрационный режим без нейросети: показ работы сервиса, без юридического заключения.' if pipeline.demo else 'Юридическая помощь по праву РФ: земельные и другие вопросы с учётом доступных нормативных материалов.','attachments_supported':False})
            elif path in STATIC:
                target=root/STATIC[path]
                if not target.is_file() or target.resolve().parent!=root:
                    self.error(404,'Файл интерфейса не найден.');return
                ctype=mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
                self.reply(200,target.read_bytes(),ctype+'; charset=utf-8')
            else:self.error(404,'Страница не найдена.')
        def transcribe_audio(self):
            origin=self.headers.get('Origin')
            if origin and (urlsplit(origin).netloc!=self.headers.get('Host') or urlsplit(origin).scheme not in ('http','https')):
                self.error(403,'Запрос с другого сайта запрещён.');return
            if self.headers.get('Transfer-Encoding'):
                self.error(400,'Требуется фиксированный размер записи.');return
            try:size=int(self.headers.get('Content-Length','0'))
            except ValueError:self.error(400,'Некорректный размер записи.');return
            if not 0<size<=speech.MAX_BYTES:self.error(413,'Запись пуста или превышает 8 МиБ.');return
            if not speech_capacity.acquire(blocking=False):self.error(429,'Распознавание занято. Попробуйте немного позже.');return
            try:
                body=self.rfile.read(size)
                if len(body)!=size:self.error(400,'Запись передана не полностью.');return
                text=speech.transcribe(body,self.headers.get('Content-Type',''))
                self.reply(200,{'text':text})
            except speech.SpeechError as exc:self.error(422,str(exc))
            except (TimeoutError,OSError):self.error(408,'Не удалось получить запись. Попробуйте ещё раз.')
            finally:speech_capacity.release()
        def do_POST(self):
            if not self.allowed_host():self.error(403,'Неподдерживаемый адрес локального сервера.');return
            if urlsplit(self.path).path=='/api/transcribe':self.transcribe_audio();return
            if urlsplit(self.path).path!='/api/legal-help':self.error(404,'Маршрут не найден.');return
            origin=self.headers.get('Origin')
            if origin and (urlsplit(origin).netloc!=self.headers.get('Host') or urlsplit(origin).scheme not in ('http','https')):
                self.error(403,'Запрос с другого сайта запрещён.');return
            if self.headers.get('Transfer-Encoding'):
                self.error(400,'Требуется запрос фиксированного размера.');return
            if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
                self.error(415,'Ожидается application/json.');return
            try:size=int(self.headers.get('Content-Length','0'))
            except ValueError:self.error(400,'Некорректный размер запроса.');return
            if size>262144:self.error(413,'Запрос превышает 256 КиБ.');return
            if size<=0:self.error(400,'Пустое тело запроса.');return
            if not capacity.acquire(blocking=False):self.error(429,'Два запроса уже выполняются. Дождитесь завершения и повторите.');return
            try:
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):raise ValueError('Ожидается JSON-объект.')
                if payload.get('attachments'):raise ValueError('Анализ вложений пока не подключён. Уберите вложения и опишите сведения текстом.')
                if set(payload)-{'question','intake','chat_id','attachments','history'}:raise ValueError('Неизвестные поля запроса.')
                chat_id=payload.get('chat_id','')
                if not isinstance(chat_id,str) or len(chat_id)>100:raise ValueError('Некорректный идентификатор чата.')
                result=asyncio.run(run_connected(pipeline.run(payload.get('question'),payload.get('intake',{}),**({'history':payload['history']} if 'history' in payload else {})),self.connection))
                result['chat_id']=chat_id
                self.reply(400 if result['status']=='invalid_request' else 200,public_result(result))
            except (ConnectionAbortedError,ConnectionResetError,BrokenPipeError):pass
            except (ValueError,TypeError,UnicodeError):self.error(400,'Некорректный JSON или поля запроса. Анализ вложений пока не поддерживается.')
            except TimeoutError:self.error(408,'Истекло время чтения запроса.')
            except Exception:self.error(500,'Внутренняя ошибка прототипа. Повтор не выполнялся автоматически.')
            finally:capacity.release()
    return Handler


def serve_web(pipeline,static_root,port=8080):
    server=ThreadingHTTPServer(('127.0.0.1',port),make_web_handler(pipeline,static_root))
    server.daemon_threads=True
    print(f'GROUNDandLAW: http://127.0.0.1:{server.server_port} · режим {"DEMO" if pipeline.demo else "LIVE"}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
