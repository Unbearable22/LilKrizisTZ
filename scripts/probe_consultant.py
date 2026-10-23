"""Bounded public-source probe, never a recursive site crawler."""
import argparse,asyncio,json,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from land_assistant.legal.consultant_http import ConsultantHTTP
from land_assistant.legal.consultant_types import RequestBudget,SourceError
from land_assistant.legal.consultant_parser import parse_document
async def probe(output):
 http=ConsultantHTTP();results=[];output.mkdir(parents=True,exist_ok=True)
 for root in json.loads(Path('knowledge/consultant/roots.json').read_text())['roots']:
  try:
   page=await http.fetch(root['url'],budget=RequestBudget());parsed=parse_document(page,as_of_date=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat())
   (output/(root['id']+'.html')).write_text(page.body)
   row={'id':root['id'],'status':'available','url':root['url'],'title':parsed['title'],'edition':parsed['edition_label'],'articles':len(parsed['toc'])}
  except SourceError as exc:row={'id':root['id'],'status':exc.code,'url':root['url']}
  results.append(row);print(root['id'],row['status'],flush=True)
 (output/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();asyncio.run(probe(a.output))
