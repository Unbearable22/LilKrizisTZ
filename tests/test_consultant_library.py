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
 def test_passport_loss_reads_relevant_passport_article_not_citizenship_revocation(self):
  class PassportHTTP(FakeHTTP):
   async def fetch(self,url,**kw):
    self.calls+=1
    title='Закон (ред. от 01.01.2026)' if url==ROOT else 'Статья '+('9. Документы, удостоверяющие гражданство' if url==ARTICLE else '11. Утрата иностранного гражданства')
    body=f'<a href="{ARTICLE}">Статья 9. Документы, удостоверяющие гражданство</a><a href="{ROOT+"b"*40+"/"}">Статья 11. Утрата иностранного гражданства</a>' if url==ROOT else f'<p class="doc-style">{title}</p><p>При утрате паспорта необходимо незамедлительно заявить об этом.</p>'
    return DocumentPage(url,200,{},f'<h1>{title}</h1><div class="document-page__content">{body}</div>','2026-10-22T00:00:00+00:00')
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'roots.json').write_text(json.dumps({'roots':[{'id':'citizenship','url':ROOT,'topics':['administrative'],'enabled':True}]}));http=PassportHTTP();lib=ConsultantLibrary(root/'roots.json',root/'cache',http=http,now=lambda:__import__('datetime').datetime(2026,10,22,1,tzinfo=__import__('datetime').timezone.utc))
    hits=await lib.search('паспорт утрата хищение','administrative','2026-10-22',RequestBudget())
    self.assertTrue(hits);self.assertTrue(all(f['citation'].startswith('Статья 9.') for f in hits));self.assertEqual(http.calls,2)
  asyncio.run(run())

 def test_sale_document_search_includes_registration_law_and_contract(self):
  reg='https://www.consultant.ru/document/cons_doc_LAW_182661/'
  class SaleHTTP:
   async def fetch(self,url,**kw):
    root=reg if url.startswith(reg) else ROOT
    number='18' if root==reg else '550'
    heading=f'Статья {number}. '+('Представление заявления и документов' if root==reg else 'Форма договора продажи недвижимости')
    body=f'<a href="{root+"a"*40+"/"}">{heading}</a>' if url==root else f'<p class="doc-style">{heading}</p><p>Документы и заявление представляются заявителем.</p>'
    title='Закон (ред. от 01.01.2026)' if url==root else heading
    return DocumentPage(url,200,{},f'<h1>{title}</h1><div class="document-page__content">{body}</div>','2026-10-22T00:00:00+00:00')
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp);p.joinpath('roots.json').write_text(json.dumps({'roots':[{'id':'civil2','url':ROOT,'topics':['civil'],'enabled':True},{'id':'registration','url':reg,'topics':['civil'],'enabled':True}]}))
    now=lambda:__import__('datetime').datetime(2026,10,22,1,tzinfo=__import__('datetime').timezone.utc)
    lib=ConsultantLibrary(p/'roots.json',p/'cache',http=SaleHTTP(),now=now)
    hits=await lib.search('договор продажи недвижимости документы государственная регистрация','civil','2026-10-22',RequestBudget())
    self.assertEqual({f['citation'].split('.')[0] for f in hits},{'Статья 18','Статья 550'})
  asyncio.run(run())
