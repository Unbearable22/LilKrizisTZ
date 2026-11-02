import importlib.util,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('run_web',Path(__file__).resolve().parents[1]/'scripts/run_web.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
class LauncherTests(unittest.TestCase):
 def test_env_is_data_and_does_not_override_existing_environment(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'.env';p.write_text('# comment\nLLM_API_KEY="fake=a=b"\nLLM_MODEL=from-file\nX=$(echo forbidden)\n',encoding='utf-8')
   with patch.dict(os.environ,{'LLM_MODEL':'existing'},clear=True):
    launcher.load_env(p);self.assertEqual(os.environ['LLM_API_KEY'],'fake=a=b');self.assertEqual(os.environ['LLM_MODEL'],'existing');self.assertEqual(os.environ['X'],'$(echo forbidden)')
 def test_portable_python_paths(self):
  self.assertEqual(launcher.venv_python(Path('env'),windows=True),Path('env/Scripts/python.exe'))
  self.assertEqual(launcher.venv_python(Path('env'),windows=False),Path('env/bin/python'))
 def test_malformed_env_reports_line_without_value(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'.env';p.write_text('LLM_API_KEY="private\n')
   with self.assertRaises(ValueError) as e:launcher.load_env(p)
   self.assertNotIn('private',str(e.exception));self.assertIn('1',str(e.exception))
