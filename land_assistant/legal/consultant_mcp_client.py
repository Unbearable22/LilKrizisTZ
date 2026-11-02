"""Host-side client; passes only a legal search formulation and a bounded budget."""
import json,os,sys
from pathlib import Path
from datetime import timedelta
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from .consultant_types import SourceError
class ConsultantLegalMCP:
    def __init__(self,root,cache_root,function_id='general_legal_help'):self.root=Path(root).resolve();self.cache_root=Path(cache_root).resolve();self.function_id=function_id
    async def context(self,query,*,legal_topic,as_of_date,budget,fallback=False):
        params=StdioServerParameters(command=sys.executable,args=['-m','land_assistant.legal.mcp_server' if self.function_id=='legal_help' else 'land_assistant.legal.consultant_mcp_server','--knowledge-root',str(self.root),'--cache-root',str(self.cache_root),'--budget-json',json.dumps(budget.wire())],env={**{k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','LANG','LC_ALL','TMPDIR','TEMP','TMP')},'PYTHONPATH':str(Path(__file__).resolve().parents[2])})
        trace=['mcp.initialize'];fragments=[]
        def value(result):
            if result.isError:raise SourceError('source_parse_error')
            structured=getattr(result,'structuredContent',None)
            return structured if structured is not None else json.loads(result.content[0].text)
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=30)) as session:
                await session.initialize();prompt=await session.get_prompt(self.function_id);master='\n'.join(m.content.text for m in prompt.messages if hasattr(m.content,'text'));trace.append('mcp.prompts.get')
                if not master:raise SourceError('source_prompt_missing')
                found=value(await session.call_tool('search_verified_documents',{'query':query,'legal_topic':legal_topic,'as_of_date':as_of_date,'refresh':fallback}));trace.append('mcp.tools.search')
                for key,v in found['budget'].items():setattr(budget,key,v)
                for hit in found['fragments']:
                    fragments.append(value(await session.call_tool('read_verified_fragment',{'fragment_id':hit['id'],'as_of_date':as_of_date})));trace.append('mcp.tools.read')
                checked=min((f['last_checked_at'] for f in fragments),default=None)
                limitations=['Использованы общедоступные нормативные материалы; покрытие может быть неполным.']
                if found.get('source_errors'):limitations.append('Часть нормативных материалов не удалось загрузить или проверить; ответ ограничен доступным контекстом.')
                if any(f.get('partial') for f in fragments):limitations.append('Часть статьи или связанных норм не вошла в контекст; ответ ограничен прочитанными фрагментами.')
                return {'prompt':master,'fragments':fragments,'source_errors':found.get('source_errors',[]),'source_checked_at':checked,'limitations':limitations,'trace':trace}
