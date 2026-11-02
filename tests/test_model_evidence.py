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
