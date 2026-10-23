"""A dedicated, read-only stdio MCP for the legal_help function."""
import argparse
from mcp.server.fastmcp import FastMCP
from .knowledge import Knowledge


def create_server(root,demo=False):
    library=Knowledge(root,demo=demo)
    server=FastMCP('groundAndLaw-legal-help',log_level='ERROR')

    @server.prompt(name='legal_help')
    def legal_help() -> str:
        """Get the legal-help master prompt from its trusted local .txt file."""
        return library.prompt()

    @server.tool()
    def search_legal_fragments(query:str) -> dict:
        """Find available normative fragments. Returns IDs and provenance, not conclusions."""
        return {'fragments':library.search(query)}

    @server.tool()
    def read_legal_fragment(fragment_id:str) -> dict:
        """Read a known current fragment by ID, never by a caller-supplied file path."""
        return library.read(fragment_id)

    return server


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--knowledge-root',required=True)
    parser.add_argument('--demo',action='store_true')
    args=parser.parse_args()
    create_server(args.knowledge_root,args.demo).run(transport='stdio')
