"""Opt-in bounded stream diagnostic of one recorded synthetic QA verification.

Records timings, counts and a safe provider request ID, never model/user text.
The result is diagnostic only: it cannot publish or approve a chat response.
"""
import argparse
import asyncio
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from scripts.evaluate_legal import local_env
from scripts.diagnose_llm import numeric_usage
from land_assistant.config import Settings
from land_assistant.legal.model import LiveModel


async def measure(settings,messages,*,model,effort='',timeout=30):
    start=time.monotonic();pieces=[];seen_bytes=0
    row={'model':model,'reasoning_effort':effort or 'provider_default','stream':True,
         'input_characters':sum(len(m['content']) for m in messages)}
    body={'model':model,'temperature':0,'max_tokens':settings.llm_answer_tokens,
          'response_format':{'type':'json_object'},'messages':messages,
          'stream':True,'stream_options':{'include_usage':True}}
    if effort:body['reasoning_effort']=effort
    headers={'Content-Type':'application/json'}
    if settings.llm_key:headers['Authorization']='Bearer '+settings.llm_key
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout,connect=min(10,timeout)),follow_redirects=False) as client:
                async with client.stream('POST',settings.llm_url,headers=headers,json=body) as response:
                    row.update(http_status=response.status_code,headers_seconds=round(time.monotonic()-start,3))
                    request_id=response.headers.get('x-request-id','')
                    if re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',request_id):row['request_id']=request_id
                    response.raise_for_status()
                    done=False
                    async for line in response.aiter_lines():
                        seen_bytes+=len(line.encode('utf-8'))
                        if seen_bytes>256000:row['error_type']='response_size';break
                        if not line.startswith('data:'):continue
                        data=line[5:].strip()
                        if data=='[DONE]':done=True;break
                        chunk=json.loads(data)
                        if chunk.get('usage'):row['usage']=numeric_usage(chunk['usage'])
                        for choice in chunk.get('choices',[]):
                            delta=choice.get('delta',{})
                            if delta.get('reasoning_content') or delta.get('reasoning'):
                                row.setdefault('first_reasoning_seconds',round(time.monotonic()-start,3))
                            if isinstance(delta.get('content'),str) and delta['content']:
                                row.setdefault('first_content_seconds',round(time.monotonic()-start,3));pieces.append(delta['content'])
                            if choice.get('finish_reason') in ('stop','length','content_filter'):row['finish_reason']=choice['finish_reason']
                    if not done or row.get('finish_reason')!='stop':row.setdefault('error_type','incomplete_stream')
                    if 'error_type' not in row:
                        value=json.loads(''.join(pieces));row['json_object']=isinstance(value,dict)
                        if isinstance(value,dict) and type(value.get('supported')) is bool:
                            row['supported']=value['supported']
                            for field in ('supported_sections','issues'):
                                if isinstance(value.get(field),list):row[field[:-1]+'_count']=len(value[field])
    except (httpx.HTTPError,TimeoutError,ValueError,KeyError,TypeError,AttributeError) as exc:
        row['error_type']=type(exc).__name__
    row.update(seconds=round(time.monotonic()-start,3),content_characters=sum(map(len,pieces)))
    return row


async def run(args):
    local_env();settings=Settings.from_env()
    # This is an operator-selected existing QA record, not a user-provided URL.
    if args.record.stat().st_size>4*1024*1024:raise ValueError('QA record exceeds 4 MiB')
    record=json.loads(args.record.read_text())
    plan=next(r for r in record['model_results'] if r.get('tasks'))
    if len(plan['tasks'])!=1 or len(record['contexts'])!=1:
        raise ValueError('Select a one-task QA record with one answer context for an unambiguous replay.')
    draft=next(r for r in record['model_results'] if r.get('status') in ('answered','partial_answer'))
    class Capture(LiveModel):
        async def _json(self,messages,**kwargs):self.messages=messages;return {'supported':False}
    capture=Capture(settings)
    await capture.verify_evidence(result=draft,fragments=record['contexts'][0],
        formulation=plan['tasks'][0]['formulation'],
        original_question=record.get('internal_result',{}).get('question',''),intake=plan.get('known_fields',{}))
    row=await measure(settings,capture.messages,model=args.model or settings.llm_verifier_model or settings.llm_model,
        effort=args.reasoning_effort,timeout=args.timeout)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(row,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Authorize one paid API call')
    parser.add_argument('--record',type=Path,required=True,help='Private JSON from synthetic evaluate_legal run')
    parser.add_argument('--model',default='')
    parser.add_argument('--reasoning-effort',choices=('','low','medium','high'),default='')
    parser.add_argument('--timeout',type=float,default=30)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.live:parser.error('--live is required for a paid call')
    if not 5<=args.timeout<=30:parser.error('--timeout must be between 5 and 30 seconds')
    if args.output.exists():parser.error('Output exists: choose a new path to preserve earlier measurements')
    asyncio.run(run(args))


if __name__=='__main__':main()
