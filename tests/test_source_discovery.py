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
   with patch.object(lib.library,'search',return_value=[]) as search,patch('land_assistant.legal.source_discovery.discover_roots',return_value=[]):
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
 def test_missing_registered_materials_searches_web_then_reuses_discovered_index(self):
  from unittest.mock import AsyncMock
  with tempfile.TemporaryDirectory() as tmp:
   lib=VerifiedSourceLibrary(Path('knowledge'),Path(tmp));now=datetime.now(timezone.utc).isoformat();day=datetime.now().date().isoformat()
   f={'id':'new','source_url':'https://www.consultant.ru/document/cons_doc_LAW_999999/','title':'Новый проверенный закон','citation':'Статья 1','text':'Порядок восстановления утраченного документа.','version':'ред. от 01.01.2026','last_checked_at':now}
   root={'id':'web_999999','url':f['source_url'],'topics':['administrative'],'enabled':True}
   with patch.object(lib.library,'search',AsyncMock(side_effect=[[],[{'id':'new'}]])),patch.object(lib.library,'read',return_value=f),patch('land_assistant.legal.source_discovery.discover_roots',AsyncMock(return_value=[root])) as web:
    result=asyncio.run(lib.search('восстановление утраченного документа','administrative',day,RequestBudget()))
   self.assertTrue(result);web.assert_awaited_once()
   cached=VerifiedSourceLibrary(Path('knowledge'),Path(tmp))
   with patch('land_assistant.legal.source_discovery.discover_roots',side_effect=AssertionError('fresh cache avoids network')):
    result=asyncio.run(cached.search('восстановления утраченного документа','administrative',day,RequestBudget()))
   self.assertTrue(result)
 def test_explicit_source_expansion_searches_web_even_if_catalog_has_some_materials(self):
  from unittest.mock import AsyncMock
  with tempfile.TemporaryDirectory() as tmp:
   lib=VerifiedSourceLibrary(Path('knowledge'),Path(tmp));now=datetime.now(timezone.utc).isoformat();day=datetime.now().date().isoformat()
   f={'id':'new','source_url':'https://www.consultant.ru/document/cons_doc_LAW_999999/','title':'Новый закон','citation':'Статья 1','text':'Норма по теме административных процедур.','version':'ред. от 01.01.2026','last_checked_at':now}
   root={'id':'web_999999','url':f['source_url'],'topics':['administrative'],'enabled':True}
   with patch.object(lib.library,'search',AsyncMock(return_value=[{'id':'new'}])),patch.object(lib.library,'read',return_value=f),patch('land_assistant.legal.source_discovery.discover_roots',AsyncMock(return_value=[root])) as web:
    result=asyncio.run(lib.search('административные процедуры','administrative',day,RequestBudget(),refresh=True))
   self.assertTrue(result);web.assert_awaited_once()
 def test_passport_cache_ignores_unrelated_citizenship_articles(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=VerifiedSourceLibrary(Path('knowledge'),Path(tmp));now=datetime.now(timezone.utc).isoformat();day=datetime.now().date().isoformat()
   lib.index.upsert(VerifiedDocument('https://www.consultant.ru/document/cons_doc_LAW_445998/','О гражданстве','КонсультантПлюс','normative_act','current','ред. от 26.06.2026',now,[{'text':'Утрата паспорта: незамедлительно заявить в территориальный орган внутренних дел.','citation':'Статья 9. Документы'},{'text':'Паспорт при прекращении гражданства и сведения о гражданстве.','citation':'Статья 25. Прекращение гражданства'}]))
   hits=asyncio.run(lib.search('паспорт утрата хищение','administrative',day,RequestBudget()))
   self.assertEqual(len(hits),1);self.assertTrue(hits[0]['citation'].startswith('Статья 9.'))
 def test_initial_catalog_then_refresh_share_budget_without_skipping_web(self):
  from unittest.mock import AsyncMock
  with tempfile.TemporaryDirectory() as tmp:
   lib=VerifiedSourceLibrary(Path('knowledge'),Path(tmp));now=datetime.now(timezone.utc).isoformat();day=datetime.now().date().isoformat();budget=RequestBudget()
   def fragment(fid,doc):return {'id':fid,'source_url':f'https://www.consultant.ru/document/cons_doc_LAW_{doc}/','title':'Закон','citation':'Статья 1','text':'Правило административной процедуры.','version':'ред. от 01.01.2026','last_checked_at':now}
   root={'id':'web_999999','url':fragment('new',999999)['source_url'],'topics':['administrative'],'enabled':True}
   with patch.object(lib.library,'search',AsyncMock(side_effect=[[{'id':'old'}],[{'id':'new'}]])),patch.object(lib.library,'read',side_effect=lambda fid,day:fragment(fid,34661 if fid=='old' else 999999)),patch('land_assistant.legal.source_discovery.discover_roots',AsyncMock(return_value=[root])) as web:
    asyncio.run(lib.search('административная процедура','administrative',day,budget))
    result=asyncio.run(lib.search('дополнительные административные основания','administrative',day,budget,refresh=True))
   self.assertTrue(result);web.assert_awaited_once()
 def test_initial_catalog_reserves_three_new_document_slots_for_web_expansion(self):
  from unittest.mock import AsyncMock
  with tempfile.TemporaryDirectory() as tmp:
   lib=VerifiedSourceLibrary(Path('knowledge'),Path(tmp));now=datetime.now(timezone.utc).isoformat();day=datetime.now().date().isoformat();budget=RequestBudget()
   f={'id':'old','source_url':'https://www.consultant.ru/document/cons_doc_LAW_34661/','title':'Закон','citation':'Статья 1','text':'Административная процедура.','version':'ред. от 01.01.2026','last_checked_at':now}
   async def exhaustive(query,topic,date,b):
    b.documents_left=0
    return [{'id':'old'}]
   with patch.object(lib.library,'search',exhaustive),patch.object(lib.library,'read',return_value=f):
    asyncio.run(lib.search('административная процедура','administrative',day,budget))
   self.assertGreaterEqual(budget.documents_left,3)
 def test_sale_documents_cache_without_registration_rules_is_incomplete(self):
  self.assertFalse(VerifiedSourceLibrary.covered('договор продажи недвижимости представление заявления и прилагаемых документов','civil',[{'citation':'Статья 550. Форма договора','source_url':'https://www.consultant.ru/document/cons_doc_LAW_9027/','text':'Договор составляется письменно.'}]))

 def test_unrelated_civil_article_does_not_complete_sale_cache(self):
  fragments=[{'citation':'Статья 18. Представление документов','source_url':'https://www.consultant.ru/document/cons_doc_LAW_182661/'}, {'citation':'Статья 702. Договор подряда','source_url':'https://www.consultant.ru/document/cons_doc_LAW_9027/'}]
  self.assertFalse(VerifiedSourceLibrary.covered('договор продажи недвижимости','civil',fragments))
