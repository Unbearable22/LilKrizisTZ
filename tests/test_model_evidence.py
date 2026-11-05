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
 def test_optional_reasoning_budget_applies_only_to_verifier(self):
  import os,httpx,json
  with patch.dict(os.environ,{'LLM_URL':'https://fixture.invalid','LLM_MODEL':'answer-model','LLM_VERIFIER_REASONING_EFFORT':'low'},clear=True):
   settings=Settings.from_env()
  model=LiveModel(settings);real=httpx.AsyncClient;payloads=[]
  def respond(request):
   payloads.append(json.loads(request.content));return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]})
  with patch('land_assistant.legal.model.httpx.AsyncClient',side_effect=lambda **kw:real(transport=httpx.MockTransport(respond),**kw)):
   for stage in ('classify','answer','verify'):asyncio.run(model._json([{'role':'system','content':'JSON'}],stage=stage))
  self.assertNotIn('reasoning_effort',payloads[0]);self.assertNotIn('reasoning_effort',payloads[1]);self.assertEqual(payloads[2].get('reasoning_effort'),'low')
 def test_default_verifier_does_not_send_reasoning_parameter(self):
  import httpx,json
  model=LiveModel(Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture'));real=httpx.AsyncClient;payloads=[]
  def respond(request):
   payloads.append(json.loads(request.content));return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]})
  with patch('land_assistant.legal.model.httpx.AsyncClient',side_effect=lambda **kw:real(transport=httpx.MockTransport(respond),**kw)):
   asyncio.run(model._json([{'role':'system','content':'JSON'}],stage='verify'))
  self.assertNotIn('reasoning_effort',payloads[0])
 def test_invalid_reasoning_budget_is_rejected_before_request(self):
  import os
  with patch.dict(os.environ,{'LLM_VERIFIER_REASONING_EFFORT':'arbitrary'},clear=True):
   with self.assertRaisesRegex(ValueError,'LLM_VERIFIER_REASONING_EFFORT'):Settings.from_env()
 def test_answer_uses_short_handles_and_restores_only_reference_fields(self):
  import json
  model=LiveModel(Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture'))
  fid='idx_27b6c30abdcc8e16:8e958715b563e23e:0';question=fid
  reply={'answer':'1','citations':['1','9'],'scenarios':[{'condition':'1','outcome':'1','citations':['1']}],'legal_bases':[{'fragment_id':'1','explanation':'1'}]}
  with patch.object(model,'_json',AsyncMock(return_value=reply)) as call:
   result=asyncio.run(model.answer(original_question=question,formulation='1',intake={},prompt='Правила',fragments=[{'id':fid,'text':'Подтверждённый текст.'}]))
  payload=json.loads(call.call_args.args[0][1]['content'])
  self.assertEqual(payload['fragments'][0]['id'],'1');self.assertEqual(payload['original_question'],question)
  self.assertEqual(result['citations'],[fid,'9']);self.assertEqual(result['scenarios'][0]['citations'],[fid]);self.assertEqual(result['legal_bases'][0]['fragment_id'],fid)
  self.assertEqual(result['answer'],'1');self.assertEqual(result['scenarios'][0]['outcome'],'1');self.assertEqual(result['legal_bases'][0]['explanation'],'1')
 def test_grounding_repair_uses_same_handle_contract_without_changing_quotes(self):
  import json
  model=LiveModel(Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture'));fid='long-source-id'
  draft={'answer':'1','citations':[fid],'claims':[{'section':'answer','evidence_ids':[fid],'anchors':[{'fragment_id':fid,'quote':fid}]}]}
  for method in (model.rewrite_answer,model.repair_grounding):
   with patch.object(model,'_json',AsyncMock(return_value={'citations':['1']})) as call:
    result=asyncio.run(method(draft=draft,original_question='1',formulation='Задача',intake={},prompt='Правила',fragments=[{'id':fid,'text':fid}]))
   payload=json.loads(call.call_args.args[0][1]['content']);self.assertEqual(payload['draft']['citations'],['1']);self.assertEqual(payload['draft']['claims'][0]['anchors'][0]['quote'],fid);self.assertEqual(result['citations'],[fid])
  self.assertEqual(draft['citations'],[fid])
 def test_verifier_receives_snapshot_date_instead_of_assuming_current_edition(self):
  model=LiveModel(Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture'))
  draft={'answer':'Общий порядок.','citations':['f'],'status':'answered'}
  with patch.object(model,'_json',AsyncMock(return_value={'supported':True})) as call:
   asyncio.run(model.verify_evidence(result=draft,fragments=[{'id':'f','text':'Сохранённое нормативное положение.','snapshot_as_of':'2026-10-22','last_checked_at':'2026-10-22'}]))
  import json
  payload=json.loads(call.call_args.args[0][-1]['content'])
  self.assertEqual(payload['fragments'][0]['snapshot_as_of'],'2026-10-22')
  self.assertIn('локальные снимки',call.call_args.args[0][0]['content'])
