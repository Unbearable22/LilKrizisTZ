"""Small reviewed registry of official explanations; never arbitrary web URLs."""
import hashlib,re,time
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import httpx
from .consultant_parser import Tree
from .consultant_types import SourceError
FNS_SALE='https://www.nalog.gov.ru/rn77/fl/pay_taxes/land/land_sell/'
FNS_TITLE='Я продал или собираюсь продать земельный участок'
def allowed_public_url(url):
 if url!=FNS_SALE:raise SourceError('source_url_rejected')
 return url
def parse_fns(html,as_of_date):
 tree=Tree();tree.feed(html);nodes=list(tree.root.walk())
 title=next((n.text(False).strip() for n in nodes if n.tag=='h1'),'')
 body=next((n.text() for n in nodes if 'text_block' in n.attrs.get('class','').split()),'')
 update=re.search(r'Дата обновления страницы\s*(\d{2}\.\d{2}\.\d{4})',tree.root.text(False))
 if title!=FNS_TITLE or len(body)<100 or re.search(r'captcha|подтвердите.{0,20}человек|доступ запрещен',body,re.I):raise SourceError('source_parse_error')
 if not update:raise SourceError('source_edition_unknown')
 try:age=datetime.fromisoformat(as_of_date).date()-datetime.strptime(update.group(1),'%d.%m.%Y').date()
 except ValueError:raise SourceError('source_edition_unknown') from None
 if not timedelta(0)<=age<=timedelta(days=30):raise SourceError('source_edition_unknown')
 if not all(w in body.casefold() for w in ('налог','продаж','земельн')):raise SourceError('source_parse_error')
 return '\n'.join(line.strip() for line in body.splitlines() if line.strip())
async def official_fragments(query,topic,as_of_date,budget,library):
 # Registry routing uses canonical legal words only, no client identity.
 if topic!='tax' or not re.search(r'продаж|недвижим',query,re.I):return []
 today=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
 if as_of_date!=today:raise SourceError('source_edition_unknown')
 budget.take('root');started=time.monotonic()
 try:
  async with httpx.AsyncClient(follow_redirects=False,trust_env=False,timeout=min(10,budget.network_seconds_left,max(.1,budget.deadline-time.monotonic()))) as client:
   async with client.stream('GET',allowed_public_url(FNS_SALE),headers={'User-Agent':'GroundAndLaw/0.1 official public reference reader'}) as response:
    if response.status_code==429:budget.rate_limited=True;raise SourceError('source_rate_limit')
    if response.status_code!=200:raise SourceError('source_unavailable')
    data=bytearray()
    async for chunk in response.aiter_bytes():
     data.extend(chunk)
     if len(data)>2*1024*1024:raise SourceError('source_size_limit')
    text=parse_fns(bytes(data).decode('utf-8',errors='strict'),as_of_date)
 except (httpx.HTTPError,UnicodeError):raise SourceError('source_unavailable') from None
 finally:budget.network_seconds_left-=time.monotonic()-started
 budget.require()
 if len(text)>budget.context_left:raise SourceError('source_budget_exhausted')
 now=datetime.now(timezone.utc).isoformat();digest=hashlib.sha256(text.encode()).hexdigest()
 f={'document_id':'official_fns_sale','source_url':FNS_SALE,'title':'Официальное разъяснение ФНС: продажа земельного участка','citation':'Разъяснение, не нормативный акт','text':text,'source_kind':'official_explanation','version':'Страница проверена '+today+'; применимость зависит от обстоятельств','demo':False,'last_checked_at':now,'retrieved_at':now,'extraction_status':'verified_current','page_hash':digest,'part_index':0,'scope_note':'Федеральное разъяснение; не подтверждает региональные льготы, прошлые редакции или индивидуальный размер налога.'}
 fid=library.cache.put(f);library.allowed_ids.add(fid);budget.context_left-=len(text)
 return [{k:v for k,v in library.cache.read(fid,as_of_date=as_of_date,now=datetime.now(timezone.utc)).items() if k!='text'}]
