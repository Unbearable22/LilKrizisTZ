import tempfile
import unittest
from land_assistant.legal.source_index import SourceIndex
from land_assistant.legal.source_documents import VerifiedDocument

class SourceIndexTests(unittest.TestCase):
 def test_hash_identity_search_atomic_replacement_and_freshness(self):
  with tempfile.TemporaryDirectory() as folder:
   index=SourceIndex(folder+'/index.sqlite')
   def doc(text,checked='2026-11-02T10:00:00+00:00'):
    return VerifiedDocument('https://www.consultant.ru/document/cons_doc_LAW_305/','Закон о защите прав потребителей','КонсультантПлюс','normative_act','current','ред. от 01.01.2026',checked,[{'text':text,'citation':'Статья 18'}])
   first=doc('Права потребителя при обнаружении недостатков товара. Отсутствие чека не основание для отказа.')
   index.upsert(first);a=index.search('потребител недостатк',6)[0]
   index.upsert(first);self.assertEqual(index.search('потребител недостатк',6)[0]['id'],a['id'])
   self.assertEqual(index.read(a['id'],'2026-11-02')['text'],first.fragments[0]['text'])
   self.assertEqual(index.search('потребител',6,as_of_date='2026-11-03'),[])
   index.upsert(doc('Права потребителя при обнаружении недостатков изменены.'))
   self.assertNotEqual(index.search('потребител',6)[0]['id'],a['id'])
   self.assertIsNone(index.read(a['id'],'2026-11-02'))
 def test_empty_queries_and_fts_syntax_are_not_sql(self):
  with tempfile.TemporaryDirectory() as folder:
   index=SourceIndex(folder+'/index.sqlite')
   self.assertEqual(index.search('" OR * --',6),[])
