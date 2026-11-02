import asyncio,json,unittest,httpx
from unittest.mock import patch
from pathlib import Path
from land_assistant.config import Settings
from land_assistant.legal.model import LiveModel
class GeneralBudgetTests(unittest.TestCase):
 def test_richer_context_has_enough_completion_budget(self):
  settings=Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture');real=httpx.AsyncClient
  def reply(request):
   enough=json.loads(request.content)['max_tokens']>=6144
   return httpx.Response(200,json={'choices':[{'finish_reason':'stop' if enough else 'length','message':{'content':'{"status":"answered"}'}}]})
  with patch('land_assistant.legal.model.httpx.AsyncClient',side_effect=lambda **kw:real(transport=httpx.MockTransport(reply),**kw)):
   result=asyncio.run(LiveModel(settings).answer(original_question='Наследство',formulation='Наследство',intake={},prompt='Правила',fragments=[]))
  self.assertEqual(result['status'],'answered')
