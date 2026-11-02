import unittest
from land_assistant.legal.answer_evidence import validate_claims,public_evidence
from land_assistant.legal.errors import LegalError
class EvidenceTests(unittest.TestCase):
 def setUp(self):
  self.f={'id':'f1','title':'Закон','text':'Отсутствие у потребителя кассового или товарного чека не является основанием для отказа.','source_url':'https://www.consultant.ru/document/cons_doc_LAW_305/','citation':'Статья 18','last_checked_at':'2026-11-02T10:00:00+00:00','version':'ред. от 28.12.2025','source_kind':'normative_act'}
 def test_anchor_and_id_required_and_urls_come_from_read_evidence(self):
  claim={'section':'answer','text':'Отсутствие чека само по себе не исключает защиту.','evidence_ids':['f1'],'anchors':[{'fragment_id':'f1','quote':'не является основанием для отказа'}]}
  self.assertTrue(validate_claims([claim],{'f1':self.f}).accepted_claims)
  for bad in [{**claim,'evidence_ids':['unknown']},{**claim,'anchors':[{'fragment_id':'f1','quote':'можно вернуть любой товар в любое время'}]}]:
   with self.assertRaises(LegalError):validate_claims([bad],{'f1':self.f})
  evidence=public_evidence([self.f]);self.assertEqual(evidence[0]['url'],self.f['source_url']);self.assertNotIn('text',evidence[0])
  self.assertEqual(public_evidence([{**self.f,'source_url':'https://www.consultant.ru.evil/'}]),[])
 def test_missing_checked_timestamp_never_yields_public_link(self):
  self.assertEqual(public_evidence([{**self.f,'last_checked_at':None}]),[])
 def test_all_answer_and_scenario_text_must_be_covered(self):
  from land_assistant.legal.answer_evidence import validate_claim_sections
  result={'answer':'Точный ответ.','scenarios':[],'claims':[{'section':'answer','text':'Иной ответ.','evidence_ids':['f1'],'anchors':[{'fragment_id':'f1','quote':'не является основанием для отказа'}]}]}
  with self.assertRaises(LegalError):validate_claim_sections(result,[self.f])
