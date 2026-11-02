"""Explicit bounded index refresh; no LLM call, no full-site crawl."""
import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from land_assistant.legal.source_discovery import VerifiedSourceLibrary
from land_assistant.legal.consultant_types import RequestBudget
from land_assistant.legal.task_catalog import search_query,TOPICS
async def main(args):
    day=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
    library=VerifiedSourceLibrary(Path('knowledge'),Path(args.cache_dir))
    budget=RequestBudget(deadline=time.monotonic()+120)
    hits=await library.search(search_query(args.query,args.topic),args.topic,day,budget,refresh=True)
    print(__import__('json').dumps({'fragments':len(hits),'errors':library.errors,'checked_on':day},ensure_ascii=False))
    return 0 if hits else 1
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--topic',choices=sorted(TOPICS|{'land'}),required=True);parser.add_argument('--query',required=True);parser.add_argument('--cache-dir',default='data/consultant-cache')
    raise SystemExit(asyncio.run(main(parser.parse_args())))
