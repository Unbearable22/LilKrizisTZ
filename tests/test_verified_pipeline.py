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
 def test_identical_fallback_evidence_does_not_regenerate_answer(self):
  class Model(DemoModel):
   calls=0
   async def classify(self,*a,**kw):return {'tasks':[{'task_id':'x','function_id':'general_legal_help','formulation':'зарплата','legal_topic':'labor','scope':'individual'}]}
   async def answer(self,**kw):
    self.calls+=1
    return {'status':'partial_answer','answer':'Общий порядок.','citations':['known'],'limitations':['Связанные нормы не представлены.'],'missing_fields':[],'scenarios':[{'condition':'факт подтвердится','outcome':'можно уточнить порядок','citations':['known']}]}
  f={'id':'known','title':'Трудовой кодекс Российской Федерации','text':'Подтверждённая норма о выплате.','source_url':'https://www.consultant.ru/document/cons_doc_LAW_34683/','citation':'Статья 136','demo':False}
  context={'prompt':'Правила','fragments':[f],'trace':[]};model=Model();p=LegalPipeline('knowledge',model,False)
  with patch.object(p,'context_for_task',AsyncMock(return_value=context)),patch.object(p,'fallback_context',AsyncMock(return_value={**context,'fragments':[{**f,'id':'different_cache_id'}]})):
   result=asyncio.run(p.run('Не платят зарплату',{}))
  self.assertEqual(result['status'],'partial_answer');self.assertEqual(model.calls,1)
 def test_claim_sources_are_included_in_public_documents(self):
  class Model(DemoModel):
   async def classify(self,*a,**kw):return {'tasks':[{'task_id':'x','function_id':'general_legal_help','formulation':'зарплата','legal_topic':'labor','scope':'general'}]}
   async def answer(self,**kw):return {'status':'answered','answer':'Общий порядок.','citations':['a'],'limitations':[],'claims':[{'section':'answer','evidence_ids':['b'],'anchors':[{'fragment_id':'b','quote':'Подтверждённая норма о выплате'}]}]}
  def f(fid,doc):return {'id':fid,'title':'Акт','text':'Подтверждённая норма о выплате.','source_url':f'https://www.consultant.ru/document/cons_doc_LAW_{doc}/','citation':'Статья 136','demo':False,'last_checked_at':'2026-11-02T10:00:00+00:00'}
  p=LegalPipeline('knowledge',Model(),False)
  with patch.object(p,'context_for_task',AsyncMock(return_value={'prompt':'Правила','fragments':[f('a',1),f('b',2)],'trace':[]})):
   r=asyncio.run(p.run('Не платят зарплату',{}))
  self.assertEqual(len(r['evidence']),2);self.assertIn('x/answer',r['evidence'][1]['claim_ids'])
 def test_missing_facts_alone_do_not_trigger_source_regeneration(self):
  class Model(DemoModel):
   async def classify(self,*a,**kw):return {'tasks':[{'task_id':'x','function_id':'general_legal_help','formulation':'зарплата','legal_topic':'labor','scope':'individual'}]}
   async def answer(self,**kw):return {'status':'partial_answer','answer':'Общий порядок.','citations':['f'],'limitations':['Точная сумма задолженности неизвестна.'],'missing_fields':['amount'],'scenarios':[{'condition':'долг подтвердится','outcome':'можно уточнить сумму','citations':['f']}]}
  p=LegalPipeline('knowledge',Model(),False)
  with patch.object(p,'context_for_task',AsyncMock(return_value={'prompt':'Правила','fragments':[{'id':'f','title':'Прочитанный документ','text':'Норма об оплате труда.','demo':False}],'trace':[]})),patch.object(p,'fallback_context',AsyncMock(return_value={'fragments':[],'trace':[]})) as fallback:
   r=asyncio.run(p.run('Не платят зарплату',{}))
  self.assertEqual(r['status'],'partial_answer');fallback.assert_not_awaited()
