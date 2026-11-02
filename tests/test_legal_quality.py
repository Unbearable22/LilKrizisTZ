import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from land_assistant.config import Settings
from land_assistant.legal.model import LiveModel, DemoModel
from land_assistant.legal.pipeline import LegalPipeline
from land_assistant.legal.privacy import has_references, public_result
from land_assistant.legal.knowledge import Knowledge
from test_legal_knowledge import make_library

class QualityTests(unittest.TestCase):
    def test_generic_legislation_is_not_a_named_source(self):
        for text in ['Это предусмотрено федеральным законом.', 'Федеральными законами могут устанавливаться дополнительные условия.']:
            self.assertFalse(has_references(text),text)
        for text in ['Согласно Федеральному закону о садоводстве.', 'См. закон о садоводстве.', 'См. №217-ФЗ.']:
            self.assertTrue(has_references(text),text)

    def test_provider_failures_are_distinguished_without_secrets(self):
        settings=Settings(Path('data'),llm_url='https://model.invalid/v1/chat/completions',llm_key='secret',llm_model='fixture')
        cases=[(httpx.ReadTimeout('private body'), 'llm_timeout'), (httpx.ConnectError('private body'),'llm_connection'), (httpx.Response(429,json={'error':'private body'}),'llm_rate_limit'), (httpx.Response(200,json={'choices':[{'message':{'content':'not json'}}]}),'llm_invalid_json')]
        real_client=httpx.AsyncClient
        for response,code in cases:
            def handler(request):
                if isinstance(response,Exception):raise response
                return response
            with self.subTest(code=code),patch('land_assistant.legal.model.httpx.AsyncClient',side_effect=lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw)):
                try:asyncio.run(LiveModel(settings).classify('Вопрос'))
                except ValueError as exc:self.assertEqual(getattr(exc,'code',None),code);self.assertNotIn('private body',str(exc))
                else:self.fail('Provider failure accepted')

    def test_single_reference_rewrite_is_validated(self):
        class RewriteModel(DemoModel):
            calls=0
            async def answer(self,**kw):return {'answer':'См. закон о садоводстве.','citations':[kw['fragments'][0]['id']],'limitations':[]}
            async def rewrite_answer(self,**kw):
                self.calls+=1
                return {'status':'answered','answer':'Необходимы исходные сведения о границах.','citations':[kw['fragments'][0]['id']],'limitations':[]}
        with tempfile.TemporaryDirectory() as tmp:
            root=make_library(tmp);model=RewriteModel()
            result=asyncio.run(LegalPipeline(root,model,demo=True).run('Образование участка',{'situation':'Участок','goal':'Порядок образования'}))
            self.assertEqual(result['status'],'answered');self.assertEqual(model.calls,1)
            self.assertNotIn('diagnostics',public_result(result))

    def test_rewrite_cannot_bypass_evidence_check(self):
        class RewriteModel(DemoModel):
            calls=0
            async def answer(self,**kw):return {'answer':'См. закон о садоводстве.','citations':[kw['fragments'][0]['id']],'limitations':[]}
            async def rewrite_answer(self,**kw):
                self.calls+=1
                return {'status':'answered','answer':'Непроверенное утверждение.','citations':['invented'],'limitations':[]}
        with tempfile.TemporaryDirectory() as tmp:
            model=RewriteModel();result=asyncio.run(LegalPipeline(make_library(tmp),model,demo=True).run('Образование участка',{'situation':'Участок','goal':'Порядок образования'}))
            self.assertEqual(result['status'],'error');self.assertEqual(model.calls,1)
            self.assertEqual(result['diagnostics']['code'],'invalid_citations')

    def test_long_procedure_includes_beginning_not_only_matching_middle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=make_library(tmp)
            text='## Статья 1. Уведомление о строительстве\nЗастройщик подаёт заявление в местную администрацию.\n\n'+('Общие обязательные сведения. '*130)+'\n\n'
            text+='\n\n'.join(('Порядок уведомления о строительстве: орган проверяет параметры. '*65) for _ in range(8))
            (root/'laws/demo.md').write_text(text)
            hits=Knowledge(root,demo=True).search('Порядок уведомления о строительстве')
            contents=[Knowledge(root,demo=True).read(h['id'])['text'] for h in hits]
            self.assertTrue(any('Застройщик подаёт' in c for c in contents))

    def test_unrepaired_references_stop_after_one_rewrite(self):
        class StillBad(DemoModel):
            calls=0
            async def answer(self,**kw):return {'answer':'См. закон о садоводстве.','citations':[kw['fragments'][0]['id']],'limitations':[]}
            async def rewrite_answer(self,**kw):self.calls+=1;return await self.answer(**kw)
        with tempfile.TemporaryDirectory() as tmp:
            model=StillBad();result=asyncio.run(LegalPipeline(make_library(tmp),model,demo=True).run('Образование участка',{'situation':'Участок','goal':'Порядок образования'}))
            self.assertEqual(result['status'],'error');self.assertEqual(model.calls,1)
            self.assertEqual(result['diagnostics']['code'],'visible_references')

    def test_diagnostic_stage_and_code_are_private(self):
        from land_assistant.legal.errors import LegalError
        class TimeoutModel:
            async def classify(self,*args):raise LegalError('llm_timeout')
        with tempfile.TemporaryDirectory() as tmp:
            result=asyncio.run(LegalPipeline(make_library(tmp),TimeoutModel()).run('Вопрос',{}))
            self.assertEqual(result['diagnostics']['stage'],'classify')
            self.assertEqual(result['diagnostics']['code'],'llm_timeout')
            self.assertNotIn('diagnostics',public_result(result))

    def test_classifier_model_can_be_selected_without_changing_executor(self):
        settings=Settings(Path('data'),llm_url='https://model.invalid/v1/chat/completions',llm_model='executor')
        settings.llm_classifier_model='classifier'
        payloads=[]
        def handler(request):
            payloads.append(json.loads(request.content));return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
        real_client=httpx.AsyncClient
        with patch('land_assistant.legal.model.httpx.AsyncClient',side_effect=lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw)):
            model=LiveModel(settings)
            asyncio.run(model.classify('Вопрос'))
            asyncio.run(model.answer(original_question='Вопрос',formulation='Вопрос',intake={},prompt='Правила',fragments=[]))
        self.assertEqual([p['model'] for p in payloads],['classifier','executor'])

    def test_named_regulations_and_orders_are_references(self):
        for text in ['Согласно постановлению Правительства РФ от 28.01.2006 № 47.','Согласно приказу Минэкономразвития России от 08.12.2015 № 921.']:
            self.assertTrue(has_references(text),text)
