import asyncio,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from land_assistant.legal.task_catalog import search_query
from land_assistant.legal.source_discovery import VerifiedSourceLibrary
from land_assistant.legal.consultant_library import ConsultantLibrary
from land_assistant.legal.consultant_types import DocumentPage,RequestBudget
LAND='https://www.consultant.ru/document/cons_doc_LAW_33773/'
REG='https://www.consultant.ru/document/cons_doc_LAW_182661/'

class AcquisitionTests(unittest.TestCase):
 def test_unknown_unformed_plot_uses_provision_query_without_address(self):
  q=search_query('Порядок приобретения пустого земельного участка без границ в Строгановке; документов нет','land')
  for phrase in ['предоставление','предварительное согласование','схема расположения']:self.assertIn(phrase,q)
  self.assertNotIn('Строганов',q)
 def test_generic_rights_article_is_not_enough_for_acquisition(self):
  q='предоставление земельного участка государственной муниципальной собственности предварительное согласование схема расположения'
  self.assertFalse(VerifiedSourceLibrary.covered(q,'land',[{'citation':'Статья 26. Документы о правах','source_url':LAND}]))
 def test_reads_provision_and_formation_articles_instead_of_unrelated_registration(self):
  titles={'39.14':'Порядок предоставления земельного участка','39.15':'Предварительное согласование предоставления земельного участка','39.3':'Продажа земельных участков государственной муниципальной собственности','11.10':'Схема расположения земельного участка','26':'Документы о правах на земельные участки'}
  urls={n:LAND+str(i)*40+'/' for i,n in enumerate(titles,1)}
  class HTTP:
   calls=[]
   async def fetch(self,url,**kw):
    self.calls.append(url)
    if url==LAND:
     title='Земельный кодекс (ред. от 01.01.2026)';body=''.join(f'<a href="{urls[n]}">Статья {n}. {t}</a>' for n,t in titles.items())
    elif url==REG:
     title='Закон о регистрации (ред. от 01.01.2026)';body='Регистрация. Документы.'
    else:
     n=next(n for n,u in urls.items() if u==url);title=f'Статья {n}. {titles[n]}';body=f'<p class="doc-style">{title}</p><p>Предоставление участка производится с учётом установленных условий.</p>'
    return DocumentPage(url,200,{},f'<h1>{title}</h1><div class="document-page__content">{body}</div>','2026-11-05T00:00:00+00:00')
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);root.joinpath('roots.json').write_text(json.dumps({'roots':[{'id':'land','url':LAND,'topics':['land'],'enabled':True},{'id':'registration','url':REG,'topics':['land'],'enabled':True}]}))
    http=HTTP();lib=ConsultantLibrary(root/'roots.json',root/'cache',http=http,now=lambda:datetime(2026,11,5,1,tzinfo=timezone.utc))
    q='предоставление земельного участка государственной муниципальной собственности предварительное согласование схема расположения'
    result=await lib.search(q,'land','2026-11-05',RequestBudget())
    numbers={f['citation'].split('. ')[0].removeprefix('Статья ') for f in result}
    self.assertEqual(numbers,{'39.14','39.15','39.3','11.10'});self.assertNotIn(REG,http.calls)
  asyncio.run(run())
 def test_known_private_seller_and_sale_of_own_plot_are_not_public_acquisition(self):
  from land_assistant.legal.task_catalog import is_land_acquisition
  self.assertFalse(is_land_acquisition('Покупка пустого участка у частного собственника без границ'))
  self.assertFalse(is_land_acquisition('Хочу продать свой пустой участок без границ'))
 def test_place_name_is_not_a_construction_intent(self):
  q=search_query('Участок в Строгановке','land')
  self.assertNotIn('градостроительный',q);self.assertNotIn('разрешенное использование',q)
 def test_known_catalog_acquisition_refresh_keeps_document_budget_and_skips_web(self):
  from unittest.mock import patch,AsyncMock
  from land_assistant.legal.task_catalog import LAND_ACQUISITION_QUERY
  with tempfile.TemporaryDirectory() as tmp:
   lib=VerifiedSourceLibrary(Path('knowledge'),Path(tmp));day=datetime.now().date().isoformat();now=datetime.now(timezone.utc).isoformat()
   fragments={str(i):{'id':str(i),'source_url':LAND+str(i)*40+'/','title':'ЗК РФ','citation':'Статья '+n+'. Правило','text':'Предоставление участка производится при наличии предусмотренных условий.','version':'Последняя редакция','last_checked_at':now} for i,n in enumerate(['39.14','39.15','39.3','11.10'],1)}
   async def catalog(query,topic,date,budget):
    self.assertEqual(budget.documents_left,6)
    return list(fragments.values())
   with patch.object(lib.library,'search',catalog),patch.object(lib.library,'read',side_effect=lambda fid,date:fragments[fid]),patch('land_assistant.legal.source_discovery.discover_roots',AsyncMock()) as web:
    result=asyncio.run(lib.search(LAND_ACQUISITION_QUERY,'land',day,RequestBudget(),refresh=True))
   self.assertEqual(len(result),4);web.assert_not_awaited()
 def test_long_articles_do_not_crowd_out_one_of_the_four_procedure_sources(self):
  from unittest.mock import patch
  numbers=['39.14','39.15','39.3','11.10'];urls={n:LAND+str(i)*40+'/' for i,n in enumerate(numbers,1)}
  class HTTP:
   async def fetch(self,url,**kw):return DocumentPage(url,200,{},'fixture','2026-11-05T00:00:00+00:00')
  def parsed(page,**kw):
   meta={'title':'Земельный кодекс','edition_label':'Последняя редакция','act_designation':'136-ФЗ','effective_from':'2026-01-01','scope_note':''}
   if page.canonical_url==LAND:return {**meta,'toc':[{'title':'Статья '+n+'. Правило','url':urls[n]} for n in numbers]}
   n=next(n for n,url in urls.items() if url==page.canonical_url);heading='Статья '+n+'. Правило'
   return {**meta,'title':heading,'text':heading+'\n'+'\n'.join(['Предоставление земельного участка при соблюдении условий. '*60]*3),'normative_headings':[heading]}
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp);p.joinpath('roots.json').write_text(json.dumps({'roots':[{'id':'land','url':LAND,'topics':['land'],'enabled':True}]}));lib=ConsultantLibrary(p/'roots.json',p/'cache',http=HTTP(),now=lambda:datetime(2026,11,5,1,tzinfo=timezone.utc))
    q='предоставление земельного участка государственной муниципальной собственности предварительное согласование схема расположения'
    with patch('land_assistant.legal.consultant_library.parse_document',side_effect=parsed):hits=await lib.search(q,'land','2026-11-05',RequestBudget())
    self.assertEqual({h['citation'].split('. ')[0].removeprefix('Статья ') for h in hits},set(numbers))
  asyncio.run(run())
 def test_unknown_owner_and_unset_boundaries_in_reverse_word_order(self):
  from land_assistant.legal.task_catalog import is_land_acquisition
  self.assertTrue(is_land_acquisition('Приобретение земельного участка: собственник неизвестен, границы не установлены'))
 def test_uncertain_private_ownership_is_not_a_known_private_seller(self):
  from land_assistant.legal.task_catalog import is_land_acquisition
  self.assertTrue(is_land_acquisition('Хочу купить пустой участок без границ, неизвестно, находится ли он в частной собственности'))
  self.assertFalse(is_land_acquisition('Покупка пустого участка, участок находится в частной собственности продавца'))
  self.assertFalse(is_land_acquisition('Хочу купить пустой участок, участок находится в частной собственности; границы неизвестны'))
