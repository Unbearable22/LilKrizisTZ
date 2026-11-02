import asyncio
from pathlib import Path
import unittest
from unittest.mock import AsyncMock,patch
from land_assistant.config import Settings
from land_assistant.legal.model import LiveModel
class ModelEvidenceTests(unittest.TestCase):
 def test_separate_verifier_attaches_anchors_without_bloating_answer_generation(self):
  model=LiveModel(Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture'))
  draft={'answer':'Общий порядок.','citations':['f'],'status':'answered'}
  claims=[{'section':'answer','evidence_ids':['f'],'anchors':[{'fragment_id':'f','quote':'Потребитель вправе потребовать возврата суммы'}]}]
  with patch.object(model,'_json',AsyncMock(return_value={'supported':True,'claims':[{'section':'answer','evidence_ids':['1'],'anchors':[{'fragment_id':'1','quote':'Потребитель вправе потребовать возврата суммы'}]}]})) as call:
   supported=asyncio.run(model.verify_evidence(result=draft,fragments=[{'id':'f','text':'Потребитель вправе потребовать возврата суммы.'}],original_question='Возврат товара',formulation='Права потребителя'))
  self.assertTrue(supported);self.assertEqual(draft['claims'],claims);self.assertEqual(call.call_args.kwargs['stage'],'verify')
  payload=__import__('json').loads(call.call_args.args[0][1]['content']);self.assertEqual(payload['fragments'][0]['id'],'1')
  with patch.object(model,'_json',AsyncMock(return_value={})) as call:
   asyncio.run(model.answer(original_question='Вопрос',formulation='Задача',intake={},prompt='Правила',fragments=[]))
  self.assertNotIn('обязательное поле',call.call_args.args[0][0]['content'])
 def test_failed_verifier_gives_bounded_feedback_for_content_repair(self):
  model=LiveModel(Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture'));draft={'answer':'Спорный вывод.'}
  with patch.object(model,'_json',AsyncMock(return_value={'supported':False,'issues':['Не подтверждено основание изъятия.']})):
   self.assertFalse(asyncio.run(model.verify_evidence(result=draft,fragments=[])))
  self.assertEqual(draft['_grounding_issues'],['Не подтверждено основание изъятия.'])
 def test_json_mode_verifier_explicitly_requests_json(self):
  model=LiveModel(Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture'))
  with patch.object(model,'_json',AsyncMock(return_value={'supported':False})) as call:
   asyncio.run(model.verify_evidence(result={'answer':'Общий ответ.'},fragments=[]))
  self.assertIn('json',call.call_args.args[0][0]['content'].casefold())
 def test_verifier_has_completion_room_and_distinguishes_provider_truncation(self):
  import httpx,json
  from land_assistant.legal.errors import LegalError
  model=LiveModel(Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture'));real=httpx.AsyncClient;observed=[]
  def respond(request):
   observed.append(json.loads(request.content)['max_tokens'])
   return httpx.Response(502,json={'error':{'code':'incomplete_upstream_stream','message':'Модель исчерпала лимит вывода, не завершив ответ.'}})
  with patch('land_assistant.legal.model.httpx.AsyncClient',side_effect=lambda **kw:real(transport=httpx.MockTransport(respond),**kw)):
   with self.assertRaises(LegalError) as caught:asyncio.run(model.verify_evidence(result={},fragments=[]))
  self.assertEqual(observed,[6144]);self.assertEqual(caught.exception.code,'llm_truncated')
 def test_separate_verifier_model_is_configurable(self):
  import httpx,json
  settings=Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='answer-model');settings.llm_verifier_model='checker-model';model=LiveModel(settings);real=httpx.AsyncClient;models=[]
  def respond(request):
   models.append(json.loads(request.content)['model']);return httpx.Response(200,json={'choices':[{'message':{'content':'{"supported":false}'}}]})
  with patch('land_assistant.legal.model.httpx.AsyncClient',side_effect=lambda **kw:real(transport=httpx.MockTransport(respond),**kw)):
   asyncio.run(model.verify_evidence(result={},fragments=[]))
  self.assertEqual(models,['checker-model'])
 def test_verifier_receives_known_client_facts_without_full_history(self):
  model=LiveModel(Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture'))
  with patch.object(model,'_json',AsyncMock(return_value={'supported':False})) as call:
   asyncio.run(model.verify_evidence(result={},fragments=[],intake={'amount':'10000'}))
  payload=__import__('json').loads(call.call_args.args[0][1]['content']);self.assertEqual(payload['intake'],{'amount':'10000'});self.assertNotIn('history',payload)
