"""Explicit opt-in live QA: synthetic HTTP requests, real model and MCP. No secrets in output."""
import argparse
import asyncio
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from land_assistant.config import Settings
from land_assistant.legal.model import LiveModel
from land_assistant.legal.pipeline import LegalPipeline
from land_assistant.legal.web import make_web_handler
from land_assistant.legal.privacy import has_unverified_references
import httpx


def local_env():
    path=ROOT/'.env'
    if path.exists():
        for line in path.read_text().splitlines():
            key,sep,value=line.strip().partition('=')
            if sep and key in ('LLM_URL','LLM_API_KEY','LLM_MODEL','LLM_CLASSIFY_TIMEOUT','LLM_ANSWER_TIMEOUT','LLM_CLASSIFIER_MODEL','LLM_ANSWER_TOKENS'):
                os.environ.setdefault(key,value.strip().strip('\"\''))


async def evaluate(cases,output):
    local_env();settings=Settings.from_env();LiveModel(settings)
    records={};case_map={case['question']:case for case in cases}
    class TrackingModel(LiveModel):
        def __init__(self,record):super().__init__(settings);self.record=record
        async def _json(self,messages,**kwargs):
            self.record['model_calls']+=1
            try:
                result=await super()._json(messages,**kwargs);self.record['model_results'].append(result);return result
            except Exception as exc:
                self.record['model_error']=getattr(exc,'code',type(exc).__name__)
                cause=getattr(exc,'__cause__',None);response=getattr(cause,'response',None)
                if response is not None:self.record['provider_http_status']=response.status_code
                raise
        async def answer(self,**kwargs):
            self.record['contexts'].append(kwargs['fragments'])
            return await super().answer(**kwargs)
    class RecordingPipeline:
        demo=False
        async def run(self,question,intake,history=None):
            case=case_map[question];record={'id':case['id'],'model_calls':0,'model_results':[],'contexts':[]};records[case['id']]=record
            result=await LegalPipeline(ROOT/'knowledge',TrackingModel(record),demo=False).run(question,intake,**({"history":history} if history else {}))
            record['internal_result']=result;return result
    server=ThreadingHTTPServer(('127.0.0.1',0),make_web_handler(RecordingPipeline(),ROOT/'groundAndLaw'))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    semaphore=asyncio.Semaphore(1)
    stopped=False;stop_reason=None;consecutive_timeouts=0
    async def one(case):
        nonlocal stopped,stop_reason,consecutive_timeouts
        async with semaphore:
            if stopped:
                result={'id':case['id'],'question':case['question'],'expected_status':case['expected_status'],'status':'not_run','reason':stop_reason,'model_calls':0,'automated_pass':False}
                (output/(case['id']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
                return result
            started=time.monotonic()
            async with httpx.AsyncClient(timeout=130) as client:
                response=await client.post(f'http://127.0.0.1:{server.server_port}/api/legal-help',json={'question':case['question'],'intake':case['intake'],'chat_id':case['id'],**({'history':case['history']} if 'history' in case else {})})
            public=response.json();record=records.get(case['id'],{})
            code=record.get('internal_result',{}).get('diagnostics',{}).get('code')
            consecutive_timeouts=consecutive_timeouts+1 if code=='llm_timeout' else 0
            if code=='llm_rate_limit':stopped=True;stop_reason='provider_rate_limit'
            elif consecutive_timeouts>=3:stopped=True;stop_reason='provider_timeouts'
            expected=case['expected_status']
            status_ok=public.get('status') in (expected if isinstance(expected,list) else [expected])
            no_metadata=not {'sources','citations','trace','tasks','error_code','diagnostics'} & public.keys()
            bases=[{'title':b['title'],'citation':b['article']} for b in public.get('legal_bases',[])]
            no_refs=not any(has_unverified_references(text,bases) for text in [public.get('answer',''),*public.get('limitations',[])])
            words_ok=not case['answer_keywords'] or bool(re.search(case['answer_keywords'],public.get('answer',''),re.I))
            result={'id':case['id'],'question':case['question'],'expected_status':case['expected_status'],'status':public.get('status'),'http_status':response.status_code,'answer':public.get('answer'),'limitations':public.get('limitations',[]),'missing_fields':public.get('missing_fields',[]),'seconds':round(time.monotonic()-started,2),'model_calls':record.get('model_calls',0),'status_ok':status_ok,'no_private_metadata':no_metadata,'verified_references_only':no_refs,'legal_bases':public.get('legal_bases',[]),'diagnostic_code':code,'keywords_ok':words_ok,'automated_pass':status_ok and no_metadata and no_refs and words_ok}
            (output/(case['id']+'.private.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
            (output/(case['id']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            print(case['id'],result['status'],'PASS' if result['automated_pass'] else 'REVIEW',result['seconds'],'s',flush=True)
            return result
    try:results=await asyncio.gather(*(one(case) for case in cases))
    finally:server.shutdown();server.server_close()
    report={'model':settings.llm_model,'classifier_model':settings.llm_classifier_model or settings.llm_model,'synthetic':True,'cases':len(results),'automated_passed':sum(r['automated_pass'] for r in results),'model_calls':sum(r['model_calls'] for r in results),'manual_review_required':True,'results':results}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('TOTAL',report['automated_passed'],'/',len(results),'automated checks; manual review required.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true',help='Allow paid calls to the configured model');parser.add_argument('--cases',type=Path,default=ROOT/'examples/legal-evaluation.json');parser.add_argument('--only',nargs='*');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if not args.live:parser.error('Use --live explicitly to permit model calls.')
    cases=json.loads(args.cases.read_text())['cases']
    if args.only:cases=[c for c in cases if c['id'] in args.only]
    args.output.mkdir(parents=True,exist_ok=True);asyncio.run(evaluate(cases,args.output))

if __name__=='__main__':main()
