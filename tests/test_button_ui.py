import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from land_assistant.config import Settings
from land_assistant.db import Database
from land_assistant.service import Service
from land_assistant.telegram import Telegram


class ButtonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.service=Service(Database(self.tmp.name))
        self.bot=Telegram(Settings(Path(self.tmp.name),telegram_token='fixture',allowed_users=(10,)),self.service)
        self.bot.call=Mock(return_value={})
        self.bot.send_file=Mock()
        self.cid=self.service.create_case(10,{'client':'Клиент','address':'Адрес','purpose':'housing'})

    def text(self,value):
        self.bot.handle({'message':{'from':{'id':10},'chat':{'id':10,'type':'private'},'text':value}})

    def click(self,data,owner=10,chat=10,kind='private'):
        self.bot.handle({'callback_query':{'id':'fixture','from':{'id':owner},'data':data,'message':{'chat':{'id':chat,'type':kind}}}})

    def messages(self):
        return [a.args[1] for a in self.bot.call.call_args_list if a.args[0]=='sendMessage']

    def buttons(self):
        return [b for m in self.messages() for row in m.get('reply_markup',{}).get('inline_keyboard',[]) for b in row]

    def option(self,index):
        token=self.service.db.session(10)['ui_token'];self.click(f'value:{token}:{index}')

    def skip(self):
        token=self.service.db.session(10)['ui_token'];self.click(f'skip:{token}')

    def test_create_case_without_commands_and_cancel_from_every_step(self):
        self.text('📐 Новый участок');self.text('Новый клиент');self.text('Новый адрес');self.skip()
        self.assertEqual(self.service.db.session(10)['step'],'purpose')
        self.option(1);self.skip()
        cases=self.service.cases(10)
        self.assertEqual(cases[0]['data']['purpose'],'commercial')
        self.assertEqual(cases[0]['data']['client'],'Новый клиент')
        self.assertEqual(self.service.db.session(10),{})
        self.assertTrue(any(b['callback_data'].startswith('analyze:') for b in self.buttons() if 'callback_data' in b))
        self.text('📐 Новый участок');self.text('🏠 Главное меню')
        self.assertEqual(self.service.db.session(10),{})

    def test_case_chooser_and_all_actions(self):
        self.text('📁 Мои дела');self.click(f'case:{self.cid}')
        actions={b.get('callback_data','').split(':')[0] for b in self.buttons()}
        self.assertTrue({'analyze','docs','nspd','reports','fields','explain','concepts'}<=actions)
        self.click(f'analyze:{self.cid}');self.click(f'docs:{self.cid}')
        self.bot.send_file.assert_called()
        self.assertTrue(any('Недостаточно данных' in m['text'] for m in self.messages()))

    def test_field_editor_numeric_boolean_and_invalid_value(self):
        self.click(f'fields:{self.cid}:1');self.click(f'field:{self.cid}:height_m');self.text('3,5')
        self.assertEqual(self.service.case(self.cid,10)['data']['height_m'],3.5)
        self.click(f'field:{self.cid}:height_m');self.text('не число')
        self.assertEqual(self.service.case(self.cid,10)['data']['height_m'],3.5)
        self.assertEqual(self.service.db.session(10)['step'],'edit_field')
        self.text('4');self.click(f'field:{self.cid}:restrictions_checked');self.option(1)
        self.assertFalse(self.service.case(self.cid,10)['data']['restrictions_checked'])
        self.click(f'field:{self.cid}:purpose');self.option(2)
        self.assertEqual(self.service.case(self.cid,10)['data']['purpose'],'agriculture')

    def test_edit_coordinates_and_restrictions_without_json(self):
        self.click(f'field:{self.cid}:coordinates')
        self.text('34.1 45.0\n34.1004 45.0\n34.1004 45.0003\n34.1 45.0003')
        self.assertEqual(len(self.service.case(self.cid,10)['data']['coordinates']),4)
        self.click(f'field:{self.cid}:restrictions');self.text('Охранная зона; Сервитут')
        self.assertEqual(len(self.service.case(self.cid,10)['data']['restrictions']),2)
        self.click(f'field:{self.cid}:restrictions');self.option(0)
        self.assertEqual(self.service.case(self.cid,10)['data']['restrictions'],[])

    def test_stale_value_callback_does_not_change_another_field(self):
        self.click(f'field:{self.cid}:purpose')
        old=self.service.db.session(10)['ui_token']
        self.click(f'field:{self.cid}:restrictions_checked')
        self.click(f'value:{old}:0')
        self.assertNotIn('restrictions_checked',self.service.case(self.cid,10)['data'])
        self.assertEqual(self.service.db.session(10)['field'],'restrictions_checked')

    def test_forged_callback_and_wrong_chat_cannot_access_case(self):
        other=self.service.create_case(99,{'client':'PRIVATE CLIENT','address':'Private','purpose':'housing'})
        self.click(f'case:{other}');self.click(f'nspd:{other}');self.click(f'field:{other}:height_m')
        self.assertNotIn('PRIVATE CLIENT',json.dumps(self.messages()))
        self.assertEqual(self.service.db.session(10),{})
        calls=len(self.bot.call.call_args_list)
        self.click(f'case:{self.cid}',owner=99,chat=99)
        self.click(f'case:{self.cid}',chat=-10,kind='group')
        self.assertEqual(len(self.bot.call.call_args_list),calls)

    def test_law_and_concept_choices(self):
        self.text('📚 Законодательство');self.click('law:land_code');self.text('образование участка')
        self.assertTrue(any('не найдены' in m['text'] for m in self.messages()))
        self.click(f'concepts:{self.cid}');self.click(f'concept:{self.cid}:interior');self.skip()
        self.assertEqual(self.service.db.session(10)['step'],'concept_reference')
        with patch.object(self.bot.integrations,'concept',return_value=b'PNG') as generate:
            self.click(f'generate:{self.cid}')
            generate.assert_called_once_with(self.cid,10,'interior','')
        self.bot.send_file.assert_called_with(10,'concept-PRELIMINARY.png',b'PNG')
        self.assertEqual(self.service.db.session(10),{})

    def test_nspd_button_report_link_and_return_to_case(self):
        self.text('🌐 НСПД');self.click(f'nspd:{self.cid}')
        self.assertTrue(any(b.get('url')=='https://nspd.gov.ru/urban-analyze' for b in self.buttons()))
        self.text('https://nspd.gov.ru/urban-analyze?reportId=example')
        self.click(f'reports:{self.cid}:0')
        report=self.bot.reports.list(self.cid,10)[0]
        self.click(f'report:{report["id"]}')
        self.assertTrue(any('не проверен' in m['text'] for m in self.messages()))
        self.click(f'case:{self.cid}')
        self.assertEqual(self.service.db.session(10),{})

    def test_pagination_and_no_command_hints_in_button_flow(self):
        for i in range(9):self.service.create_case(10,{'client':str(i),'address':'Адрес','purpose':'housing'})
        self.text('📁 Мои дела');self.click('pick:case:1');self.click(f'case:{self.cid}');self.click(f'fields:{self.cid}:2')
        self.text('❓ Помощь');self.text('📐 Новый участок')
        for m in self.messages():
            self.assertNotRegex(m['text'],r'/(?:new|edit|help|cancel|analyze|docs|nspd|concept|generate)\b')
        for b in self.buttons():
            self.assertLessEqual(len(b.get('callback_data','').encode()),64)

    def test_municipality_choices_are_paginated_without_typed_ids(self):
        for i in range(22):self.service.import_municipality({'id':f'm-{i}','name':f'Поселение {i:02}'})
        self.click(f'field:{self.cid}:municipality_id');self.click(f'municipal:{self.cid}:2');self.option(5)
        self.assertEqual(self.service.case(self.cid,10)['data']['municipality_id'],'m-21')

    def test_bad_report_link_keeps_receipt_step(self):
        self.click(f'import:{self.cid}');self.text('https://example.org/not-nspd')
        self.assertEqual(self.service.db.session(10)['step'],'nspd_result')
        self.assertEqual(self.bot.reports.list(self.cid,10),[])
        self.click(f'case:{self.cid}')
        self.assertEqual(self.service.db.session(10),{})

    def test_poll_requests_callbacks_and_acknowledges_before_action(self):
        self.click(f'case:{self.cid}')
        self.assertEqual(self.bot.call.call_args_list[0].args[0],'answerCallbackQuery')
        captured=[]
        def call(method,payload):
            if method=='getUpdates':
                captured.append(payload)
                raise KeyboardInterrupt()
            return {}
        self.bot.call=call
        with self.assertRaises(KeyboardInterrupt):self.bot._poll()
        self.assertIn('callback_query',captured[0]['allowed_updates'])
