import unittest
from land_assistant.legal.consultant_parser import parse_document
from land_assistant.legal.consultant_types import DocumentPage,SourceError
ROOT='https://www.consultant.ru/document/cons_doc_LAW_1/'
def page(title='Закон (ред. от 01.01.2026)',body='<p>Статья 1. Право</p><p>Нормативное условие.</p>',meta=''):
 return DocumentPage(ROOT,200,{},f'<html><head>{meta}</head><body><h1>{title}</h1><div class="document-page__content">{body}</div></body></html>','2026-10-22T00:00:00+00:00')
class ParserTests(unittest.TestCase):
 def test_extracts_only_content_and_valid_toc(self):
  p=page(body='<p>Статья 1. Право</p><p>Условие.</p><div class="document-page__toc"><a href="/document/cons_doc_LAW_1/'+('a'*40)+'/">Статья 2. Защита</a></div>')
  r=parse_document(p,as_of_date='2026-10-22');self.assertIn('Условие',r['text']);self.assertEqual(len(r['toc']),1);self.assertNotIn('Статья 2',r['text'])
 def test_future_unknown_and_captcha_do_not_become_law(self):
  for p in [page(title='Закон (ред. от 01.01.2027)'),page(title='Просто закон'),page(body='<p>CAPTCHA подтвердите, что вы человек</p>'),page(title='Проект закона (ред. от 01.01.2026)')]:
   with self.subTest(title=p.body[:80]),self.assertRaises(SourceError):parse_document(p,as_of_date='2026-10-22')
 def test_separate_future_announcement_is_not_current_edition(self):
  p=page();p.body=p.body.replace('<h1>','<p>Подготовлена редакция с изменениями, не вступившими в силу</p><h1>')
  self.assertEqual(parse_document(p,as_of_date='2026-10-22')['edition_status'],'current')
 def test_historical_request_not_inferred_from_current_page(self):
  with self.assertRaises(SourceError):parse_document(page(),as_of_date='2025-01-01')
 def test_act_designation_preserves_full_number(self):
  p=page(title='Кодекс N 146-ФЗ (ред. от 01.01.2026)')
  self.assertEqual(parse_document(p,as_of_date='2026-10-22')['act_designation'],'146-ФЗ')

 def test_explicit_noncurrent_or_repealed_status_is_rejected(self):
  cases=[page(title='Закон',meta='<meta name="description" content="Недействующая редакция">'),page(body='<p>Документ утратил силу</p><p>Статья 1. Прежнее правило.</p>'),page(title='Закон (недействующая редакция, ред. от 01.01.2026)')]
  for item in cases:
   with self.subTest(body=item.body),self.assertRaises(SourceError):parse_document(item,as_of_date='2026-10-22')
