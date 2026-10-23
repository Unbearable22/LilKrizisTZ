import unittest
from land_assistant.legal.task_catalog import validate_tasks,normalize_scope,allowed_fields,search_query
class RoutingTests(unittest.TestCase):
 def test_general_topic_and_legacy_scope(self):
  t={'task_id':'t','function_id':'general_legal_help','formulation':'Принятие наследства на участок','scope':'individual','legal_topic':'inheritance'}
  self.assertEqual(validate_tasks({'tasks':[t]})[0]['function_id'],'general_legal_help')
  self.assertEqual(normalize_scope('parcel'),'individual')
  for wrong in [{**t,'legal_topic':'land'},{**t,'function_id':'random'},{k:v for k,v in t.items() if k!='legal_topic'}]:
   with self.assertRaises(ValueError):validate_tasks({'tasks':[wrong]})
 def test_relevant_fields_and_search_privacy(self):
  self.assertIn('event_date',allowed_fields('labor'));self.assertNotIn('object_reference',allowed_fields('labor'))
  q=search_query('Я Иван Иванов из г. Москва, ул. Лесная 1: работодатель не платит зарплату, телефон +79991234567','labor')
  self.assertNotIn('Иван',q);self.assertNotIn('Лесная',q);self.assertNotIn('7999',q);self.assertIn('зарплат',q)
 def test_topic_prevents_ambiguous_words_from_crossing_legal_domains(self):
  q=search_query('Расторжение брака при наличии ребенка','family')
  self.assertNotIn('трудов',q);self.assertNotIn('потребител',q);self.assertIn('брака',q)
