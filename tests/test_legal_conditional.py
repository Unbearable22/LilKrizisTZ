import asyncio
import tempfile
import unittest
from unittest.mock import patch
from test_legal_knowledge import make_library
from land_assistant.legal.model import DemoModel
from land_assistant.legal.pipeline import LegalPipeline,validate_answer
from land_assistant.legal.errors import LegalError
from land_assistant.legal.privacy import public_result

class ConditionalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=make_library(self.tmp.name)

    def test_clear_general_question_needs_no_intake(self):
        r=asyncio.run(LegalPipeline(self.root,DemoModel(),demo=True).run('Как образовать участок?',{}))
        self.assertEqual(r['status'],'answered');self.assertIn('mcp.initialize',r['trace'])

    def test_unknown_facts_allow_grounded_scenarios_with_optional_questions(self):
        class Conditional(DemoModel):
            async def answer(self,**kw):
                self.received=kw
                fid=kw['fragments'][0]['id']
                return {'status':'partial_answer','answer':'Сначала определите исходные границы.', 'citations':[fid],'limitations':[], 'missing_fields':['rights','land_use'], 'scenarios':[{'condition':'границы известны','outcome':'уточните порядок подготовки документов','citations':[fid]}]}
        model=Conditional();q='Проверьте мой участок: как образовать участок?'
        r=asyncio.run(LegalPipeline(self.root,model,demo=True).run(q,{'rights':'не знаю'}))
        self.assertEqual(r['status'],'partial_answer');self.assertIn('Если границы известны',r['answer'])
        self.assertEqual(model.received['original_question'],q);self.assertEqual(model.received['scope'],'parcel')
        self.assertEqual([x['key'] for x in r['missing_fields']],['land_use'])
        self.assertNotIn('citations',str(public_result(r)));self.assertNotIn('sources',public_result(r))

    def test_conditional_branches_require_individual_evidence_and_no_references(self):
        fragments=[{'id':'known','title':'Fixture','source_url':'https://fixture.invalid'}]
        base={'status':'partial_answer','answer':'Общий порядок.','citations':['known'],'limitations':[],'missing_fields':['rights']}
        for branch in [ {'condition':'известны права','outcome':'действуйте','citations':['invented']}, {'condition':'известны права','outcome':'См. статью 12.','citations':['known']} ]:
            with self.subTest(branch=branch),self.assertRaises(LegalError):validate_answer({**base,'scenarios':[branch]},fragments)

    def test_missing_norms_are_not_replaced_by_hypotheses(self):
        with patch('land_assistant.legal.pipeline.LocalLegalMCP') as mcp:
            from unittest.mock import AsyncMock
            mcp.return_value.context=AsyncMock(return_value={'trace':[],'fragments':[],'limitations':[]})
            r=asyncio.run(LegalPipeline(self.root,DemoModel(),demo=True).run('Проверьте мой участок',{}))
        self.assertEqual(r['status'],'insufficient_sources');self.assertNotIn('Если',r['answer'])

    def test_supported_part_survives_another_task_without_evidence(self):
        class Two(DemoModel):
            async def classify(self,*args):return {'tasks':[{'task_id':str(i),'function_id':'legal_help','formulation':q,'scope':'general'} for i,q in enumerate(['образование участка','межгалактическая орбита'])]}
        r=asyncio.run(LegalPipeline(self.root,Two(),demo=True).run('Два вопроса об участке',{}))
        self.assertEqual(r['status'],'partial_answer');self.assertIn('ДЕМОНСТРАЦИЯ',r['answer']);self.assertTrue(r['limitations'])

    def test_definitive_parcel_verdict_is_rejected(self):
        with self.assertRaises(LegalError):validate_answer({'status':'answered','answer':'Стройте.','citations':['known'],'limitations':[]},[{'id':'known'}],scope='parcel')

    def test_valid_branch_then_missing_or_fabricated_evidence_is_rejected(self):
        fragments=[{'id':'known'}]
        r={'status':'partial_answer','answer':'Общий порядок.','citations':['known'],'limitations':[],'missing_fields':[],'scenarios':[{'condition':'есть сведения','outcome':'уточните порядок','citations':['known']}]}
        validate_answer(r,fragments)
        r['scenarios'][0]['citations']=[]
        with self.assertRaises(LegalError):validate_answer(r,fragments)

    def test_answer_budget_can_cover_reasoning_and_conditional_json(self):
        import json,httpx
        from pathlib import Path
        from land_assistant.config import Settings
        from land_assistant.legal.model import LiveModel
        settings=Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture')
        settings.llm_answer_tokens=5000
        real_client=httpx.AsyncClient
        def handler(request):
            enough=json.loads(request.content)['max_tokens']>=4500
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop' if enough else 'length','message':{'content':'{"status":"answered"}' if enough else '{'}}]})
        with patch('land_assistant.legal.model.httpx.AsyncClient',side_effect=lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw)):
            result=asyncio.run(LiveModel(settings).answer(original_question='Вопрос',formulation='Вопрос',intake={},prompt='Правила',fragments=[]))
        self.assertEqual(result['status'],'answered')

    def test_construction_intent_beats_incidental_unknown_land_category(self):
        from land_assistant.legal.knowledge import Knowledge
        (self.root/'laws/demo.md').write_text('''## Статья 1. Образование участка
Категория земли и разрешенное использование при образовании участка. Категория земли и разрешенное использование.
## Статья 2. Уведомление о планируемом строительстве индивидуального жилого дома
Застройщик подает уведомление. Уполномоченный орган проверяет параметры дома.
''')
        hits=Knowledge(self.root,demo=True).search('Можно ли построить жилой дом? Категорию земли и разрешенное использование не знаю')
        self.assertIn('Уведомление',hits[0]['citation'])

    def test_explicit_unknown_is_not_asked_again(self):
        class Conditional(DemoModel):
            async def answer(self,**kw):
                fid=kw['fragments'][0]['id']
                return {'status':'partial_answer','answer':'Общий порядок.','citations':[fid],'limitations':[],'missing_fields':['rights'],'scenarios':[{'condition':'права подтверждены','outcome':'уточните порядок действий','citations':[fid]}]}
        r=asyncio.run(LegalPipeline(self.root,Conditional(),demo=True).run('Проверьте мой участок',{'rights':'не знаю'}))
        self.assertEqual(r['status'],'partial_answer');self.assertEqual(r['missing_fields'],[])

    def test_urban_plan_is_not_misread_as_construction_intent(self):
        from land_assistant.legal.knowledge import Knowledge
        (self.root/'laws/demo.md').write_text('''## Статья 1. Градостроительный план земельного участка
План содержит границы и сведения об участке.
## Статья 2. Разрешение на строительство на земельном участке
Застройщик получает разрешение на строительство объекта.
''')
        hits=Knowledge(self.root,demo=True).search('Какие сведения содержит градостроительный план земельного участка')
        self.assertIn('Градостроительный план',hits[0]['citation'])
