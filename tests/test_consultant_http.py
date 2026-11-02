import asyncio,unittest,httpx,time
from land_assistant.legal.consultant_http import ConsultantHTTP,allowed_url
from land_assistant.legal.consultant_types import RequestBudget,SourceError
ROOT='https://www.consultant.ru/document/cons_doc_LAW_34154/'
class HTTPTests(unittest.TestCase):
 def test_urls_reject_other_hosts_ports_and_paths(self):
  for url in ['http://www.consultant.ru/document/cons_doc_LAW_1/','https://consultant.ru.evil/a','https://127.0.0.1/','https://www.consultant.ru:8443/document/cons_doc_LAW_1/','https://www.consultant.ru/document/../admin','https://user@consultant.ru/document/cons_doc_LAW_1/']:
   with self.subTest(url=url),self.assertRaises(SourceError):allowed_url(url)
  self.assertEqual(allowed_url(ROOT),ROOT)
 def test_foreign_redirect_is_not_requested(self):
  calls=[]
  def respond(req):calls.append(str(req.url));return httpx.Response(302,headers={'location':'https://evil.invalid'})
  async def run():
   with self.assertRaises(SourceError):await ConsultantHTTP(transport=httpx.MockTransport(respond),pace=0).fetch(ROOT,budget=RequestBudget())
  asyncio.run(run());self.assertEqual(len(calls),1)
 def test_large_body_and_rate_limit(self):
  async def run():
   for code,body,expected in [(200,b'x'*(2*1024*1024+1),'source_size_limit'),(429,b'','source_rate_limit'),(403,b'','source_access_restricted')]:
    http=ConsultantHTTP(transport=httpx.MockTransport(lambda req:httpx.Response(code,content=body)),pace=0);budget=RequestBudget()
    with self.assertRaises(SourceError) as err:await http.fetch(ROOT,budget=budget)
    self.assertEqual(err.exception.code,expected)
    if code==429:
     with self.assertRaises(SourceError):await http.fetch(ROOT,budget=budget)
  asyncio.run(run())
 def test_cancel_propagates(self):
  async def respond(req):raise asyncio.CancelledError()
  async def run():
   with self.assertRaises(asyncio.CancelledError):await ConsultantHTTP(transport=httpx.MockTransport(respond),pace=0).fetch(ROOT,budget=RequestBudget())
  asyncio.run(run())
 def test_pacing_serializes_request_starts(self):
  starts=[]
  def respond(req):starts.append(time.monotonic());return httpx.Response(200,text='ok')
  async def run():
   http=ConsultantHTTP(transport=httpx.MockTransport(respond),pace=.02);budget=RequestBudget()
   await http.fetch(ROOT,budget=budget);await http.fetch(ROOT,budget=budget)
  asyncio.run(run());self.assertGreaterEqual(starts[1]-starts[0],.019);self.assertEqual(ConsultantHTTP().pace,1)
