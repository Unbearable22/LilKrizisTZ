import asyncio,json,tempfile,unittest
from pathlib import Path
from land_assistant.legal.consultant_library import ConsultantLibrary
from land_assistant.legal.consultant_types import DocumentPage,RequestBudget,SourceError
ROOT='https://www.consultant.ru/document/cons_doc_LAW_1/'
ARTICLE=ROOT+'a'*40+'/'
class FakeHTTP:
 calls=0
 async def fetch(self,url,**kwargs):
  self.calls+=1
  title='Закон (ред. от 01.01.2026)' if url==ROOT else 'Статья 1. Принятие наследства'
  body=f'<div class="document-page__toc"><a href="{ARTICLE}">Статья 1. Принятие наследства</a></div><p>Нормативный текст закона.</p>' if url==ROOT else '<div class="document__style doc-style" data-style-id="3">Статья 1. Принятие наследства</div><p>Для приобретения наследства наследник должен его принять.</p>'
  return DocumentPage(url,200,{},f'<h1>{title}</h1><div class="document-page__content">{body}</div>','2026-10-22T00:00:00+00:00')
class LibraryTests(unittest.TestCase):
 def test_search_then_read_registered_id_and_budget(self):
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'roots.json').write_text(json.dumps({'roots':[{'id':'gk','url':ROOT,'topics':['inheritance'],'enabled':True}]}))
    http=FakeHTTP();lib=ConsultantLibrary(root/'roots.json',root/'cache',http=http,now=lambda:__import__('datetime').datetime(2026,10,22,1,tzinfo=__import__('datetime').timezone.utc))
    budget=RequestBudget();hits=await lib.search('принятие наследства','inheritance','2026-10-22',budget)
    self.assertTrue(hits);self.assertNotIn('text',hits[0]);self.assertEqual(budget.articles_left,7)
    fragment=lib.read(hits[0]['id'],'2026-10-22');self.assertIn('должен его принять',fragment['text'])
    with self.assertRaises(SourceError):lib.read('https://evil.invalid','2026-10-22')
  asyncio.run(run())
 def test_one_level_article_reference_is_read(self):
  class Linked(FakeHTTP):
   async def fetch(self,url,**kw):
    page=await super().fetch(url,**kw)
    if url==ROOT:page.body=page.body.replace('</div>',f'<div class="document-page__toc"><a href="{ROOT+"b"*40+"/"}">Статья 2. Особое правило</a></div></div>')
    elif url==ARTICLE:page.body=page.body.replace('наследник должен его принять.','применяются правила, предусмотренные статьями 2 и 3.')
    else:page.body=page.body.replace('Статья 1. Принятие наследства','Статья 2. Особое правило')
    return page
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'roots.json').write_text(json.dumps({'roots':[{'id':'gk','url':ROOT,'topics':['inheritance'],'enabled':True}]}))
    now=lambda:__import__('datetime').datetime(2026,10,22,1,tzinfo=__import__('datetime').timezone.utc)
    hits=await ConsultantLibrary(root/'roots.json',root/'cache',http=Linked(),now=now).search('принятие наследства','inheritance','2026-10-22',RequestBudget())
    self.assertTrue(any('Статья 2' in h['citation'] for h in hits))
  asyncio.run(run())
 def test_exhausted_root_budget_is_not_reported_as_absent_law(self):
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'roots.json').write_text('{"roots":[]}')
    lib=ConsultantLibrary(root/'roots.json',root/'cache')
    with self.assertRaises(SourceError) as err:await lib.search('наследство','inheritance',lib.now().astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat(),RequestBudget(roots_left=0))
    self.assertEqual(err.exception.code,'source_budget_exhausted')
  asyncio.run(run())
 def test_overview_at_article_url_does_not_become_normative_fragment(self):
  class Overview(FakeHTTP):
   async def fetch(self,url,**kwargs):
    p=await super().fetch(url,**kwargs)
    if url!=ROOT:p.body='<h1>Статья 1. Обзор</h1><div class="document-page__content"><p>Статья 1. Обзор практики применения нормы, а не нормативный текст.</p></div>'
    return p
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'roots.json').write_text(json.dumps({'roots':[{'id':'gk','url':ROOT,'topics':['inheritance'],'enabled':True}]}));lib=ConsultantLibrary(root/'roots.json',root/'cache',http=Overview(),now=lambda:__import__('datetime').datetime(2026,10,22,1,tzinfo=__import__('datetime').timezone.utc))
    with self.assertRaises(SourceError):await lib.search('принятие наследства','inheritance','2026-10-22',RequestBudget())
  asyncio.run(run())

 def test_shared_cache_keeps_budget_independent_fragment_content(self):
  class LongArticle(FakeHTTP):
   async def fetch(self,url,**kwargs):
    p=await super().fetch(url,**kwargs)
    if url!=ROOT:p.body=p.body.replace('</div>','<p>'+('Основное правило. '*100)+'</p><p>Короткое исключение.</p></div>')
    return p
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'roots.json').write_text(json.dumps({'roots':[{'id':'gk','url':ROOT,'topics':['inheritance'],'enabled':True}]}))
    now=lambda:__import__('datetime').datetime(2026,10,22,1,tzinfo=__import__('datetime').timezone.utc)
    first=ConsultantLibrary(root/'roots.json',root/'cache',http=LongArticle(),now=now)
    hits=await first.search('принятие наследства','inheritance','2026-10-22',RequestBudget());original=first.read(hits[0]['id'],'2026-10-22')['text']
    second=ConsultantLibrary(root/'roots.json',root/'cache',http=LongArticle(),now=now)
    try:await second.search('принятие наследства','inheritance','2026-10-22',RequestBudget(context_left=1000))
    except SourceError:pass
    self.assertEqual(first.read(hits[0]['id'],'2026-10-22')['text'],original)
  asyncio.run(run())
