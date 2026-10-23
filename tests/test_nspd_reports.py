import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from land_assistant.config import Settings
from land_assistant.db import Database
from land_assistant.documents import package
from land_assistant.nspd_reports import Reports, MAX_REPORT_BYTES
from land_assistant.service import Service
from land_assistant.telegram import Telegram

PDF=b'%PDF-1.4\n% synthetic test fixture, not a real NSPD report\n%%EOF\n'

class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service=Service(Database(self.tmp.name))
        self.cid=self.service.create_case(10,{'client':'Клиент','address':'Адрес','purpose':'housing','cadastre':'90:12:172201:102'})
        self.reports=Reports(self.service)

    def test_pdf_preserves_original_and_does_not_verify_case(self):
        before=self.service.case(self.cid,10)['data']
        with patch('land_assistant.nspd_reports.extract',return_value='Материал с номером 90:12:172201:102. Данные учебные, не норма.'):
            row=self.reports.add_pdf(self.cid,10,PDF)
        data=row['data']
        self.assertEqual(data['status'],'unverified')
        self.assertEqual(data['case_cadastre_match'],'found')
        self.assertEqual((Path(self.tmp.name)/data['artifact']).read_bytes(),PDF)
        self.assertEqual(self.service.case(self.cid,10)['data'],before)
        self.assertEqual(self.service.analyze(self.cid,10)['status'],'insufficient_data')
        self.assertIn('не проверен',self.reports.preparation(row['id'],10))
        # A later case edit must invalidate the apparent match in the review view.
        self.service.update_case(self.cid,10,{'cadastre':'90:12:172201:999'})
        self.assertIn('not_found',self.reports.preparation(row['id'],10))

    def test_missing_extractor_still_preserves_pdf_and_deduplicates(self):
        with patch('land_assistant.nspd_reports.extract',side_effect=ValueError('No OCR')):
            a=self.reports.add_pdf(self.cid,10,PDF)
            b=self.reports.add_pdf(self.cid,10,PDF)
        self.assertEqual(a['id'],b['id'])
        self.assertEqual(a['data']['extraction'],'manual_review_required')
        self.assertEqual(len(self.reports.list(self.cid,10)),1)

    def test_link_is_never_fetched_and_rejects_login_secrets(self):
        url='https://nspd.gov.ru/urban-analyze?reportId=demo'
        row=self.reports.add_link(self.cid,10,url)
        self.assertEqual(row['data']['extraction'],'not_fetched')
        self.assertEqual(self.reports.add_link(self.cid,10,url)['id'],row['id'])
        for bad in ('https://evil.example/report','https://nspd.gov.ru.evil.example/report','http://nspd.gov.ru/report','https://user:pass@nspd.gov.ru/report','https://nspd.gov.ru/report?access_token=secret','https://nspd.gov.ru/report#code=secret'):
            with self.assertRaises(ValueError):self.reports.add_link(self.cid,10,bad)

    def test_files_rejected_and_ownership_enforced(self):
        for data in (b'not a PDF',b'%PDF-1.4 incomplete',b'%PDF-'+b'x'*MAX_REPORT_BYTES):
            with self.assertRaises(ValueError):self.reports.add_pdf(self.cid,10,data)
        row=self.reports.add_link(self.cid,10,'https://nspd.gov.ru/urban-analyze?reportId=test')
        for fn in (lambda:self.reports.get(row['id'],99),lambda:self.reports.list(self.cid,99),lambda:self.reports.preparation(row['id'],99),lambda:self.reports.add_pdf(self.cid,99,PDF)):
            with self.assertRaises(ValueError):fn()

    def test_original_and_review_in_document_package(self):
        with patch('land_assistant.nspd_reports.extract',side_effect=ValueError()):
            row=self.reports.add_pdf(self.cid,10,PDF)
        with zipfile.ZipFile(io.BytesIO(package(self.service,self.cid,10))) as archive:
            self.assertEqual(archive.read(f'nspd/report-{row["id"]}-UNVERIFIED.pdf'),PDF)
            self.assertIn('не проверен',archive.read(f'nspd/report-{row["id"]}-REVIEW.txt').decode())
            self.assertEqual(json.loads(archive.read('nspd/materials.json'))[0]['data']['status'],'unverified')

    def bot(self,token=''):
        bot=Telegram(Settings(Path(self.tmp.name),telegram_token=token,allowed_users=(10,)),self.service)
        bot.say=lambda owner,text:None
        bot.send_file=lambda owner,name,data:None
        return bot

    def message(self,text='',document=None,owner=10):
        m={'from':{'id':owner},'chat':{'id':owner,'type':'private'},'text':text}
        if document:m['document']=document
        return {'message':m}

    def test_url_button_and_link_receipt_in_session(self):
        bot=self.bot('test-token')
        with patch.object(bot,'call',return_value={}) as call:
            bot.handle(self.message(f'/nspd {self.cid}'))
        payload=call.call_args.args[1]
        self.assertEqual(payload['reply_markup']['inline_keyboard'][0][0]['url'],'https://nspd.gov.ru/urban-analyze')
        self.assertEqual(self.service.db.session(10)['step'],'nspd_result')
        with patch.object(bot,'call',return_value={}):
            bot.handle(self.message('https://nspd.gov.ru/urban-analyze?reportId=example'))
        self.assertEqual(len(self.reports.list(self.cid,10)),1)
        self.assertEqual(self.service.db.session(10),{})

    def test_pdf_route_cancel_and_concept_separation(self):
        bot=self.bot()
        bot.handle(self.message(f'/nspd_import {self.cid}'))
        with patch.object(bot,'download_report',return_value=PDF),patch('land_assistant.nspd_reports.extract',side_effect=ValueError()):
            bot.handle(self.message(document={'file_id':'test','file_name':'../../report.pdf'}))
        self.assertEqual(len(self.reports.list(self.cid,10)),1)
        bot.handle(self.message(f'/nspd_import {self.cid}'))
        bot.handle(self.message('/cancel'))
        self.assertEqual(self.service.db.session(10),{})
        with patch.object(bot,'photo') as photo:
            bot.handle(self.message(document={'file_id':'test','file_name':'plan.png'}))
            photo.assert_called_once()
        bot.handle(self.message(f'/nspd_import {self.cid}',owner=99))
        self.assertEqual(self.service.db.session(99),{})

    def test_download_checks_actual_size_and_does_not_use_filename_as_path(self):
        bot=self.bot('test-token')
        with self.assertRaises(ValueError):bot.download_report({'file_name':'bad.exe'})
        with self.assertRaises(ValueError):bot.download_report({'file_name':'r.pdf','file_size':MAX_REPORT_BYTES+1})
        with patch.object(bot,'call',return_value={'file_path':'../private/file.pdf'}):
            with self.assertRaises(ValueError):bot.download_report({'file_name':'r.pdf','file_id':'1'})
        stream=io.BytesIO(PDF)
        with patch.object(bot,'call',return_value={'file_path':'documents/file.pdf'}),patch('land_assistant.telegram.urllib.request.urlopen',return_value=stream):
            self.assertEqual(bot.download_report({'file_name':'../../r.pdf','file_id':'1'}),PDF)
