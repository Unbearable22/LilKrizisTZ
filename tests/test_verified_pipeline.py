import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from land_assistant.legal.pipeline import LegalPipeline
from land_assistant.legal.model import DemoModel
from land_assistant.legal.consultant_types import RequestBudget
class VerifiedPipelineTests(unittest.TestCase):
 def test_general_topic_can_use_fallback(self):
  pipeline=LegalPipeline(Path('knowledge'),DemoModel(),False)
  task={'function_id':'general_legal_help','legal_topic':'consumer','formulation':'Неисправный телефон без чека'}
  with patch('land_assistant.legal.pipeline.ConsultantLegalMCP') as client:
   client.return_value.context=AsyncMock(return_value={'fragments':[{'id':'found'}],'trace':[]})
   result=asyncio.run(pipeline.fallback_context(task,budget=RequestBudget(),as_of_date='2026-11-02'))
  self.assertTrue(result['fragments']);self.assertTrue(client.return_value.context.call_args.kwargs['fallback'])
 def test_claim_check_failure_does_not_publish_answer(self):
  class Model(DemoModel):
   require_grounded_claims=True
   async def verify_evidence(self,**kw):return False
   async def classify(self,*a,**kw):return {'tasks':[{'task_id':'x','function_id':'general_legal_help','formulation':'зарплата','legal_topic':'labor','scope':'general'}]}
  p=LegalPipeline('knowledge',Model(),False)
  with patch.object(p,'context_for_task',AsyncMock(return_value={'prompt':'Правила','fragments':[{'id':'known','title':'Акт','citation':'Статья 1','text':'Оплата труда предусмотрена законом.','demo':False}],'trace':[]})):
   result=asyncio.run(p.run('Не платят зарплату',{}))
  self.assertEqual(result['status'],'error')
 def test_local_reads_share_global_eight_document_budget(self):
  p=LegalPipeline('knowledge',DemoModel(),False)
  task={'function_id':'legal_help','legal_topic':'land','formulation':'образование участка'}
  budget=RequestBudget(articles_left=1)
  with patch('land_assistant.legal.pipeline.LocalLegalMCP') as local:
   local.return_value.context=AsyncMock(return_value={'prompt':'Правила','trace':[],'fragments':[{'id':'a','text':'Первый'},{'id':'b','text':'Второй'}]})
   result=asyncio.run(p.context_for_task(task,budget=budget,as_of_date=__import__('datetime').datetime.now(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()))
  self.assertEqual(len(result['fragments']),1);self.assertEqual(budget.articles_left,0)
