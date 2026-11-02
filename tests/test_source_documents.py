import unittest
from land_assistant.legal.source_documents import extract_document
from land_assistant.legal.trusted_sources import FetchedDocument,SourcePolicy
from land_assistant.legal.consultant_types import SourceError
class SourceDocumentTests(unittest.TestCase):
 def test_unknown_markup_and_scanned_pdf_fail_closed(self):
  for kind,body in [('text/html',b'<h1>Law</h1>unknown'),('application/pdf',b'%PDF-1.0 scanned')]:
   with self.subTest(kind=kind),self.assertRaises(SourceError):extract_document(FetchedDocument('https://www.consultant.ru/document/cons_doc_LAW_305/',kind,body,'2026-11-02T12:00:00+00:00'),SourcePolicy('КонсультантПлюс','normative_act','consultant'))
