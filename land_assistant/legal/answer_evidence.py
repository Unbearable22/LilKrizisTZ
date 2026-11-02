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
        if not isinstance(claim,dict) or set(claim)!={'section','text','evidence_ids','anchors'}:raise LegalError('invalid_claims')
        if not isinstance(claim['section'],str) or not re.fullmatch(r'answer|scenario:[0-2]',claim['section']):raise LegalError('invalid_claims')
        if not isinstance(claim['text'],str) or not 1<=len(claim['text'])<=20000:raise LegalError('invalid_claims')
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
    result=[];seen=set()
    for f in fragments:
        if f.get('demo'):continue
        try:
            policy=validate_source_url(f.get('source_url'))
            datetime.fromisoformat(f['last_checked_at'])
        except (LegalError,KeyError,ValueError,TypeError):continue
        key=(f['source_url'],f.get('citation',''))
        if key in seen:continue
        seen.add(key)
        result.append({'number':len(result)+1,'title':f.get('title',''),'publisher':policy.publisher,'source_kind':f.get('source_kind',policy.source_kind),'url':f['source_url'],'citation':f.get('citation',''),'revision':f.get('version',''),'checked_at':f['last_checked_at']})
    return result

def validate_claim_sections(result,fragments):
    claims=validate_claims(result.get('claims'),{f['id']:f for f in fragments}).accepted_claims
    expected={'answer':result['answer']}
    for i,branch in enumerate(result.get('scenarios',[])):expected['scenario:'+str(i)]=branch['condition']+' → '+branch['outcome']
    if len(claims)!=len(expected) or {c['section']:c['text'] for c in claims}!=expected:raise LegalError('invalid_claim_coverage')
