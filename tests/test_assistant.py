import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from land_assistant.api import make_handler
from land_assistant.config import Settings
from land_assistant.db import Database
from land_assistant.documents import package
from land_assistant.geometry import polygon,covers,area
from land_assistant.monitor import Monitor
from land_assistant.network import validate_public_url
from land_assistant.service import Service
from land_assistant.telegram import Telegram

ROOT=Path(__file__).resolve().parent.parent

def example(name):
    return json.loads((ROOT/'examples'/name).read_text())

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Database(self.tmp.name)
        self.service=Service(self.db)
        self.service.import_municipality(example('municipality.demo.json'))
        self.service.import_rule(example('rule.demo.json'))
        self.cid=self.service.create_case(10,example('case.json'))

    def test_analysis_and_numerical_conflict(self):
        r=self.service.analyze(self.cid,10)
        self.assertEqual(r['status'],'preliminary_compliant')
        self.assertEqual(len(r['citations']),1)
        self.service.update_case(self.cid,10,{'height_m':30,'building_area_m2':600})
        r=self.service.analyze(self.cid,10)
        self.assertEqual(r['status'],'conflicts')
        self.assertEqual(len(r['conflicts']),2)

    def test_missing_or_unverified_rules_fail_closed(self):
        self.service.update_case(self.cid,10,{'zone':'unknown'})
        self.assertEqual(self.service.analyze(self.cid,10)['status'],'insufficient_data')
        self.service.update_case(self.cid,10,{'zone':'DEMO-Ж1','restrictions_checked':False})
        self.assertEqual(self.service.analyze(self.cid,10)['status'],'insufficient_data')
        self.db.execute('UPDATE rules SET active=0')
        self.assertEqual(self.service.analyze(self.cid,10)['citations'],[])

    def test_owner_isolation(self):
        for call in (lambda:self.service.case(self.cid,99),lambda:self.service.analyze(self.cid,99),lambda:package(self.service,self.cid,99),lambda:self.service.update_case(self.cid,99,{'height_m':1})):
            with self.assertRaises(ValueError):call()
        self.assertEqual(self.service.cases(99),[])

    def test_geometry_rejects_invalid_and_handles_concavity(self):
        for p in ([[0,0],[1,1],[0,1],[1,0]],[[0,0],[1,0],[1,0]],[[0,0],[float('nan'),0],[0,1]]):
            with self.assertRaises(ValueError):polygon(p)
        ring=[[0,0],[4,0],[4,4],[3,4],[3,1],[1,1],[1,4],[0,4]]
        self.assertFalse(covers(ring,[[.5,3],[3.5,3],[2,.5]]))
        self.assertTrue(1000 < area(example('case.json')['coordinates']) < 1100)

    def test_expired_and_ambiguous_data(self):
        self.db.execute("UPDATE rules SET data=json_set(data,'$.valid_until','2000-01-01')")
        self.assertEqual(self.service.analyze(self.cid,10)['status'],'insufficient_data')
        m=example('municipality.demo.json');m['id']='duplicate';self.service.import_municipality(m)
        cid=self.service.create_case(10,example('case.json'))
        self.assertEqual(self.service.case(cid,10)['data']['municipality_resolution'],'ambiguous')

    def test_docx_and_svg_package(self):
        with zipfile.ZipFile(io.BytesIO(package(self.service,self.cid,10))) as z:
            self.assertIn('04-parcel-PRELIMINARY.svg',z.namelist())
            report=z.read('01-analysis.docx')
            with zipfile.ZipFile(io.BytesIO(report)) as doc:
                xml=doc.read('word/document.xml').decode()
                self.assertIn('ДЕМОНСТРАЦИОННЫЙ КЛИЕНТ',xml)
                self.assertIn('Учебный пример',xml)
                from xml.etree.ElementTree import fromstring
                fromstring(xml)

    def test_monitor_baseline_change_dedup_invalidates_rule(self):
        sid=self.db.execute('INSERT INTO sources(title,url,municipality_id,kind) VALUES(?,?,?,?)',('ПЗЗ','https://example.org/rules','demo-only','pzz'))
        first=b'<html><body>Original baseline rules long enough to be extracted and stored properly.</body></html>'
        second=('<html><body>Changed planning rules for cadastre 90:12:172201:102 with new limitations.</body></html>').encode()
        monitor=Monitor(self.db,lambda url:(first,'text/html','utf-8'))
        self.assertEqual(monitor.run()[0]['status'],'baseline')
        self.assertEqual(self.db.rows('SELECT * FROM notifications'),[])
        monitor.fetcher=lambda url:(second,'text/html','utf-8')
        self.assertEqual(monitor.run()[0]['status'],'changed')
        self.assertEqual(len(self.db.rows('SELECT * FROM notifications')),1)
        self.assertEqual(self.db.rows('SELECT active FROM rules')[0]['active'],0)
        self.assertEqual(monitor.run()[0]['status'],'unchanged')
        self.assertEqual(len(self.db.rows('SELECT * FROM notifications')),1)
        note=json.loads(self.db.rows('SELECT data FROM notifications')[0]['data'])
        self.assertIn('найден',note['match'])
        self.assertTrue(Path(note['artifact']).exists())

    def test_monitor_error_preserves_baseline(self):
        self.db.execute('INSERT INTO sources(title,url,kind) VALUES(?,?,?)',('ЗК','https://example.org/code','land_code'))
        def fail(url):raise ValueError('Недоступен')
        result=Monitor(self.db,fail).run()
        self.assertEqual(result[0]['status'],'error')
        self.assertIsNone(self.db.rows('SELECT digest FROM sources')[0]['digest'])

    def test_telegram_access_and_wizard(self):
        bot=Telegram(Settings(Path(self.tmp.name),allowed_users=(10,)),self.service)
        sent=[]
        bot.say=lambda owner,text:sent.append(text)
        def msg(owner,text,chat_type='private'):
            return {'message':{'from':{'id':owner},'chat':{'id':owner,'type':chat_type},'text':text}}
        bot.handle(msg(99,'/cases'))
        bot.handle(msg(10,'/cases','group'))
        self.assertEqual(sent,[])
        for text in ('/new','Клиент','Адрес','нет','housing','нет'):
            bot.handle(msg(10,text))
        self.assertEqual(len(self.service.cases(10)),2)
        self.assertIn('Создано дело',sent[-1])
        bot.handle(msg(10,f'анализ {self.cid}'))
        self.assertIn('предварительно',sent[-1])

    def test_api_auth_and_export(self):
        token='x'*40
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service,token))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(base+'/cases')
        self.assertEqual(err.exception.code,401)
        err.exception.close()
        req=urllib.request.Request(base+f'/cases/{self.cid}/documents',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status,200)
            self.assertTrue(zipfile.is_zipfile(io.BytesIO(response.read())))

    def test_ssrf_rejected(self):
        for url in ('http://example.org','https://user:pass@example.org','https://127.0.0.1','https://[::1]','https://169.254.169.254'):
            with self.assertRaises(ValueError):validate_public_url(url)

    def test_legal_library_search_and_invalidation(self):
        self.service.import_legal_document({'kind':'land_code','title':'Учебный акт','version':'DEMO','source_url':'https://example.org/act','citation':'Учебная статья 11','content':'Образование земельного участка: учебные сведения, не действующая норма.','valid_until':'2099-12-31','verified_by':'DEMO'})
        self.assertEqual(self.service.legal_search('land_code','образование участка')['status'],'found')
        self.assertEqual(self.service.legal_search('217-fz','образование')['status'],'insufficient_data')
        self.db.execute('INSERT INTO sources(title,url,kind) VALUES(?,?,?)',('ЗК','https://example.org/code','land_code'))
        monitor=Monitor(self.db,lambda url:(b'A long enough baseline for the official text of land law example number one.','text/plain','utf-8'))
        monitor.run()
        monitor.fetcher=lambda url:(b'A modified long enough baseline for the official text of land law example number two.','text/plain','utf-8')
        monitor.run()
        self.assertEqual(self.service.legal_search('land_code','образование')['status'],'insufficient_data')

    def test_integration_contracts_without_external_calls(self):
        from land_assistant.integrations import Integrations
        settings=Settings(Path(self.tmp.name),llm_url='https://example.org/chat',llm_model='demo',nspd_url='https://example.org/nspd',image_url='https://example.org/image',image_model='demo')
        integration=Integrations(settings,self.service)
        with patch('land_assistant.integrations.request_json',return_value={'choices':[{'message':{'content':'Пояснение'}}]}) as mock:
            result=integration.explain(self.cid,10)
            self.assertEqual(result['explanation'],'Пояснение')
            self.assertNotIn('ДЕМОНСТРАЦИОННЫЙ КЛИЕНТ',json.dumps(mock.call_args.args[1],ensure_ascii=False))
        with patch('land_assistant.integrations.request_json',return_value={'cadastre':'90:12:172201:102'}):
            self.assertEqual(integration.nspd(self.cid,10)['status'],'received_unverified')
        self.assertEqual(integration.service.case(self.cid,10)['data']['nspd_evidence'],example('case.json')['nspd_evidence'])
        with patch('land_assistant.integrations.request_json',return_value={'data':[{'b64_json':'iVBORw0KGgo='}]}):
            self.assertTrue(integration.concept(self.cid,10,'building').startswith(b'\x89PNG'))
        self.service.update_case(self.cid,10,{'height_m':100})
        with self.assertRaises(ValueError):integration.concept(self.cid,10,'building')

    def test_untrusted_rule_never_activated(self):
        p=example('rule.demo.json');p['version']='unreviewed';p.pop('verified_by')
        self.service.import_rule(p)
        rows=self.db.rows('SELECT active FROM rules WHERE version=?',('unreviewed',))
        self.assertEqual(rows[0]['active'],0)
        self.assertEqual(self.service.analyze(self.cid,10)['status'],'preliminary_compliant')

if __name__=='__main__':unittest.main()
