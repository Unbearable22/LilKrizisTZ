"""Bounded local transcription. Audio travels over stdin and is never saved."""
import json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MAX_BYTES=8*1024*1024
class SpeechError(Exception):pass
def speech_python():
 configured=os.getenv('SPEECH_PYTHON')
 if configured:return Path(configured)
 return ROOT/('.venv-speech/Scripts/python.exe' if os.name=='nt' else '.venv-speech/bin/python')
def available():
 if os.getenv('SPEECH_DISABLED')=='1':return False
 ready=os.getenv('SPEECH_READY_FILE')
 if ready and not Path(ready).is_file():return False
 return speech_python().is_file() and (ROOT/'data/speech-model/model.bin').is_file()
def transcribe(body,mime):
 if not body or len(body)>MAX_BYTES:raise SpeechError('Запись пуста или превышает 8 МиБ.')
 if mime.split(';')[0].strip() not in ('audio/webm','audio/ogg','audio/mp4','audio/wav'):raise SpeechError('Этот формат записи не поддерживается.')
 if not available():raise SpeechError('Распознавание ещё не готово. Введите вопрос текстом.')
 try:
  result=subprocess.run([str(speech_python()),str(ROOT/'scripts/transcribe_local.py'),str(ROOT/'data/speech-model')],input=body,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=90,env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','SYSTEMROOT')})
  if result.returncode:raise SpeechError('Не удалось прочитать запись. Попробуйте записать ещё раз.')
  text=json.loads(result.stdout)['text'].strip()
  if not text:raise SpeechError('Речь не обнаружена. Попробуйте говорить ближе к микрофону.')
  if len(text)>8000:raise SpeechError('Распознанный текст слишком длинный. Запишите вопрос короче.')
  return text
 except subprocess.TimeoutExpired:raise SpeechError('Распознавание заняло слишком много времени. Попробуйте более короткую запись.') from None
 except (ValueError,KeyError,OSError):raise SpeechError('Не удалось распознать запись. Введите вопрос текстом.') from None
