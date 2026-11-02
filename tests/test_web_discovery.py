import asyncio,json,time,unittest
from unittest.mock import AsyncMock,patch
from urllib.parse import urlencode
from land_assistant.legal.web_discovery import discover_roots,parse_results,validate_search_url
from land_assistant.legal.consultant_types import RequestBudget,SourceError
from land_assistant.legal.trusted_sources import FetchedDocument,validate_source_url
class WebDiscoveryTests(unittest.TestCase):
 def test_only_public_document_candidates_are_returned_not_snippets_or_paid_links(self):
  html='<li class="search-results__item" data-avail="yes"><a class="search-results__link" href="/document/cons_doc_LAW_123/">Акт о паспорте</a><p>Сниппет не является нормой</p></li>'
  html+='<li class="search-results__item" data-avail="no"><a class="search-results__link" href="https://login.consultant.ru/link/">Закрытый</a></li>'
  html+='<a href="https://evil.invalid/document/cons_doc_LAW_4/">Подмена</a>'
  roots=parse_results({'ready':True,'results':html},'administrative')
  self.assertEqual(len(roots),1);self.assertEqual(roots[0]['url'],'https://www.consultant.ru/document/cons_doc_LAW_123/');self.assertNotIn('text',roots[0])
 def test_discovery_endpoint_cannot_become_evidence_or_arbitrary_query(self):
  url='https://www.consultant.ru/search/?'+urlencode({'q':'утрата паспорта'})
  validate_search_url(url)
  with self.assertRaises(SourceError):validate_source_url(url)
  for u in [url+'&extra=x',url.replace('www.consultant.ru','evil.invalid'),url.replace('https:','http:'),url.replace('/search/','/other/')]:
   with self.assertRaises(SourceError):validate_search_url(u)
 def test_search_consumes_shared_budget_and_pending_is_not_success(self):
  budget=RequestBudget();reply=FetchedDocument('https://www.consultant.ru/search/','application/json',b'{"ready":false}','2026-11-02T10:00:00+00:00')
  with patch('land_assistant.legal.web_discovery.fetch_document',AsyncMock(return_value=reply)) as fetch:
   with self.assertRaises(SourceError):asyncio.run(discover_roots('утрата паспорта','administrative',budget))
  self.assertEqual(budget.discovery_left,1);self.assertEqual(budget.documents_left,5);self.assertTrue(fetch.call_args.kwargs['discovery'])
 def test_pinned_transport_keeps_query_and_sets_native_search_header(self):
  from land_assistant.legal import trusted_http as h
  url='https://www.consultant.ru/search/?q=test'
  with patch.object(h,'PinnedHTTPS') as conn:
   response=conn.return_value.getresponse.return_value;response.status=200;response.getheaders.return_value=[];response.read.return_value=b''
   h.request_once(url,'93.184.216.34',1)
   args=conn.return_value.request.call_args;self.assertEqual(args.args[1],'/search/?q=test');self.assertEqual(args.kwargs['headers']['X-Requested-With'],'XMLHttpRequest')
