"""Public publisher search: candidates only, never search snippets as evidence."""
import json
import re
import time
from urllib.parse import parse_qs,urlencode,urljoin,urlsplit
from .consultant_parser import Tree
from .consultant_types import SourceError
from .trusted_sources import validate_source_url
from .trusted_http import fetch_document

SEARCH='https://www.consultant.ru/search/'

def validate_search_url(url):
    try:
        p=urlsplit(url)
        query=parse_qs(p.query,strict_parsing=True)
        if (p.scheme!='https' or p.hostname!='www.consultant.ru' or p.username or p.password
            or p.port not in (None,443) or p.path!='/search/' or p.fragment or set(query)!={'q'}
            or len(query['q'])!=1 or not 1<=len(query['q'][0].strip())<=1500
            or any(ord(c)<32 for c in url) or re.search(r'%(?![0-9a-fA-F]{2})',p.query)):
            raise ValueError()
    except (ValueError,TypeError,AttributeError):raise SourceError('source_url_rejected') from None

def parse_results(value,topic):
    if not isinstance(value,dict) or value.get('ready') is not True:raise SourceError('search_not_ready')
    html=value.get('results')
    if not isinstance(html,str) or value.get('error'):raise SourceError('source_parse_error')
    tree=Tree();tree.feed(html);roots=[];seen=set()
    for node in tree.root.walk():
        if 'search-results__item' not in node.attrs.get('class','').split() or node.attrs.get('data-avail')!='yes':continue
        for link in node.walk():
            if link.tag!='a' or 'search-results__link' not in link.attrs.get('class','').split():continue
            url=urljoin(SEARCH,link.attrs.get('href',''))
            try:validate_source_url(url)
            except SourceError:continue
            match=re.fullmatch(r'https://www\.consultant\.ru/document/cons_doc_LAW_(\d+)/',url)
            if not match or url in seen:continue
            seen.add(url);roots.append({'id':'web_'+match.group(1),'url':url,'topics':[topic],
                'label':' '.join(link.text(False).split())[:300],'enabled':True})
            if len(roots)>=4:return roots
    return roots

async def discover_roots(query,topic,budget):
    budget.require()
    if budget.discovery_left<=0 or budget.documents_left<=0:raise SourceError('source_budget_exhausted')
    budget.discovery_left-=1;budget.documents_left-=1;started=time.monotonic()
    url=SEARCH+'?'+urlencode({'q':query});validate_search_url(url)
    try:
        page=await fetch_document(url,deadline=min(budget.deadline,time.monotonic()+budget.network_seconds_left),discovery=True)
        if page.content_type!='application/json':raise SourceError('source_parse_error')
        try:return parse_results(json.loads(page.body),topic)
        except (ValueError,UnicodeError):raise SourceError('source_parse_error') from None
    except SourceError as exc:
        if exc.code=='source_rate_limit':budget.rate_limited=True
        raise
    finally:budget.network_seconds_left-=time.monotonic()-started
