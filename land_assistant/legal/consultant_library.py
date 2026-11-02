"""Discover article links from a trusted registry, then read/cache bounded normative chunks."""
import re,json,hashlib,math
from collections import Counter
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from .consultant_http import ConsultantHTTP,allowed_url
from .consultant_types import DocumentPage,SourceError
from .consultant_cache import ConsultantCache
from .consultant_parser import parse_document
from .knowledge import terms

class ConsultantLibrary:
    def __init__(self,registry,cache_root,http=None,now=None):
        self.roots=json.loads(Path(registry).read_text())['roots'];self.cache=ConsultantCache(cache_root);self.http=http or ConsultantHTTP();self.now=now or (lambda:datetime.now(timezone.utc));self.allowed_ids=set();self.fragments=[];self.errors=[]
    async def page(self,url,budget):
        url=allowed_url(url);cached=self.cache.lookup(url);now=self.now()
        if cached and timedelta(0)<=now-datetime.fromisoformat(cached['checked_at'])<=timedelta(hours=24):return DocumentPage(**cached)
        headers={}
        if cached:
            if cached['headers'].get('etag'):headers['If-None-Match']=cached['headers']['etag']
            if cached['headers'].get('last-modified'):headers['If-Modified-Since']=cached['headers']['last-modified']
        page=await self.http.fetch(url,budget=budget,conditional_headers=headers)
        if page.status==304:
            if not cached:raise SourceError('source_parse_error')
            page=DocumentPage(url,200,{**cached['headers'],**page.headers},cached['body'],page.checked_at)
        # Never replace a previously usable page with an access challenge.
        parse_document(page,as_of_date=datetime.fromisoformat(page.checked_at).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat(),parent_metadata={'edition_status':'current','edition_label':'pending root verification'})
        self.cache.put_page(page);return page
    async def search(self,query,legal_topic,as_of_date,budget):
        if not isinstance(query,str) or not query.strip() or len(query)>1500:raise SourceError('source_invalid_query')
        today=self.now().astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
        if as_of_date!=today:raise SourceError('source_edition_unknown')
        budget.require()
        if min(budget.roots_left,budget.articles_left,budget.context_left)<=0:raise SourceError('source_budget_exhausted')
        roots=[r for r in self.roots if r.get('enabled') and legal_topic in r['topics'] and (r['id']!='enforcement' or re.search(r'исполнительн|пристав',query,re.I))]
        if not roots:raise SourceError('search_no_candidates')
        if legal_topic=='civil' and re.search(r'продаж.*недвижим',query,re.I):roots=[r for r in roots if r['id']=='civil2']
        if legal_topic=='tax' and re.search(r'продаж.*недвижим',query,re.I):roots=[r for r in roots if r['id']=='tax2']
        roots=roots[:budget.roots_left]
        words=terms(query);candidates=[];self.errors=[];self.fragments=[];self.allowed_ids=set()
        for root in roots:
            try:
                budget.take('root');page=await self.page(root['url'],budget)
                checked_day=datetime.fromisoformat(page.checked_at).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
                parsed=parse_document(page,as_of_date=checked_day)
                frequency=Counter(word for item in parsed['toc'] for word in terms(item['title']))
                for item in parsed['toc']:
                    title_words=terms(item['title']);score=sum(math.log(1+(len(parsed['toc'])+1)/(frequency[word]+1)) for word in words & title_words)/(1+.02*len(title_words))
                    if re.search(r'продаж.*недвижим',query,re.I):
                        preferred=['217.1','220','224','214.10'] if legal_topic=='tax' else ['550','551','554','555'] if legal_topic=='civil' else []
                        number=re.search(r'Статья\s+(\d+(?:\.\d+)?)',item['title'])
                        if number and number.group(1) in preferred:score+=1000-10*preferred.index(number.group(1))
                    if score:candidates.append((score,root,parsed,item))
            except SourceError as exc:
                self.errors.append(exc.code)
                if exc.code=='source_rate_limit':break
        candidates.sort(key=lambda c:(-c[0],c[3]['title']))
        candidates=[(*row,0) for row in candidates[:4]]
        seen=set()
        for _,root,parent,item,depth in candidates:
            if item['url'] in seen:continue
            seen.add(item['url'])
            if budget.articles_left<=0 or budget.context_left<100:break
            try:
                budget.take('article');page=await self.page(item['url'],budget)
                checked_day=datetime.fromisoformat(page.checked_at).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
                parsed=parse_document(page,as_of_date=checked_day,parent_metadata=parent)
                expected_article=re.search(r'Статья\s+(\d+(?:\.\d+)?)',item['title'])
                actual_article=re.search(r'Статья\s+(\d+(?:\.\d+)?)',parsed['title']+' '+parsed['text'][:500],re.I)
                if not expected_article or not actual_article or expected_article.group(1)!=actual_article.group(1) or not any(re.search(r'Статья\s+'+re.escape(expected_article.group(1))+r'(?!\d|\.\d)',heading,re.I) for heading in parsed['normative_headings']):raise SourceError('source_parse_error')
                text=parsed['text'];page_hash=hashlib.sha256((parent['edition_label']+'|'+text).encode()).hexdigest()
                # Paragraphs remain whole; a huge paragraph is not silently clipped.
                pieces=[];current='';omitted=False
                for line in text.splitlines():
                    if current and len(current)+len(line)+1>4000:pieces.append(current);current=''
                    current=(current+'\n'+line).strip()
                if current:pieces.append(current)
                for index,piece in enumerate(pieces):
                    if len(piece)>budget.context_left:omitted=True;continue
                    document_id='cp_'+root['id']+'_'+hashlib.sha256(item['url'].encode()).hexdigest()[:8]
                    fragment={'document_id':document_id,'title':parent['title'],'citation':item['title'],'act_designation':parent['act_designation'],'version':parent['edition_label'],'source_url':page.canonical_url,'effective_from':parent['effective_from'],'text':piece,'page_hash':page_hash,'part_index':index,'demo':False,'partial':len(pieces)>1 or omitted,'retrieved_at':page.checked_at,'last_checked_at':page.checked_at,'extraction_status':'verified_current','scope_note':parent['scope_note']}
                    fid=self.cache.put(fragment);self.allowed_ids.add(fid);self.fragments.append(self.cache.read(fid,as_of_date=as_of_date,now=self.now()));budget.context_left-=len(piece)
                if depth==0:
                    referenced=set(re.findall(r'стат(?:ь[а-яё]+|ей)\s+(\d+(?:\.\d+)?)',text,re.I))
                    for link in parent['toc']:
                        number=re.search(r'Статья\s+(\d+(?:\.\d+)?)',link['title'])
                        if number and number.group(1) in referenced and link['url'] not in seen and not any(c[3]['url']==link['url'] for c in candidates):candidates.append((0,root,parent,link,1))
                # Leave room for other relevant articles, not every chunk of every candidate.
                if len(self.fragments)>=8:break
            except SourceError as exc:
                self.errors.append(exc.code)
                if exc.code in ('source_rate_limit','source_budget_exhausted'):break
        self.cache.prune(self.now())
        if not self.fragments and self.errors:raise SourceError(self.errors[0])
        return [{k:v for k,v in f.items() if k!='text'} for f in self.fragments]
    def read(self,fragment_id,as_of_date):
        if fragment_id not in self.allowed_ids:raise SourceError('source_unknown_fragment')
        return self.cache.read(fragment_id,as_of_date=as_of_date,now=self.now())
