"""Parse normative content and explicit edition evidence; fail closed on unknown markup."""
from html.parser import HTMLParser
from urllib.parse import urljoin
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from .consultant_http import allowed_url
from .consultant_types import SourceError

class Node:
    def __init__(self,tag='',attrs=()):self.tag=tag;self.attrs=dict(attrs);self.children=[]
    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child,Node):yield from child.walk()
    def text(self,exclude=True):
        classes=self.attrs.get('class','')
        if self.tag in ('script','style','nav') or (exclude and any(x in classes for x in ('__toc','consultant','document__insert','document-page__insert','comment'))):return ''
        text=''.join(c.text(exclude) if isinstance(c,Node) else c for c in self.children)
        return text+('\n' if self.tag in ('p','li','div','br','h1','h2','h3') else '')
class Tree(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.root=Node();self.stack=[self.root]
    def handle_starttag(self,tag,attrs):
        node=Node(tag,attrs);self.stack[-1].children.append(node)
        if tag not in ('meta','link','br','hr','img','input','source','wbr'):self.stack.append(node)
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs);self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):self.stack[-1].children.append(data)

def iso_date(value):return datetime.strptime(value,'%d.%m.%Y').date().isoformat()
def parse_document(page,*,as_of_date,parent_metadata=None):
    tree=Tree();tree.feed(page.body);nodes=list(tree.root.walk())
    title=next((n.text(False).strip() for n in nodes if n.tag=='h1'),'')
    content=next((n for n in nodes if 'document-page__content' in n.attrs.get('class','').split()),None)
    if not title or content is None:raise SourceError('source_parse_error')
    raw=content.text().replace('\xa0',' ');text='\n'.join(line.strip() for line in raw.splitlines() if line.strip())
    if re.search(r'captcha|подтвердите.{0,20}человек|доступ.{0,15}подписк',text,re.I) or re.search(r'\bпроект\b',title,re.I):raise SourceError('source_access_restricted')
    if len(text)<10:raise SourceError('source_parse_error')
    description=' '.join(n.attrs.get('content','') for n in nodes if n.tag=='meta' and n.attrs.get('name')=='description')
    # Explicit publisher status overrides dates and inherited current metadata.
    status_text=title+' '+description+' '+text[:1000]
    if re.search(r'(?<![а-яё])(?:утратил[а-яё]*\s+силу|не\s+действует)(?![а-яё])',title+' '+description,re.I) or re.search(r'(?<![а-яё])(?:недействующ[а-яё]*|не\s+действующ[а-яё]*|архивн[а-яё]*)\s+редакци|документ\s+(?:утратил\s+силу|не\s+действует)',status_text,re.I):raise SourceError('source_edition_unknown')
    if re.search(r'(?<![а-яё])(?:обзор|комментарий|путеводитель|аналитический материал)(?![а-яё])',title,re.I):raise SourceError('source_parse_error')
    edition=re.search(r'ред\. от (\d{2}\.\d{2}\.\d{4})',title)
    effective=re.search(r'вступ\S* в силу с (\d{2}\.\d{2}\.\d{4})',title)
    checked_day=datetime.fromisoformat(page.checked_at).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
    # A current page alone cannot prove an edition for a past event.
    if as_of_date!=checked_day:raise SourceError('source_edition_unknown')
    if edition and iso_date(edition.group(1))>as_of_date or effective and iso_date(effective.group(1))>as_of_date:raise SourceError('source_edition_unknown')
    if edition:version='ред. от '+edition.group(1)
    elif re.search(r'(?<![а-яё])действующая\s+редакция(?![а-яё])',description,re.I):version='Действующая редакция по метаданным страницы; дата редакции не указана'
    elif parent_metadata and parent_metadata.get('edition_status')=='current':version=parent_metadata['edition_label']
    else:raise SourceError('source_edition_unknown')
    # Observed normative article pages repeat their heading inside doc-style.
    normative_headings=[n.text(False).strip() for n in content.walk() if 'doc-style' in n.attrs.get('class','').split() and re.search(r'Статья\s+\d',n.text(False),re.I)]
    toc=[]
    for node in nodes:
        if node.tag=='a' and re.match(r'Статья\s+\d',node.text(False).strip()):
            try:url=allowed_url(urljoin(page.canonical_url,node.attrs.get('href','')))
            except SourceError:continue
            if url.split('/')[4]!=page.canonical_url.split('/')[4]:continue
            toc.append({'title':node.text(False).strip(),'url':url})
    designation=re.search(r'(?:N|№)\s*(\d+(?:-ФЗ|-\d+)?)',title+' '+text[:250])
    return {'title':title,'act_designation':designation.group(1) if designation else '', 'edition_label':version,'edition_status':'current','effective_from':iso_date(effective.group(1)) if effective else None,'toc':toc,'normative_headings':normative_headings,'text':text,'canonical_url':page.canonical_url,'scope_note':'Дата редакции не указана на странице.' if not edition else ''}
