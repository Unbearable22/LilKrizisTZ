import asyncio
import time
import unittest
from unittest.mock import patch
from land_assistant.legal import trusted_http as h
from land_assistant.legal.trusted_sources import validate_source_url
from land_assistant.legal.consultant_types import SourceError

class TrustedHTTPTests(unittest.TestCase):
 def test_url_policy(self):
  self.assertEqual(validate_source_url('https://www.consultant.ru/document/cons_doc_LAW_1/').publisher,'КонсультантПлюс')
  for url in ['http://www.consultant.ru/document/cons_doc_LAW_1/','https://www.consultant.ru.evil.test/document/cons_doc_LAW_1/','https://x@www.consultant.ru/document/cons_doc_LAW_1/','https://www.consultant.ru:444/document/cons_doc_LAW_1/','https://www.consultant.ru/document/../secret','https://127.0.0.1/','https://www.consultant.ru/document/cons_doc_LAW_1/?q=secret']:
   with self.subTest(url=url),self.assertRaises(SourceError):validate_source_url(url)
 def test_private_dns_answers_rejected(self):
  for ip in ['127.0.0.1','10.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1']:
   with patch.object(h.socket,'getaddrinfo',return_value=[(2,1,6,'',(ip,443))]),self.assertRaises(SourceError):h.resolve_public('www.consultant.ru')
 def test_redirect_is_revalidated_and_rate_limit_not_retried(self):
  with patch.object(h,'resolve_public',return_value='93.184.216.34'),patch.object(h,'request_once',return_value=(302,{'location':'https://127.0.0.1/'},b'')) as request:
   with self.assertRaises(SourceError):asyncio.run(h.fetch_document('https://www.consultant.ru/document/cons_doc_LAW_1/',deadline=time.monotonic()+10))
   self.assertEqual(request.call_count,1)
  with patch.object(h,'resolve_public',return_value='93.184.216.34'),patch.object(h,'request_once',return_value=(429,{},b'')) as request:
   with self.assertRaises(SourceError) as caught:asyncio.run(h.fetch_document('https://www.consultant.ru/document/cons_doc_LAW_1/',deadline=time.monotonic()+10))
   self.assertEqual(caught.exception.code,'source_rate_limit');self.assertEqual(request.call_count,1)
 def test_connection_pins_resolved_ip_and_preserves_tls_hostname(self):
  with patch.object(h.socket,'create_connection') as connect,patch.object(h.ssl,'create_default_context') as context:
   connection=h.PinnedHTTPS('www.consultant.ru','93.184.216.34',timeout=1);connection.connect()
   self.assertEqual(connect.call_args.args[0],('93.184.216.34',443))
   self.assertEqual(context.return_value.wrap_socket.call_args.kwargs['server_hostname'],'www.consultant.ru')
 def test_body_stream_size_limit(self):
  with patch.object(h,'PinnedHTTPS') as connection:
   response=connection.return_value.getresponse.return_value;response.status=200;response.getheaders.return_value=[('Content-Type','text/html')];response.read.return_value=b'x'*(2*1024*1024+1)
   with self.assertRaises(SourceError) as caught:h.request_once('https://www.consultant.ru/document/cons_doc_LAW_1/','93.184.216.34',1)
   self.assertEqual(caught.exception.code,'source_size_limit')
 def test_existing_consultant_reader_uses_pinned_transport(self):
  from land_assistant.legal.consultant_http import ConsultantHTTP
  from land_assistant.legal.consultant_types import RequestBudget
  from land_assistant.legal.trusted_sources import FetchedDocument
  with patch('land_assistant.legal.trusted_http.fetch_document',return_value=FetchedDocument('https://www.consultant.ru/document/cons_doc_LAW_1/','text/html',b'ok','2026-11-02T10:00:00+00:00')) as fetch:
   result=asyncio.run(ConsultantHTTP(pace=0).fetch('https://www.consultant.ru/document/cons_doc_LAW_1/',budget=RequestBudget()))
   self.assertEqual(result.body,'ok');fetch.assert_called_once()
