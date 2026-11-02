import asyncio,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from test_legal_knowledge import make_library
from land_assistant.legal.pipeline import LegalPipeline
from land_assistant.legal.model import DemoModel
from land_assistant.legal.consultant_types import SourceError
class GeneralPipelineTests(unittest.TestCase):
 def test_mixed_tasks_keep_checked_answer_when_second_source_fails(self):
  class Model(DemoModel):
   async def classify(self,*args,**kwargs):return {'tasks':[{'task_id':'a','function_id':'legal_help','formulation':'образование участка','scope':'general'},{'task_id':'b','function_id':'general_legal_help','formulation':'наследство','scope':'individual','legal_topic':'inheritance'}]}
  with tempfile.TemporaryDirectory() as tmp:
   p=LegalPipeline(make_library(tmp),Model(),True)
   with patch.object(p,'context_for_task',side_effect=[{'prompt':'Правила','fragments':[{'id':'known','title':'Учебный акт','citation':'Статья 1','demo':True,'text':'Образование участка'}],'trace':[]},SourceError('source_unavailable')]):r=asyncio.run(p.run('Два вопроса',{}))
   self.assertEqual(r['status'],'partial_answer');self.assertIn('ДЕМОНСТРАЦИЯ',r['answer']);self.assertEqual(r['task_outcomes'][1]['status'],'error');self.assertIn('наследство',r['task_outcomes'][1]['summary'])
 def test_general_route_passes_only_sanitized_query_to_mcp(self):
  class Model(DemoModel):
   async def classify(self,*args,**kwargs):return {'tasks':[{'task_id':'a','function_id':'general_legal_help','formulation':'Иван Иванов: зарплата не выплачена','scope':'general','legal_topic':'labor'}]}
  with tempfile.TemporaryDirectory() as tmp:
   p=LegalPipeline(make_library(tmp),Model(),False)
   with patch('land_assistant.legal.pipeline.ConsultantLegalMCP') as m:
    m.return_value.context=AsyncMock(return_value={'prompt':'Правила','fragments':[{'id':'known','title':'Трудовой кодекс Российской Федерации','citation':'Статья 136','demo':False,'text':'Оплата труда'}],'trace':[],'source_checked_at':'2026-10-22T00:00:00+00:00'})
    r=asyncio.run(p.run('Не платят зарплату',{'event_date':'не помню'}))
   self.assertEqual(r['status'],'answered');q=m.return_value.context.call_args.args[0];self.assertNotIn('Иван',q);self.assertTrue(r['source_checked_at'])
 def test_ready_question_does_not_ask_client_to_repeat_situation(self):
  class Model(DemoModel):
   async def answer(self,**kwargs):
    r=await super().answer(**kwargs);r['missing_fields']=['situation','goal','documents'];return r
  with tempfile.TemporaryDirectory() as tmp:
   r=asyncio.run(LegalPipeline(make_library(tmp),Model(),True).run('Проверьте мой участок: образование участка',{}))
  self.assertEqual(r['status'],'partial_answer');self.assertEqual([f['key'] for f in r['missing_fields']],['documents'])

 def test_deadline_identifies_unfinished_subquestion(self):
  class Model(DemoModel):
   async def classify(self,*args,**kwargs):return {'tasks':[{'task_id':'a','function_id':'legal_help','formulation':'образование участка','scope':'general'},{'task_id':'b','function_id':'general_legal_help','formulation':'наследство','scope':'individual','legal_topic':'inheritance'}]}
  async def run(tmp):
   p=LegalPipeline(make_library(tmp),Model(),True);calls=0
   async def context(*args,**kwargs):
    nonlocal calls
    calls+=1
    if calls==2:await asyncio.Event().wait()
    return {'prompt':'Правила','fragments':[{'id':'known','title':'Учебный акт','citation':'Статья 1','demo':True,'text':'Образование участка'}],'trace':[]}
   real_timeout=asyncio.timeout
   with patch.object(p,'context_for_task',side_effect=context),patch('land_assistant.legal.pipeline.asyncio.timeout',side_effect=lambda _:real_timeout(.1)):
    return await p.run('Два вопроса',{})
  with tempfile.TemporaryDirectory() as tmp:r=asyncio.run(run(tmp))
  self.assertEqual(r['status'],'partial_answer');self.assertEqual(len(r['task_outcomes']),2);self.assertIn('наследство',r['task_outcomes'][1]['summary'])

class PublicFallbackPipelineTests(unittest.TestCase):
 def test_missing_material_uses_one_verified_fallback(self):
  class Model(DemoModel):
   async def classify(self,*a,**kw):return {'tasks':[{'task_id':'tax','function_id':'general_legal_help','formulation':'Налог при продаже участка','scope':'general','legal_topic':'tax'}]}
   async def answer(self,**kw):
    return {'status':'answered','answer':'Возможность освобождения зависит от срока владения.','citations':['official'],'limitations':[]}
  with tempfile.TemporaryDirectory() as tmp:
   p=LegalPipeline(make_library(tmp),Model(),False)
   fragment={'id':'official','title':'Разъяснение ФНС','citation':'Разъяснение','demo':False,'text':'Продажа участка облагается налогом с учётом предусмотренных освобождений.'}
   with patch.object(p,'context_for_task',new=AsyncMock(return_value={'prompt':'Правила','fragments':[],'trace':[]})),patch.object(p,'fallback_context',new=AsyncMock(return_value={'prompt':'Правила','fragments':[fragment],'trace':['public.fallback']})) as fallback:
    r=asyncio.run(p.run('Налог при продаже участка',{}))
   self.assertEqual(r['status'],'answered');self.assertEqual(fallback.await_count,1)

 def test_insufficient_answer_retries_once_with_verified_supplement(self):
  class Model(DemoModel):
   calls=0
   async def classify(self,*a,**kw):return {'tasks':[{'task_id':'tax','function_id':'general_legal_help','formulation':'Налог при продаже участка','scope':'general','legal_topic':'tax'}]}
   async def answer(self,**kw):
    self.calls+=1
    if self.calls==1:return {'status':'insufficient_sources','answer':'Недостаточно норм.'}
    return {'status':'answered','answer':'Общие условия зависят от срока владения.','citations':['official'],'limitations':[]}
  with tempfile.TemporaryDirectory() as tmp:
   m=Model();p=LegalPipeline(make_library(tmp),m,False);f={'id':'known','title':'Прочитанный акт','citation':'Статья 1','demo':False,'text':'Исходный фрагмент.'}
   with patch.object(p,'context_for_task',new=AsyncMock(return_value={'prompt':'Правила','fragments':[f],'trace':[]})),patch.object(p,'fallback_context',new=AsyncMock(return_value={'prompt':'Правила','fragments':[{**f,'id':'official'}],'trace':[]})) as fallback:
    r=asyncio.run(p.run('Налог при продаже участка',{}))
   self.assertEqual(r['status'],'answered');self.assertEqual(m.calls,2);self.assertEqual(fallback.await_count,1)

 def test_source_error_can_use_verified_official_fallback(self):
  class Model(DemoModel):
   async def classify(self,*a,**kw):return {'tasks':[{'task_id':'tax','function_id':'general_legal_help','formulation':'Налог при продаже участка','scope':'general','legal_topic':'tax'}]}
   async def answer(self,**kw):return {'status':'answered','answer':'Налог зависит от условий продажи.','citations':['official'],'limitations':[]}
  with tempfile.TemporaryDirectory() as tmp:
   p=LegalPipeline(make_library(tmp),Model(),False)
   f={'id':'official','title':'Официальное разъяснение','citation':'Разъяснение','demo':False,'text':'Проверенный текст.'}
   with patch.object(p,'context_for_task',new=AsyncMock(side_effect=SourceError('source_unavailable'))),patch.object(p,'fallback_context',new=AsyncMock(return_value={'prompt':'Правила','fragments':[f],'trace':[]})):
    r=asyncio.run(p.run('Налог при продаже участка',{}))
   self.assertEqual(r['status'],'answered')

 def test_checked_partial_survives_fallback_model_failure(self):
  from land_assistant.legal.errors import LegalError
  class Model(DemoModel):
   calls=0
   async def classify(self,*a,**kw):return {'tasks':[{'task_id':'tax','function_id':'general_legal_help','formulation':'Налог при продаже участка','scope':'individual','legal_topic':'tax'}]}
   async def answer(self,**kw):
    self.calls+=1
    if self.calls>1:raise LegalError('llm_http',http_status=502)
    return {'status':'partial_answer','answer':'Проверенная общая часть.','citations':['known'],'limitations':[],'missing_fields':[],'scenarios':[{'condition':'срок подтверждён','outcome':'можно проверить освобождение','citations':['known']}]}
  with tempfile.TemporaryDirectory() as tmp:
   p=LegalPipeline(make_library(tmp),Model(),False);f={'id':'known','title':'Прочитанный акт','citation':'Статья 1','demo':False,'text':'Проверенное правило.'}
   with patch.object(p,'context_for_task',new=AsyncMock(return_value={'prompt':'Правила','fragments':[f],'trace':[]})),patch.object(p,'fallback_context',new=AsyncMock(return_value={'prompt':'Правила','fragments':[{**f,'id':'official'}],'trace':[]})):
    r=asyncio.run(p.run('Налог при продаже участка',{}))
   self.assertEqual(r['status'],'partial_answer');self.assertIn('Проверенная общая часть',r['answer']);self.assertTrue(any('сохранён' in v for v in r['limitations']))
