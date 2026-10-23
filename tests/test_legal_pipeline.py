import asyncio
import tempfile
import unittest
from pathlib import Path
from test_legal_knowledge import make_library

try:
    from land_assistant.legal.pipeline import LegalPipeline
    from land_assistant.legal.model import DemoModel
except ImportError:
    LegalPipeline=DemoModel=None


class LegalPipelineTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(LegalPipeline,'Юридическая цепочка ещё не реализована')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=make_library(self.tmp.name)
        self.intake={'situation':'Нужна общая справка о земельном участке','goal':'Узнать порядок образования'}
        self.pipeline=LegalPipeline(self.root,DemoModel(),demo=True)

    def run_query(self,question,intake=None):
        return asyncio.run(self.pipeline.run(question,self.intake if intake is None else intake))

    def test_empty_and_long_questions_stop_before_model(self):
        class NoModel:
            async def classify(self,q,intake=None):raise AssertionError('Модель не должна вызываться')
        p=LegalPipeline(self.root,NoModel(),demo=True)
        for q in ('', 'x'*8001):
            r=asyncio.run(p.run(q,{}));self.assertEqual(r['status'],'invalid_request');self.assertNotIn('mcp.initialize',r['trace'])

    def test_clear_question_without_intake_runs_mcp(self):
        r=self.run_query('Как образовать участок?',{})
        self.assertEqual(r['status'],'answered')
        self.assertIn('mcp.initialize',r['trace'])

    def test_parcel_without_full_intake_returns_preliminary_answer(self):
        r=self.run_query('Можно ли построить офис на моем участке?',{})
        self.assertEqual(r['status'],'partial_answer')
        self.assertIn('Если',r['answer'])
        self.assertIn('mcp.initialize',r['trace'])
        self.assertLessEqual(len(r['missing_fields']),3)

    def test_demo_really_uses_mcp_and_keeps_original_question(self):
        question='Каков порядок образования земельного участка?'
        r=self.run_query(question)
        self.assertEqual(r['status'],'answered')
        self.assertEqual(r['question'],question)
        self.assertEqual(r['mode'],'demo')
        self.assertTrue(r['sources'])
        self.assertIn('mcp.initialize',r['trace'])
        self.assertIn('ДЕМОНСТРАЦИЯ',r['answer'])

    def test_no_matching_sources_means_no_legal_answer(self):
        r=self.run_query('Как рассчитать орбиту спутника?')
        self.assertEqual(r['status'],'unsupported')
        r=self.run_query('Что сказано про ипотечный кредит?',{'situation':'Ипотека','goal':'Уточнить условия'})
        self.assertEqual(r['status'],'insufficient_sources')
        self.assertEqual(r['sources'],[])

    def test_unknown_function_cannot_choose_server(self):
        class WrongModel:
            async def classify(self,q,intake=None):return {'tasks':[{'task_id':'a','function_id':'shell','formulation':q,'scope':'general'}]}
        r=asyncio.run(LegalPipeline(self.root,WrongModel(),demo=True).run('Вопрос',self.intake))
        self.assertEqual(r['status'],'error');self.assertNotIn('mcp.initialize',r['trace'])

    def test_invented_citation_is_rejected(self):
        class BadCitation(DemoModel):
            async def answer(self,**kwargs):return {'answer':'Произвольное утверждение','citations':['invented'],'limitations':[]}
        r=asyncio.run(LegalPipeline(self.root,BadCitation(),demo=True).run('Образование участка',self.intake))
        self.assertEqual(r['status'],'error')
        self.assertNotIn('Произвольное утверждение',r['answer'])

    def test_completed_intake_resolves_ambiguous_question_without_rewriting_it(self):
        class Clarify(DemoModel):
            async def classify(self,q,intake=None):
                if not intake or not intake.get('goal'):return {'tasks':[],'needs_clarification':True}
                return {'tasks':[{'task_id':'a','function_id':'legal_help','formulation':intake['goal'],'scope':'general'}]}
        pipeline=LegalPipeline(self.root,Clarify(),demo=True)
        first=asyncio.run(pipeline.run('Помогите',{}))
        self.assertEqual(first['status'],'needs_clarification')
        result=asyncio.run(pipeline.run('Помогите',{'situation':'Вопрос об участке','goal':'Образование участка'}))
        self.assertEqual(result['status'],'answered')
        self.assertEqual(result['question'],'Помогите')

    def test_missing_prompt_and_duplicate_task_ids_are_errors(self):
        (self.root/'prompts/legal_help.txt').unlink()
        r=self.run_query('Образование участка')
        self.assertEqual(r['status'],'error')
        class Duplicate(DemoModel):
            async def classify(self,q,intake=None):
                item={'task_id':'a','function_id':'legal_help','formulation':q,'scope':'general'}
                return {'tasks':[item,item]}
        r=asyncio.run(LegalPipeline(self.root,Duplicate(),demo=True).run('Образование участка',self.intake))
        self.assertEqual(r['status'],'error')

    def test_model_references_in_answer_or_limitations_never_reach_user(self):
        for field in ('answer','limitations'):
            for text in ('Согласно статье 12 Земельного кодекса РФ.', 'Подробнее https://example.org/demo',
                         'Ответ [1].', 'Основание: № 217-ФЗ.', 'См. ст. 12.', 'В соответствии с ГПК РФ.', 'Согласно пункту 2 указанной нормы.', 'Согласно ГК РФ.', 'Согласно Федеральному закону о садоводстве.', 'См. закон о садоводстве.', 'Основание — Закон Российской Федерации о приватизации.', 'Согласно Гражданскому кодексу.'):
                class ReferencingModel(DemoModel):
                    async def answer(self,**kwargs):
                        result={'answer':'Общие условия зависят от обстоятельств.','citations':[kwargs['fragments'][0]['id']],'limitations':[]}
                        result[field]=text if field=='answer' else [text]
                        return result
                with self.subTest(field=field,text=text):
                    r=asyncio.run(LegalPipeline(self.root,ReferencingModel(),demo=True).run('Образование участка',self.intake))
                    self.assertEqual(r['status'],'error')
                    self.assertNotIn(text,r['answer'])

    def test_irrelevant_retrieved_context_can_produce_insufficient_evidence(self):
        class NoEvidence(DemoModel):
            async def answer(self,**kwargs):
                return {'status':'insufficient_sources','answer':'Нельзя подтверждать требование по этим материалам.','citations':[],'limitations':[]}
        r=asyncio.run(LegalPipeline(self.root,NoEvidence(),demo=True).run('Образование участка',self.intake))
        self.assertEqual(r['status'],'insufficient_sources')
        self.assertNotIn('Нельзя подтверждать требование',r['answer'])
