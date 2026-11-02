"""Dedicated public Consultant read-only MCP. Model keys never enter this process."""
import argparse,json
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from .consultant_library import ConsultantLibrary
from .consultant_types import RequestBudget,SourceError
from .public_sources import official_fragments

def create_server(root,cache_root,budget=None):
    root=Path(root);library=ConsultantLibrary(root/'consultant/roots.json',cache_root);budget=budget or RequestBudget();server=FastMCP('consultant-general-legal',log_level='ERROR')
    @server.prompt(name='general_legal_help')
    def general_legal_help()->str:
        text=(root/'prompts/general_legal_help.txt').read_text().strip()
        if not text or len(text)>20000:raise ValueError('Промпт отсутствует или слишком велик.')
        return text
    @server.tool()
    async def search_consultant_fragments(query:str,legal_topic:str,as_of_date:str)->dict:
        try:
            fragments=await library.search(query,legal_topic,as_of_date,budget)
            return {'fragments':fragments,'source_errors':library.errors,'budget':budget.wire()}
        except SourceError as exc:return {'fragments':[],'source_errors':[exc.code],'budget':budget.wire()}
    @server.tool()
    async def search_verified_public_fragments(query:str,legal_topic:str,as_of_date:str)->dict:
        try:
            fragments=await official_fragments(query,legal_topic,as_of_date,budget,library)
            if not fragments:fragments=await library.search(query,legal_topic,as_of_date,budget)
            return {'fragments':fragments,'source_errors':library.errors,'budget':budget.wire()}
        except SourceError as exc:return {'fragments':[],'source_errors':[exc.code],'budget':budget.wire()}
    @server.tool()
    def read_consultant_fragment(fragment_id:str,as_of_date:str)->dict:return library.read(fragment_id,as_of_date)
    return server
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--knowledge-root',required=True);p.add_argument('--cache-root',required=True);p.add_argument('--budget-json',default='{}');args=p.parse_args()
    create_server(args.knowledge_root,args.cache_root,RequestBudget(**json.loads(args.budget_json))).run(transport='stdio')
