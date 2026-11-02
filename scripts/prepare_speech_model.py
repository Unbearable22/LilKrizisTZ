"""Optional, bounded model setup. Failure must never stop text chat."""
import os,sys,time,threading
from pathlib import Path
os.environ['HF_HUB_DISABLE_XET']='1'
os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT','60')
os.environ.setdefault('HF_HUB_ETAG_TIMEOUT','30')

def prepare(model,download,validate,sleep=time.sleep):
    model=Path(model)
    for attempt in range(2):
        try:
            download('Systran/faster-whisper-small',local_dir=str(model),allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.txt'],max_workers=1)
            validate(str(model),device='cpu',compute_type='int8',cpu_threads=2,local_files_only=True)
            (model/'.ready').write_text('Validated local Whisper model\n')
            print('Voice model ready.',flush=True)
            return True
        except Exception as exc:
            print(f'Voice setup attempt {attempt+1} failed: {type(exc).__name__}',flush=True)
            if attempt==0:sleep(3)
    print('Voice unavailable. Text chat remains available; restart to retry preparation.',flush=True)
    return False

if __name__=='__main__':
    timer=threading.Timer(900,lambda:os._exit(1));timer.daemon=True;timer.start()
    try:
        from huggingface_hub import snapshot_download
        from faster_whisper import WhisperModel
        ok=prepare(sys.argv[1],snapshot_download,WhisperModel)
    finally:timer.cancel()
    sys.exit(0 if ok else 1)
