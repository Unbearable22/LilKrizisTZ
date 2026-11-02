import asyncio,tempfile,unittest
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from land_assistant.legal.consultant_mcp_client import ConsultantLegalMCP
from land_assistant.legal.consultant_types import RequestBudget
class MCPTests(unittest.TestCase):
 def test_real_stdio_handshake_and_dedicated_prompt_without_network(self):
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'consultant').mkdir();(root/'prompts').mkdir()
    (root/'consultant/roots.json').write_text('{"roots":[]}');(root/'prompts/general_legal_help.txt').write_text('Отвечай только по прочитанным нормам.')
    result=await ConsultantLegalMCP(root,root/'cache').context('Наследство',legal_topic='inheritance',as_of_date=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat(),budget=RequestBudget(discovery_left=1))
    self.assertIn('mcp.initialize',result['trace']);self.assertEqual(result['fragments'],[]);self.assertEqual(result['source_errors'],['search_no_candidates'])
  asyncio.run(run())
