import json
import asyncio
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from test_legal_knowledge import make_library

try:
    from land_assistant.legal.web import make_web_handler
    from land_assistant.legal.pipeline import LegalPipeline
    from land_assistant.legal.model import DemoModel
except ImportError:
    make_web_handler=None


class WebTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(make_web_handler,'HTTP-вход прототипа ещё не реализован')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=make_library(self.tmp.name)
        pipeline=LegalPipeline(root,DemoModel(),demo=True)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_web_handler(pipeline,Path(__file__).resolve().parents[1]/'groundAndLaw'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def request(self,path,body=None,headers=None):
        req=urllib.request.Request(self.base+path,data=body,headers=headers or {})
        try:
            with urllib.request.urlopen(req) as response:return response.status,response.read()
        except urllib.error.HTTPError as e:
            status=e.code;data=e.read();e.close();return status,data

    def test_ui_and_spa_are_served_but_secrets_are_not(self):
        for path in ('/','/chat','/script.js','/db.js','/styles.css'):
            status,data=self.request(path);self.assertEqual(status,200);self.assertTrue(data)
        for path in ('/.env','/../.env','/%2e%2e/.env','/knowledge/laws/manifest.json','/land_assistant/config.py'):
            self.assertEqual(self.request(path)[0],404)
        status,data=self.request('/api/legal-help/config')
        self.assertEqual(json.loads(data)['mode'],'demo')

    def test_complete_http_intake_then_real_mcp_answer(self):
        headers={'Content-Type':'application/json','Origin':self.base}
        payload={'question':'Образование земельного участка','intake':{},'chat_id':'c_test'}
        status,data=self.request('/api/legal-help',json.dumps(payload).encode(),headers)
        result=json.loads(data);self.assertEqual(status,200)
        self.assertEqual(result['status'],'answered')
        payload['intake']={'situation':'Общая справка','goal':'Порядок образования'}
        status,data=self.request('/api/legal-help',json.dumps(payload).encode(),headers)
        result=json.loads(data)
        self.assertEqual(result['status'],'answered');self.assertEqual(result['chat_id'],'c_test')
        self.assertNotIn('trace',result)
        self.assertNotIn('sources',result)
        self.assertNotIn('citations',result)
        self.assertNotIn('tasks',result)
        self.assertNotIn('https://example.org',result['answer'])

    def test_bad_origin_and_malformed_or_oversize_payload_rejected(self):
        payload=json.dumps({'question':'Образование участка','intake':{}}).encode()
        self.assertEqual(self.request('/api/legal-help',payload,{'Content-Type':'application/json','Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/legal-help',b'{',{'Content-Type':'application/json'})[0],400)
        self.assertEqual(self.request('/api/legal-help',b'x'*262145,{'Content-Type':'application/json'})[0],413)
        self.assertEqual(self.request('/api/legal-help',payload,{'Content-Type':'text/plain'})[0],415)

    def test_client_disconnect_cancels_pipeline_before_further_work(self):
        started=threading.Event();stopped=threading.Event();finished=threading.Event()
        class SlowPipeline:
            demo=True
            async def run(self,*args):
                started.set()
                try:
                    await asyncio.sleep(3)
                    finished.set()
                    return {'status':'answered'}
                finally:stopped.set()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_web_handler(SlowPipeline(),Path(self.tmp.name)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        conn=socket.create_connection(('127.0.0.1',server.server_port))
        payload=b'{"question":"test","intake":{}}'
        conn.sendall(f'POST /api/legal-help HTTP/1.0\r\nHost: 127.0.0.1:{server.server_port}\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n'.encode()+payload)
        self.assertTrue(started.wait(1))
        conn.close()
        self.assertTrue(stopped.wait(1.5),'Отключение браузера должно остановить серверную цепочку')
        self.assertFalse(finished.is_set())

    def test_unknown_fields_and_attachments_are_not_silently_ignored(self):
        p={'question':'Образование участка','intake':{},'attachments':[{'name':'proof.pdf'}]}
        status,data=self.request('/api/legal-help',json.dumps(p).encode(),{'Content-Type':'application/json'})
        self.assertEqual(status,400)
        self.assertIn('вложен',json.loads(data)['answer'])

    def test_errors_do_not_export_internal_metadata(self):
        for path,body,headers in [('/missing',None,{}),('/api/legal-help',b'{',{'Content-Type':'application/json'})]:
            status,data=self.request(path,body,headers)
            self.assertGreaterEqual(status,400)
            result=json.loads(data)
            self.assertTrue({'sources','citations','trace','tasks','error_code'}.isdisjoint(result))
