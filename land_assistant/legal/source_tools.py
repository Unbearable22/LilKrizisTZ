"""Same read-only source capabilities, attached to each business MCP independently."""
from .source_discovery import VerifiedSourceLibrary
from .consultant_types import SourceError

def attach_source_tools(server,root,cache_root,budget):
    library=VerifiedSourceLibrary(root,cache_root)
    @server.tool()
    async def search_verified_documents(query:str,legal_topic:str,as_of_date:str,refresh:bool=False)->dict:
        try:
            found=await library.search(query,legal_topic,as_of_date,budget,refresh)
            return {'fragments':found,'source_errors':list(dict.fromkeys(library.errors)),'coverage_gaps':library.coverage_gaps,'budget':budget.wire()}
        except SourceError as exc:return {'fragments':[],'source_errors':[exc.code],'budget':budget.wire()}
    @server.tool()
    def read_verified_fragment(fragment_id:str,as_of_date:str)->dict:
        return library.read(fragment_id,as_of_date)
