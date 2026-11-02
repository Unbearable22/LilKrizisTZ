import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from land_assistant.legal.consultant_cache import ConsultantCache
from land_assistant.legal.consultant_types import SourceError
class CacheTests(unittest.TestCase):
 def test_age_hash_change_and_evicted_id(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=ConsultantCache(Path(tmp));now=datetime.now(timezone.utc)
   f={'document_id':'law1','source_url':'https://www.consultant.ru/document/cons_doc_LAW_1/','text':'Условие','last_checked_at':now.isoformat(),'version':'ред.','extraction_status':'verified_current'}
   fid=c.put(f);self.assertEqual(c.read(fid,as_of_date=now.date().isoformat(),now=now)['text'],'Условие')
   with self.assertRaises(SourceError):c.read(fid,as_of_date=now.date().isoformat(),now=now+timedelta(hours=25))
   c.put({**f,'text':'Другое условие'})
   with self.assertRaises(SourceError):c.read(fid,as_of_date=now.date().isoformat(),now=now)
 def test_future_check_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=ConsultantCache(Path(tmp));now=datetime.now(timezone.utc)
   fid=c.put({'document_id':'x','source_url':'x','text':'x','last_checked_at':(now+timedelta(days=1)).isoformat(),'extraction_status':'verified_current'})
   with self.assertRaises(SourceError):c.read(fid,as_of_date=now.date().isoformat(),now=now)
 def test_current_fragment_cannot_be_read_as_historical_edition(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=ConsultantCache(Path(tmp));now=datetime(2026,10,22,12,tzinfo=timezone.utc)
   fid=c.put({'document_id':'x','source_url':'x','text':'Норма','last_checked_at':now.isoformat(),'extraction_status':'verified_current'})
   with self.assertRaises(SourceError):c.read(fid,as_of_date='2020-01-01',now=now)

 def test_same_page_and_part_cannot_reassign_id_to_different_text(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=ConsultantCache(tmp);now=datetime(2026,10,22,12,tzinfo=timezone.utc)
   f={'document_id':'law','source_url':'x','text':'Основное правило и исключение','page_hash':'a'*64,'part_index':0,'last_checked_at':now.isoformat(),'extraction_status':'verified_current'}
   old=c.put(f);new=c.put({**f,'text':'Только исключение'})
   self.assertNotEqual(old,new)
   with self.assertRaises(SourceError):c.read(old,as_of_date='2026-10-22',now=now)
