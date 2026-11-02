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
 def test_section_references_do_not_require_duplicate_answer_text(self):
  from land_assistant.legal.answer_evidence import validate_claim_sections
  result={'answer':'Отсутствие чека само по себе не исключает защиту.','claims':[{'section':'answer','evidence_ids':['f1'],'anchors':[{'fragment_id':'f1','quote':'не является основанием для отказа'}]}]}
  validate_claim_sections(result,[self.f])
 def test_host_selects_exact_anchor_without_generating_or_truncating_norm(self):
  from land_assistant.legal.answer_evidence import prepare_claims
  draft={'answer':'Отсутствие кассового чека не является основанием для отказа.','citations':['f1']}
  claims=prepare_claims(draft,[self.f]);self.assertEqual(claims[0]['section'],'answer')
  quote=claims[0]['anchors'][0]['quote'];self.assertIn(quote,self.f['text']);self.assertIn('чека',quote)
  validate_claims(claims,{'f1':self.f})
 def test_anchor_selection_covers_distinct_sentences_not_only_longest_topic(self):
  from land_assistant.legal.answer_evidence import prepare_claims
  f={**self.f,'text':'Отсутствие кассового чека не является основанием для отказа.\nЕсли гарантийный срок не установлен, покупатель доказывает причины возникновения недостатков до передачи товара.'}
  result={'answer':'Отсутствие кассового чека не является основанием для отказа. Если гарантийный срок не установлен, покупатель доказывает причины возникновения недостатков до передачи товара.','citations':['f1']}
  quotes=[a['quote'] for a in prepare_claims(result,[f])[0]['anchors']]
  self.assertTrue(any('чека' in q for q in quotes));self.assertTrue(any('гарантийный' in q for q in quotes))
 def test_only_explicitly_verified_scenarios_can_survive_rejected_draft(self):
  from land_assistant.legal.answer_evidence import prepare_claims,salvage_verified_sections
  f={**self.f,'text':'Потребитель вправе потребовать возврата суммы. Отсутствие чека не является основанием для отказа.'}
  draft={'status':'partial_answer','answer':'Неподтвержденное обещание.','citations':['f1'],'missing_fields':[],'scenarios':[{'condition':'всегда','outcome':'Неподтвержденное обещание.','citations':['f1']},{'condition':'чек отсутствует','outcome':'это не является основанием для отказа','citations':['f1']}],'limitations':['Спорное правило.'],'_verified_sections':['scenario:1','scenario:99']}
  draft['claims']=prepare_claims(draft,[f]);result=salvage_verified_sections(draft,[f],scope='individual')
  self.assertEqual(len(result['scenarios']),1);self.assertNotIn('Неподтвержденное',str(result));self.assertIn('основанием для отказа',result['scenarios'][0]['outcome'])
  from land_assistant.legal.answer_evidence import validate_claim_sections
  validate_claim_sections(result,[f])
  self.assertIsNone(salvage_verified_sections({**draft,'_verified_sections':[]},[f],scope='individual'))
