"""Validate exact textual anchors and serialize only actually read source metadata."""
from dataclasses import dataclass
from datetime import datetime
import re
from .errors import LegalError
from .trusted_sources import validate_source_url

@dataclass
class ValidationResult:
    accepted_claims: list
    rejected_claims: list
    limitations: list

def validate_claims(claims,fragments):
    if not isinstance(claims,list) or not 1<=len(claims)<=4:raise LegalError('invalid_claims')
    for claim in claims:
        if not isinstance(claim,dict) or not {'section','evidence_ids','anchors'}<=set(claim) or isinstance(claim,dict) and bool(set(claim)-{'section','text','evidence_ids','anchors'}):raise LegalError('invalid_claims')
        if not isinstance(claim['section'],str) or not re.fullmatch(r'answer|scenario:[0-2]',claim['section']):raise LegalError('invalid_claims')
        if 'text' in claim and (not isinstance(claim['text'],str) or not 1<=len(claim['text'])<=20000):raise LegalError('invalid_claims')
        ids=claim['evidence_ids'];anchors=claim['anchors']
        if not isinstance(ids,list) or not 1<=len(ids)<=6 or any(not isinstance(i,str) or i not in fragments for i in ids):raise LegalError('invalid_claims')
        if not isinstance(anchors,list) or not 1<=len(anchors)<=6:raise LegalError('invalid_claims')
        seen=set()
        for a in anchors:
            if not isinstance(a,dict) or set(a)!={'fragment_id','quote'}:raise LegalError('invalid_claims')
            fid=a['fragment_id'];quote=a['quote']
            if not isinstance(fid,str) or fid not in ids or not isinstance(quote,str) or not 15<=len(quote)<=2000 or quote not in fragments[fid]['text']:raise LegalError('invalid_claim_anchor')
            seen.add(fid)
        if seen!=set(ids):raise LegalError('invalid_claim_anchor')
    return ValidationResult(claims,[],[])

def public_evidence(fragments):
    result=[];seen={}
    for f in fragments:
        if f.get('demo'):continue
        try:
            policy=validate_source_url(f.get('source_url'))
            datetime.fromisoformat(f['last_checked_at'])
        except (LegalError,KeyError,ValueError,TypeError):continue
        key=(f['source_url'],f.get('citation',''))
        refs=[v for v in f.get('_claim_refs',[]) if isinstance(v,str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,30}/(?:answer|scenario:[0-2]|basis:[0-5])',v)]
        if key in seen:
            seen[key]['claim_ids']=sorted(set(seen[key]['claim_ids']+refs));continue
        result.append({'number':len(result)+1,'title':f.get('title',''),'publisher':policy.publisher,'source_kind':f.get('source_kind',policy.source_kind),'url':f['source_url'],'citation':f.get('citation',''),'revision':f.get('version',''),'checked_at':f['last_checked_at'],'claim_ids':refs})
        seen[key]=result[-1]
    return result

def validate_claim_sections(result,fragments):
    claims=validate_claims(result.get('claims'),{f['id']:f for f in fragments}).accepted_claims
    expected={'answer':result['answer']}
    for i,branch in enumerate(result.get('scenarios',[])):expected['scenario:'+str(i)]=branch['condition']+' → '+branch['outcome']
    if len(claims)!=len(expected) or {c['section'] for c in claims}!=set(expected) or any('text' in c and c['text']!=expected[c['section']] for c in claims):raise LegalError('invalid_claim_coverage')


def prepare_claims(result,fragments):
    """Select verbatim evidence mechanically; the model must still judge its support."""
    from .knowledge import terms
    available={f['id']:f for f in fragments}
    sections=[('answer',result.get('answer',''),result.get('citations',[]))]
    sections.extend(('scenario:'+str(i),b['condition']+' → '+b['outcome'],b.get('citations',[])) for i,b in enumerate(result.get('scenarios',[])))
    claims=[]
    for section,text,ids in sections:
        if not isinstance(ids,list):continue
        ids=list(dict.fromkeys(i for i in ids if isinstance(i,str) and i in available))[:6]
        anchors=[];candidates=[]
        for fid in ids:
            body=available[fid]['text']
            paragraphs=[line.strip() for line in body.splitlines() if 15<=len(line.strip())<=2000]
            if not paragraphs:paragraphs=[m.group().strip() for m in re.finditer(r'[^\n!?;]+[!?;]?',body) if 15<=len(m.group().strip())<=2000]
            content=[p for p in paragraphs if not re.match(r'^(?:#{1,6}\s*)?(?:Статья|Глава)\s+\d',p)]
            candidates.extend((fid,p) for p in (content or paragraphs))
        # Each sentence gets a candidate before a long secondary topic can dominate.
        sentences=[part for part in re.split(r'(?<=[.!?])\s+|\n+',text) if len(terms(part))>=2]
        seen=set()
        for sentence in sentences or [text]:
            if not candidates or len(anchors)>=6:break
            query=terms(sentence)
            fid,quote=max(candidates,key=lambda row:(len(query & terms(row[1]))/(1+.001*len(row[1])),len(row[1])))
            if (fid,quote) not in seen:
                anchors.append({'fragment_id':fid,'quote':quote});seen.add((fid,quote))
        if anchors:claims.append({'section':section,'evidence_ids':list(dict.fromkeys(a['fragment_id'] for a in anchors)),'anchors':anchors})
    return claims


def salvage_verified_sections(draft,fragments,*,scope):
    """Keep only unchanged sections explicitly approved by the semantic verifier."""
    validate_claim_sections(draft,fragments)
    verified=set(draft.get('_verified_sections',[]))
    old_claims={c['section']:c for c in draft['claims']}
    branches=[];claims=[]
    for i,branch in enumerate(draft.get('scenarios',[])):
        section='scenario:'+str(i)
        if section not in verified or section not in old_claims:continue
        claims.append({**old_claims[section],'section':'scenario:'+str(len(branches))})
        branches.append(branch)
    keep_answer='answer' in verified
    if not branches and not (keep_answer and scope=='general'):return None
    ids=list(dict.fromkeys([c for branch in branches for c in branch['citations']]+(draft.get('citations',[]) if keep_answer else [])))
    if not ids:return None
    if keep_answer:
        text=draft['answer'];main=old_claims['answer']
    else:
        text='Подтверждены приведённые ниже условные варианты. Остальную часть вопроса подтвердить не удалось.'
        main={**claims[0],'section':'answer'}
    available={f['id']:f for f in fragments}
    # Explanations from rejected sections are never copied into the public answer.
    result={'status':'partial_answer' if branches else 'answered','answer':text,'citations':ids,'limitations':['Ответ ограничен подтверждённой частью; остальные выводы не включены.'],'legal_bases':[{'fragment_id':fid,'explanation':'Нормативное основание для подтверждённой части ответа.'} for fid in ids[:6]],'claims':[{**main,'section':'answer'},*claims]}
    if branches:result.update(scenarios=branches,missing_fields=draft.get('missing_fields',[]))
    if any(fid not in available for fid in ids):raise LegalError('invalid_citations')
    validate_claim_sections(result,fragments)
    return result
