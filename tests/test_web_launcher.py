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
 def test_auto_port_avoids_other_app_and_reuses_our_server(self):
  with patch.object(launcher,'port_occupied',side_effect=lambda p:p==8080),patch.object(launcher,'app_running',return_value=False):
   self.assertEqual(launcher.choose_endpoint(8080,True),(8081,False))
   with self.assertRaises(ValueError):launcher.choose_endpoint(8080,False)
  with patch.object(launcher,'port_occupied',return_value=True),patch.object(launcher,'app_running',side_effect=lambda url:url.endswith(':8081')):
   self.assertEqual(launcher.choose_endpoint(8080,True),(8081,True))
 def test_check_config_reports_only_missing_keys(self):
  import io
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'.env').write_text('LLM_URL=\nLLM_API_KEY="private-fixture"\nLLM_MODEL=\n')
   out=io.StringIO()
   with patch.object(launcher,'ROOT',root),patch.dict(os.environ,{},clear=True),patch('sys.stdout',out),patch('os.chdir'):
    self.assertEqual(launcher.main(['--check-config']),1)
   self.assertIn('LLM_URL',out.getvalue());self.assertIn('LLM_MODEL',out.getvalue());self.assertNotIn('private-fixture',out.getvalue());self.assertIn(str(root/'.env'),out.getvalue())
 def test_speech_download_runs_in_background_and_failure_is_optional(self):
  import subprocess,io
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);out=io.StringIO()
   with patch.object(launcher,'ROOT',root),patch.dict(os.environ,{},clear=True),patch('subprocess.Popen') as proc,patch('sys.stdout',out):
    launcher.start_speech_download(Path('python'))
    self.assertEqual(proc.call_count,1);self.assertTrue(os.environ.get('SPEECH_READY_FILE'));self.assertNotIn('LLM_API_KEY',proc.call_args.kwargs['env'])
   with patch.object(launcher,'ROOT',root),patch('subprocess.Popen',side_effect=OSError('download unavailable')),patch('sys.stdout',out):
    self.assertIsNone(launcher.start_speech_download(Path('python')))
 def test_launch_identity_changes_with_code_and_model_but_not_runtime_cache(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'land_assistant').mkdir();(root/'land_assistant/app.py').write_text('first');(root/'data').mkdir()
   with patch.object(launcher,'ROOT',root),patch.dict(os.environ,{'LLM_MODEL':'first'},clear=True):
    first=launcher.launch_identity(demo=False,speech=True);(root/'data/cache').write_text('new data')
    self.assertEqual(first,launcher.launch_identity(demo=False,speech=True))
    (root/'land_assistant/app.py').write_text('second');second=launcher.launch_identity(demo=False,speech=True);self.assertNotEqual(first,second)
    os.environ['LLM_MODEL']='second';self.assertNotEqual(second,launcher.launch_identity(demo=False,speech=True))
    self.assertNotEqual(launcher.launch_identity(demo=False,speech=True),launcher.launch_identity(demo=True,speech=True))
 def test_old_server_is_not_reused_for_updated_launcher(self):
  import io
  with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{"mode":"live","launch_id":"old"}')):
   self.assertFalse(launcher.app_running('http://127.0.0.1:8080',launch_id='new'))
  with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{"mode":"live","launch_id":"new"}')):
   self.assertTrue(launcher.app_running('http://127.0.0.1:8080',launch_id='new'))
  with patch.object(launcher,'port_occupied',side_effect=lambda p:p==8080),patch.object(launcher,'app_running',return_value=False) as running:
   self.assertEqual(launcher.choose_endpoint(8080,True,launch_id='new'),(8081,False));self.assertEqual(running.call_args.kwargs['launch_id'],'new')
