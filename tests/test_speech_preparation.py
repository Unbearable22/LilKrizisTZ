import importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
spec=importlib.util.spec_from_file_location('speech_setup',Path(__file__).resolve().parents[1]/'scripts/prepare_speech_model.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
class SpeechPreparationTests(unittest.TestCase):
 def test_failed_download_retries_twice_and_never_marks_ready(self):
  with tempfile.TemporaryDirectory() as d:
   download=Mock(side_effect=ConnectionError('interrupted'));validate=Mock()
   self.assertFalse(setup.prepare(d,download,validate,sleep=lambda _:None))
   self.assertEqual(download.call_count,2);validate.assert_not_called();self.assertFalse((Path(d)/'.ready').exists())
 def test_completed_download_requires_valid_model_before_ready(self):
  with tempfile.TemporaryDirectory() as d:
   download=Mock();validate=Mock(side_effect=ValueError('incomplete weights'))
   self.assertFalse(setup.prepare(d,download,validate,sleep=lambda _:None));self.assertFalse((Path(d)/'.ready').exists())
   self.assertTrue(setup.prepare(d,download,Mock(),sleep=lambda _:None));self.assertTrue((Path(d)/'.ready').exists())
