import unittest
from land_assistant.legal.public_sources import parse_fns,allowed_public_url
from land_assistant.legal.consultant_types import SourceError
class PublicSourcesTests(unittest.TestCase):
 def test_exact_url_allowlist(self):
  for u in ['https://www.nalog.gov.ru.evil.test/rn77/fl/pay_taxes/land/land_sell/','http://www.nalog.gov.ru/rn77/fl/pay_taxes/land/land_sell/','https://www.nalog.gov.ru/other/']:
   with self.assertRaises(SourceError):allowed_public_url(u)
 def test_page_must_have_known_heading_body_and_current_update(self):
  html='<h1>Я продал или собираюсь продать земельный участок</h1><div class="text_block"><p>Доходы от продажи земельных участков облагаются налогом на доходы физических лиц. Налоговая декларация представляется в установленный срок.</p></div>Дата обновления страницы 22.10.2026'
  r=parse_fns(html,'2026-10-22');self.assertIn('налог',r)
  for wrong in [html.replace('22.10.2026','22.10.2020'),html.replace('text_block','unknown'),html.replace('Доходы','CAPTCHA Доходы')]:
   with self.assertRaises(SourceError):parse_fns(wrong,'2026-10-22')
 def test_official_document_consumes_shared_read_budget(self):
  import asyncio
  from unittest.mock import patch
  from datetime import datetime
  from zoneinfo import ZoneInfo
  from land_assistant.legal.public_sources import official_fragments
  from land_assistant.legal.consultant_types import RequestBudget
  day=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat();budget=RequestBudget(articles_left=0)
  with patch('land_assistant.legal.trusted_http.fetch_document',side_effect=AssertionError('network read exceeds budget')) as fetch:
   with self.assertRaises(SourceError):asyncio.run(official_fragments('продажа недвижимости','tax',day,budget,None))
   fetch.assert_not_called()
