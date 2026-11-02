"""Opt-in sequential latency comparison; output contains metrics, never credentials or text."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from scripts.evaluate_legal import local_env
from land_assistant.config import Settings
from land_assistant.legal.mcp_client import LocalLegalMCP


def numeric_usage(usage):
    if not isinstance(usage,dict):return {}
    result={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens') if type(usage.get(k)) is int}
    details=usage.get('completion_tokens_details')
    if isinstance(details,dict) and type(details.get('reasoning_tokens')) is int:result['reasoning_tokens']=details['reasoning_tokens']
    return result


async def measure(settings,model,messages,max_tokens,timeout):
    start=time.monotonic();events=[]
    async def trace(event,info):
        # Never record info: it can contain request headers and provider payloads.
        if event.endswith('.complete') or event.endswith('.failed'):
            events.append({'event':event,'seconds':round(time.monotonic()-start,3)})
    headers={'Content-Type':'application/json'}
    if settings.llm_key:headers['Authorization']='Bearer '+settings.llm_key
    result={'model':model,'input_characters':sum(len(m['content']) for m in messages),'max_tokens':max_tokens}
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout,connect=10),follow_redirects=False) as client:
                response=await client.post(settings.llm_url,headers=headers,json={
                    'model':model,'messages':messages,'temperature':0,'max_tokens':max_tokens,
                    'response_format':{'type':'json_object'}},extensions={'trace':trace})
        result['http_status']=response.status_code
        if response.status_code==200:
            data=response.json();choice=data['choices'][0];content=choice['message'].get('content')
            result.update(finish_reason=choice.get('finish_reason') if choice.get('finish_reason') in ('stop','length','content_filter') else 'other',usage=numeric_usage(data.get('usage')),content_characters=len(content) if isinstance(content,str) else 0)
            try:result['json_object']=isinstance(json.loads(content),dict)
            except (ValueError,TypeError):result['json_object']=False
    except Exception as exc:
        result['error_type']=type(exc).__name__ if isinstance(exc,(httpx.HTTPError,TimeoutError,ValueError,KeyError,IndexError,TypeError)) else 'unexpected'
    result.update(seconds=round(time.monotonic()-start,3),events=events)
    return result


async def run(args):
    local_env();settings=Settings.from_env()
    if not settings.llm_url:raise ValueError('Set LLM_URL in the local environment.')
    short=[{'role':'system','content':'Верни только JSON.'},{'role':'user','content':'Ответь объектом {"ok":true}.'}]
    question='Какие сведения содержит градостроительный план земельного участка?'
    context=await LocalLegalMCP(ROOT/'knowledge').context(question)
    report={'sequential':True,'samples_per_pair':1,'context_available':bool(context['fragments']),'results':[]}
    profiles=[('short',short,128)]
    if context['fragments']:
        full=[{'role':'system','content':context['prompt']},{'role':'user','content':json.dumps({'original_question':question,'formulation':question,'intake':{'situation':'Общая справка','goal':'Узнать состав сведений'},'fragments':context['fragments']},ensure_ascii=False)}]
        profiles.append(('context',full,settings.llm_answer_tokens))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for profile,messages,limit in profiles:
        for model in args.models:
            row=await measure(settings,model,messages,limit,args.timeout);row['profile']=profile
            report['results'].append(row);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            print(profile,model,row.get('http_status',row.get('error_type')),row['seconds'],'s',flush=True)
            if row.get('http_status')==429:return


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Authorize paid API calls')
    parser.add_argument('--models',nargs='+',default=['deepseek-v4-pro','deepseek-v4.1-flash'])
    parser.add_argument('--timeout',type=float,default=90)
    parser.add_argument('--output',type=Path,default=ROOT/'data/llm-diagnostics/report.json')
    args=parser.parse_args()
    if not args.live:parser.error('--live is required for paid calls')
    if not 5<=args.timeout<=180:parser.error('--timeout must be between 5 and 180 seconds')
    asyncio.run(run(args))


if __name__=='__main__':main()
