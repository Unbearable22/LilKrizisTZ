"""Contracts that catch wrong sources, unsafe paths and fake MCP integration."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

try:
    from land_assistant.legal.knowledge import Knowledge
    from land_assistant.legal.mcp_client import LocalLegalMCP
except ImportError:
    Knowledge=LocalLegalMCP=None


def make_library(root):
    root=Path(root)
    (root/'prompts').mkdir();(root/'laws').mkdir()
    (root/'prompts/legal_help.txt').write_text('Отвечай только по предоставленным источникам. Это учебный тест.')
    (root/'laws/demo.md').write_text('# Учебный акт\n\n## Статья 1. Образование участка\nДля образования участка нужны исходные сведения о границах.\n\n## Статья 2. Документы\nСостав документов зависит от выбранной процедуры.')
    (root/'laws/manifest.json').write_text(json.dumps({'documents':[{'id':'demo','path':'demo.md','title':'Учебный акт','version':'DEMO','source_url':'https://example.org/demo','valid_until':'2099-01-01','verified_by':'DEMO','demo':True}]},ensure_ascii=False))
    return root


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Knowledge,'Файловый MCP ещё не реализован')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=make_library(self.tmp.name)

    def test_registered_digest_rejects_modified_law(self):
        manifest=self.root/'laws/manifest.json'
        data=json.loads(manifest.read_text());data['documents'][0]['sha256']='0'*64
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):Knowledge(self.root,demo=True).search('образование участка')

    def test_search_reads_actual_fragment_and_tracks_revision(self):
        k=Knowledge(self.root,demo=True)
        found=k.search('образование участка')
        self.assertTrue(found)
        fragment=k.read(found[0]['id'])
        self.assertIn('исходные сведения',fragment['text'])
        self.assertEqual(fragment['title'],'Учебный акт')
        self.assertTrue(fragment['demo'])
        self.assertEqual(k.search('космические ракеты'),[])
        self.assertIn('источникам',k.prompt())

    def test_demo_sources_never_become_live_law(self):
        self.assertEqual(Knowledge(self.root,demo=False).search('участок'),[])

    def test_expired_material_is_not_used(self):
        p=self.root/'laws/manifest.json';data=json.loads(p.read_text());data['documents'][0]['valid_until']='2000-01-01';p.write_text(json.dumps(data))
        self.assertEqual(Knowledge(self.root,demo=True).search('участок'),[])

    def test_file_change_invalidates_old_fragment_id(self):
        k=Knowledge(self.root,demo=True);fid=k.search('образование')[0]['id']
        p=self.root/'laws/demo.md';p.write_text(p.read_text()+'\nИзменение редакции.')
        with self.assertRaises(ValueError):k.read(fid)

    def test_symlink_and_path_traversal_do_not_read_outside_library(self):
        p=self.root/'laws/manifest.json';data=json.loads(p.read_text());data['documents'][0]['path']='../../.env';p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):Knowledge(self.root,demo=True).search('секрет')
        outside=self.root/'secret.md';outside.write_text('secret')
        (self.root/'laws/alias.md').symlink_to(outside)
        data['documents'][0]['path']='alias.md';p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):Knowledge(self.root,demo=True).search('секрет')

    def test_context_budget_reduction_is_explicit(self):
        text='\n'.join(f'## Статья {i}. Образование участка\n'+('образование участка '*190) for i in range(6))
        (self.root/'laws/demo.md').write_text(text)
        result=asyncio.run(LocalLegalMCP(self.root,demo=True).context('образование участка'))
        self.assertTrue(result['context_reduced'])
        self.assertTrue(result['limitations'])
        self.assertLessEqual(sum(len(f['text']) for f in result['fragments']),16000)

    def test_real_stdio_mcp_returns_prompt_and_sources(self):
        self.assertIsNotNone(LocalLegalMCP)
        result=asyncio.run(LocalLegalMCP(self.root,demo=True).context('образование участка'))
        self.assertIn('источникам',result['prompt'])
        self.assertIn('исходные сведения',result['fragments'][0]['text'])
        self.assertEqual(result['trace'][0],'mcp.initialize')
        self.assertIn('mcp.prompts.get',result['trace'])
        self.assertIn('mcp.tools.read',result['trace'])

    def test_specific_heading_beats_generic_paragraph_with_query_word_overlap(self):
        (self.root/'laws/demo.md').write_text('''## Статья 1. Градостроительный план земельного участка
Градостроительный план земельного участка содержит границы, ограничения и параметры строительства.
## Статья 2. Общие сведения
Какие сведения обычно содержит градостроительный план земельного участка: эта общая фраза упомянута здесь для сравнения, этот раздел описывает иной предмет.
''')
        found=Knowledge(self.root,demo=True).search('Какие сведения обычно содержит градостроительный план земельного участка')
        self.assertEqual(found[0]['citation'],'Статья 1. Градостроительный план земельного участка')

    def test_inflected_membership_and_rights_are_searchable(self):
        (self.root/'laws/demo.md').write_text('''## Статья 1. Права члена товарищества
Члены товарищества вправе получать копии документов.
## Статья 2. Общие сведения
Порядок деятельности организации.
''')
        found=Knowledge(self.root,demo=True).search('О правах членов')
        self.assertTrue(found)
        self.assertEqual(found[0]['citation'],'Статья 1. Права члена товарищества')
