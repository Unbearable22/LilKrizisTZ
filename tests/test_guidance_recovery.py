import asyncio,tempfile,unittest
from pathlib import Path
from land_assistant.legal.pipeline import LegalPipeline
from land_assistant.legal.errors import LegalError
from land_assistant.legal.answer_evidence import prepare_claims

class Model:
 require_grounded_claims=True
 async def classify(self,*a,**kw):
  return {'tasks':[{'task_id':'t1','function_id':'general_legal_help','legal_topic':'civil','formulation':'Возврат займа: переписка и перевод денег','scope':'general'}]}
 async def answer(self,**kw):
  r={'status':'answered','answer':'Вам гарантировано взыскание всей суммы.','citations':['f1'],'limitations':[]}
  r['claims']=prepare_claims(r,kw['fragments']);return r
 async def verify_evidence(self,**kw):return False

class Pipeline(LegalPipeline):
 async def context_for_task(self,*a,**kw):
  return {'prompt':'Правила','trace':[],'fragments':[{'id':'f1','text':'Возврат денег зависит от условий договора.','title':'Текст','citation':'','version':'current','demo':False}]}
 async def fallback_context(self,*a,**kw):return {'prompt':'','trace':[],'fragments':[]}

class GuidanceRecoveryTests(unittest.TestCase):
 def test_rejected_answer_returns_guidance_without_unchecked_draft_or_sources(self):
  r=asyncio.run(Pipeline(Path('knowledge'),Model()).run('Дал в долг. Что делать?',{}))
  self.assertEqual(r['status'],'partial_answer');self.assertEqual(r['response_kind'],'general_guidance')
  self.assertIn('переписк',r['answer']);self.assertNotIn('гарантировано',r['answer'])
  self.assertEqual(r['sources'],[]);self.assertEqual(r['legal_bases'],[])
 def test_verifier_timeout_returns_useful_guidance(self):
  class Slow(Model):
   async def verify_evidence(self,**kw):raise TimeoutError()
  r=asyncio.run(Pipeline(Path('knowledge'),Slow()).run('Не возвращают долг',{}))
  self.assertEqual(r['response_kind'],'general_guidance');self.assertIn('провер',r['answer'].lower())
 def test_empty_context_returns_guidance_instead_of_bare_refusal(self):
  class Empty(Pipeline):
   async def context_for_task(self,*a,**kw):return {'prompt':'','trace':[],'fragments':[]}
  r=asyncio.run(Empty(Path('knowledge'),Model()).run('Возврат долга',{}))
  self.assertEqual(r['response_kind'],'general_guidance');self.assertTrue(r['answer'])
 def test_invalid_input_and_cancellation_do_not_become_guidance(self):
  p=Pipeline(Path('knowledge'),Model());self.assertEqual(asyncio.run(p.run('',{}))['status'],'invalid_request')
  class Cancel(Model):
   async def verify_evidence(self,**kw):raise asyncio.CancelledError()
  with self.assertRaises(asyncio.CancelledError):asyncio.run(Pipeline(Path('knowledge'),Cancel()).run('Возврат долга',{}))
 def test_verifier_has_its_own_configurable_http_timeout(self):
  import json,httpx
  from unittest.mock import patch
  from land_assistant.config import Settings
  from land_assistant.legal.model import LiveModel
  settings=Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture',llm_answer_timeout=10,llm_verify_timeout=72)
  seen=[]
  def handle(request):
   seen.append(request.extensions['timeout']['read'])
   return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
  real=httpx.AsyncClient
  with patch('land_assistant.legal.model.httpx.AsyncClient',side_effect=lambda **kw:real(transport=httpx.MockTransport(handle),**kw)):
   asyncio.run(LiveModel(settings)._json([{'role':'user','content':'check'}],stage='verify'))
  self.assertEqual(seen,[72])
 def test_classification_timeout_still_gives_general_preparation_guidance(self):
  class NoPlan(Model):
   async def classify(self,*a,**kw):raise LegalError('llm_timeout')
  r=asyncio.run(Pipeline(Path('knowledge'),NoPlan()).run('Помогите с моей ситуацией',{}))
  self.assertEqual(r['response_kind'],'general_guidance');self.assertIn('последовательность',r['answer'])
