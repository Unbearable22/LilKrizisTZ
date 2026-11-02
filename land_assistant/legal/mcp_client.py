import json
import os
import sys
from pathlib import Path
from datetime import timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class LocalLegalMCP:
    def __init__(self,root,demo=False):
        self.root=Path(root).resolve()
        self.demo=demo

    async def context(self,query):
        args=['-m','land_assistant.legal.mcp_server','--knowledge-root',str(self.root)]
        if self.demo:args.append('--demo')
        env={k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','WINDIR','LANG','LC_ALL','TMPDIR','TEMP','TMP')}
        env['PYTHONPATH']=str(Path(__file__).resolve().parents[2])
        params=StdioServerParameters(command=sys.executable,args=args,env=env)
        trace=['mcp.initialize']
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=20)) as session:
                await session.initialize()
                prompt=await session.get_prompt('legal_help')
                master='\n'.join(m.content.text for m in prompt.messages if hasattr(m.content,'text'))
                trace.append('mcp.prompts.get')
                found=await session.call_tool('search_legal_fragments',{'query':query})
                trace.append('mcp.tools.search')
                def value(result):
                    if result.isError:raise ValueError('MCP не смог прочитать нормативные материалы.')
                    structured=getattr(result,'structuredContent',None)
                    return structured if structured is not None else json.loads(result.content[0].text)
                matches=value(found)['fragments']
                fragments=[];size=0
                for hit in matches[:6]:
                    result=await session.call_tool('read_legal_fragment',{'fragment_id':hit['id']})
                    fragment=value(result)
                    if size+len(fragment['text'])>16000:continue
                    fragments.append(fragment);size+=len(fragment['text'])
                    trace.append('mcp.tools.read')
                if not master:raise ValueError('MCP вернул пустой мастер-промпт.')
                reduced=len(fragments)<len(matches)
                limitations=['Объём учтённых материалов ограничен; ответ не является исчерпывающим анализом ситуации.'] if reduced else []
                if any(f.get('partial') for f in fragments):limitations.append('Учтена часть доступных материалов; отдельные условия могут требовать дополнительного разбора.')
                return {'prompt':master,'fragments':fragments,'trace':trace,'context_reduced':reduced,'limitations':limitations}
