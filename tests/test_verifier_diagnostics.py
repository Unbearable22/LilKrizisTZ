import asyncio,json,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from land_assistant.config import Settings
from scripts.diagnose_verifier import measure

class VerifierDiagnosticsTests(unittest.TestCase):
 def test_stream_metrics_keep_usage_and_request_id_without_content_or_secrets(self):
  settings=Settings(Path('data'),llm_url='https://fixture.invalid',llm_key='secret-key',llm_model='fixture');real=httpx.AsyncClient;observed=[]
  def respond(request):
   observed.append(json.loads(request.content))
   chunks=[{'choices':[{'delta':{'reasoning_content':'private reasoning'}}]}, {'choices':[{'delta':{'content':'{"supported":false,"issues":["private legal text"],"supported_sections":["scenario:0"]}'},'finish_reason':'stop'}]}, {'choices':[],'usage':{'prompt_tokens':8,'completion_tokens':4,'total_tokens':12,'private':'secret'}}]
   return httpx.Response(200,headers={'x-request-id':'safe-request_123'},text=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n')
  with patch('scripts.diagnose_verifier.httpx.AsyncClient',side_effect=lambda **kw:real(transport=httpx.MockTransport(respond),**kw)):
   row=asyncio.run(measure(settings,[{'role':'user','content':'private question'}],model='fixture',effort='low',timeout=5))
  self.assertTrue(row['json_object']);self.assertFalse(row['supported']);self.assertEqual(row['supported_section_count'],1);self.assertEqual(row['usage']['total_tokens'],12);self.assertEqual(row['request_id'],'safe-request_123')
  self.assertEqual(observed[0]['reasoning_effort'],'low');self.assertNotIn('private',json.dumps(row));self.assertNotIn('secret',json.dumps(row))
 def test_incomplete_stream_never_counts_as_completed_verdict(self):
  settings=Settings(Path('data'),llm_url='https://fixture.invalid',llm_model='fixture');real=httpx.AsyncClient;observed=[]
  def respond(request):
   observed.append(json.loads(request.content))
   return httpx.Response(200,headers={'x-request-id':'unsafe value'},text='data: {"choices":[{"delta":{"content":"{\\\"supported\\\":true}"}}]}\n\n')
  with patch('scripts.diagnose_verifier.httpx.AsyncClient',side_effect=lambda **kw:real(transport=httpx.MockTransport(respond),**kw)):
   row=asyncio.run(measure(settings,[],model='fixture',effort='',timeout=5))
  self.assertEqual(row['error_type'],'incomplete_stream');self.assertNotIn('supported',row);self.assertNotIn('request_id',row);self.assertNotIn('reasoning_effort',observed[0])
