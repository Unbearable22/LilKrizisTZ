import json,unittest
from unittest.mock import patch
from subprocess import CompletedProcess,TimeoutExpired
from land_assistant.legal.speech import transcribe,SpeechError
class SpeechTests(unittest.TestCase):
 def test_rejects_empty_oversize_and_wrong_type_before_worker(self):
  for body,mime in [(b'', 'audio/webm'),(b'x'*(8*1024*1024+1),'audio/webm'),(b'x','text/plain')]:
   with self.subTest(mime=mime),patch('subprocess.run') as run,self.assertRaises(SpeechError):transcribe(body,mime)
   run.assert_not_called()
 def test_returns_text_without_writing_audio(self):
  with patch('land_assistant.legal.speech.available',return_value=True),patch('subprocess.run',return_value=CompletedProcess([],0,json.dumps({'text':'У меня есть участок'}).encode(),b'')) as run:
   self.assertEqual(transcribe(b'fake audio','audio/webm'),'У меня есть участок')
   self.assertEqual(run.call_args.kwargs['input'],b'fake audio');self.assertNotIn('LLM_API_KEY',run.call_args.kwargs['env'])
 def test_timeout_and_invalid_audio_are_safe_errors(self):
  for response in [TimeoutExpired('worker',90),CompletedProcess([],2,b'',b'secret')]:
   with patch('land_assistant.legal.speech.available',return_value=True),patch('subprocess.run',side_effect=response if isinstance(response,Exception) else None,return_value=response),self.assertRaises(SpeechError):transcribe(b'a','audio/ogg')

class SpeechHTTPTests(unittest.TestCase):
 def test_transcription_route_and_origin_validation(self):
  import threading,urllib.request,urllib.error
  from http.server import ThreadingHTTPServer
  from pathlib import Path
  from types import SimpleNamespace
  from land_assistant.legal.web import make_web_handler
  server=ThreadingHTTPServer(('127.0.0.1',0),make_web_handler(SimpleNamespace(demo=True),Path('groundAndLaw')))
  threading.Thread(target=server.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{server.server_port}/api/transcribe'
  try:
   with patch('land_assistant.legal.speech.transcribe',return_value='Тестовый вопрос') as stt:
    req=urllib.request.Request(url,data=b'audio',headers={'Content-Type':'audio/webm'})
    with urllib.request.urlopen(req) as r:self.assertEqual(json.load(r),{'text':'Тестовый вопрос'})
    self.assertEqual(stt.call_count,1)
    req=urllib.request.Request(url,data=b'audio',headers={'Content-Type':'audio/webm','Origin':'https://evil.example'})
    with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
    self.assertEqual(err.exception.code,403);err.exception.close();self.assertEqual(stt.call_count,1)
  finally:server.shutdown();server.server_close()
