"""Isolated CPU Whisper worker; stdin audio, stdout JSON, no audio files."""
import io,json,sys
import av,numpy as np
from faster_whisper import WhisperModel

def decode_limited(body):
 samples=[];count=0
 with av.open(io.BytesIO(body)) as container:
  stream=container.streams.audio[0]
  resampler=av.AudioResampler(format='fltp',layout='mono',rate=16000)
  def append(frame):
   nonlocal count
   a=frame.to_ndarray().flatten();count+=len(a)
   # Allow one second for recorder/container finalization.
   if count>121*16000:raise ValueError('duration')
   samples.append(a)
  for frame in container.decode(stream):
   for output in resampler.resample(frame):append(output)
  for output in resampler.resample(None):append(output)
 if not samples:raise ValueError('empty')
 return np.concatenate(samples)

def main():
 audio=decode_limited(sys.stdin.buffer.read(8*1024*1024+1))
 model=WhisperModel(sys.argv[1],device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
 segments,_=model.transcribe(audio,language='ru',beam_size=3,vad_filter=True,condition_on_previous_text=False)
 text=' '.join(s.text.strip() for s in segments if s.no_speech_prob<.6)
 print(json.dumps({'text':text},ensure_ascii=False))
if __name__=='__main__':
 try:main()
 except Exception:sys.exit(2)
