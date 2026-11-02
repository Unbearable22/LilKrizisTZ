import asyncio
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from land_assistant.legal.source_discovery import VerifiedSourceLibrary
from land_assistant.legal.consultant_types import RequestBudget
from land_assistant.legal.source_documents import VerifiedDocument

class DiscoveryTests(unittest.TestCase):
 def test_cached_index_avoids_network_and_only_registered_ids_can_be_read(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=VerifiedSourceLibrary(Path('knowledge'),Path(tmp))
   now=datetime.now(timezone.utc).isoformat();day=datetime.now().date().isoformat()
   lib.index.upsert(VerifiedDocument('https://www.consultant.ru/document/cons_doc_LAW_305/','Права потребителя','КонсультантПлюс','normative_act','current','ред. от 01.01.2026',now,[{'text':'Потребитель при обнаружении недостатков товара вправе потребовать возврата суммы.','citation':'Статья 18'}]))
   with patch.object(lib.library,'search',side_effect=AssertionError('network not needed')):
    result=asyncio.run(lib.search('права потребителя при обнаружении недостатков товара','consumer',day,RequestBudget()))
   self.assertTrue(result);self.assertNotIn('text',result[0]);self.assertIn('недостатков',lib.read(result[0]['id'],day)['text'])
 def test_closed_query_has_no_personal_information_and_land_has_route(self):
  from land_assistant.legal.task_catalog import search_query
  q=search_query('Иванов участок 90:01:123 власти забрать изъятие дорога','land')
  self.assertNotIn('Иванов',q);self.assertNotIn('90:',q);self.assertIn('изъят',q)
  roots=__import__('json').loads(Path('knowledge/consultant/roots.json').read_text())['roots']
  self.assertTrue(any('land' in r['topics'] and r['enabled'] for r in roots))
 def test_deadline_only_index_cannot_satisfy_request_for_defect_rights(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=VerifiedSourceLibrary(Path('knowledge'),Path(tmp));now=datetime.now(timezone.utc).isoformat();day=datetime.now().date().isoformat()
   lib.index.upsert(VerifiedDocument('https://www.consultant.ru/document/cons_doc_LAW_305/','Закон о защите прав потребителей','КонсультантПлюс','normative_act','current','ред. от 01.01.2026',now,[{'text':'Сроки предъявления требований потребителем при обнаружении недостатков товара.','citation':'Статья 19'}]))
   with patch.object(lib.library,'search',return_value=[]) as search:
    asyncio.run(lib.search('права потребителя при обнаружении недостатков товара сроки предъявления требований','consumer',day,RequestBudget()))
   search.assert_called_once()
 def test_rights_article_number_accepts_heading_punctuation_not_subarticle(self):
  f={'citation':'Статья 18. Права потребителя','text':'Потребитель вправе потребовать возврата. Отсутствие чека не является основанием для отказа.'}
  self.assertTrue(VerifiedSourceLibrary.covered('недостатки отсутствие кассового чека','consumer',[f]))
  self.assertFalse(VerifiedSourceLibrary.covered('недостатки','consumer',[{**f,'citation':'Статья 18.1. Иная норма'}]))
 def test_child_alimony_query_and_coverage_do_not_use_divorce_or_parentage_only(self):
  from land_assistant.legal.task_catalog import search_query
  q=search_query('Разводимся, алименты на ребенка, место работы отца неизвестно','family')
  self.assertIn('твердой',search_query('Алименты на ребёнка, доход неизвестен','family'));self.assertIn('содержанию',q);self.assertIn('твердой',q);self.assertNotIn('происхождения',q)
  self.assertFalse(VerifiedSourceLibrary.covered(q,'family',[{'citation':'Статья 90. Алименты бывшему супругу','text':'Алиментные отношения.'}]))
