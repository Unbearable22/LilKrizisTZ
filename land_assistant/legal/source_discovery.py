"""Direct discovery from publisher TOCs and a verified local index, no search API."""
from collections import defaultdict
import re
from pathlib import Path
from .consultant_library import ConsultantLibrary
from .consultant_types import SourceError
from .source_index import SourceIndex
from .source_documents import VerifiedDocument
from .public_sources import official_fragments

class VerifiedSourceLibrary:
    def __init__(self,root,cache_root):
        self.root=Path(root);self.library=ConsultantLibrary(self.root/'consultant/roots.json',cache_root)
        self.index=SourceIndex(Path(cache_root)/'verified-index.sqlite');self.allowed_ids=set();self.errors=[];self.coverage_gaps=[]
    async def search(self,query,legal_topic,as_of_date,budget,refresh=False):
        self.errors=[];self.coverage_gaps=[]
        allowed_roots=[r['url'] for r in self.library.roots if r.get('enabled') and legal_topic in r['topics']]
        hits=[] if refresh else [f for f in self.index.search(query,8,as_of_date) if any(f['source_url'].startswith(url) for url in allowed_roots)]
        if hits and self.covered(query,legal_topic,hits):
            selected=[]
            for f in hits:
                if budget.articles_left<=0:break
                if len(f['text'])>budget.context_left:continue
                budget.take('article');budget.context_left-=len(f['text']);selected.append(f)
            self.allowed_ids={f['id'] for f in selected}
            return [{k:v for k,v in f.items() if k!='text'} for f in selected]
        if budget.discovery_left<=0:raise SourceError('source_budget_exhausted')
        budget.discovery_left-=1
        found=[]
        try:found=await self.library.search(query,legal_topic,as_of_date,budget)
        except SourceError as exc:
            self.errors.append(exc.code)
            if exc.code=='source_rate_limit':raise
        self.errors.extend(self.library.errors)
        if not found and not budget.rate_limited:
            try:found=await official_fragments(query,legal_topic,as_of_date,budget,self.library)
            except SourceError as exc:self.errors.append(exc.code)
        groups=defaultdict(list)
        for f in found:
            fragment=self.library.read(f['id'],as_of_date);groups[fragment['source_url']].append(fragment)
        for url,parts in groups.items():
            f=parts[0]
            self.index.upsert(VerifiedDocument(url,f['title'],'ФНС России' if f.get('source_kind')=='official_explanation' else 'КонсультантПлюс',f.get('source_kind','normative_act'),'guidance' if f.get('source_kind')=='official_explanation' else 'current',f['version'],f['last_checked_at'],[{'text':p['text'],'citation':p.get('citation',''),'partial':p.get('partial',False),'scope_note':p.get('scope_note',''),'act_designation':p.get('act_designation','')} for p in parts]))
        if found and not self.covered(query,legal_topic,[self.library.read(f['id'],as_of_date) for f in found]):self.coverage_gaps=['Не найдены все необходимые основания по текущей теме; ответ ограничен прочитанной частью.']
        self.allowed_ids={f['id'] for f in found}
        return found
    @staticmethod
    def covered(query,topic,fragments):
        if topic=='family' and 'алиментов' in query and 'несовершеннолетних детей' in query:
            numbers={m.group(1) for f in fragments if (m:=re.search(r'Статья\s+(\d+)(?!\d|\.\d)',f.get('citation',''),re.I))}
            return {'80','81','83'}<=numbers
        if topic!='consumer' or not re.search(r'недостат|отсутствие.*чек',query,re.I):return True
        rights=[f for f in fragments if re.search(r'Статья\s+18(?!\d|\.\d)',f.get('citation',''),re.I)]
        if not rights:return False
        text=' '.join(f.get('text','') for f in rights).casefold()
        if not re.search(r'вправе|потребова|своему выбору',text):return False
        return 'чек' not in query.casefold() or 'чек' in text
    def read(self,fragment_id,as_of_date):
        if fragment_id not in self.allowed_ids:raise SourceError('source_unknown_fragment')
        if fragment_id.startswith('idx_'):
            fragment=self.index.read(fragment_id,as_of_date)
            if fragment is None:raise SourceError('source_edition_unknown')
            return fragment
        return self.library.read(fragment_id,as_of_date)
