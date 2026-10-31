from course_context import LESSON_ROOT, LESSON, MODEL_PATH, MODEL_CACHE
from pathlib import Path
import wave,json
import numpy as np
import torch
from silero_vad import load_silero_vad,get_speech_timestamps

root=LESSON_ROOT
torch.set_num_threads(1)
model=load_silero_vad()
intervals=[]
with wave.open(str(root/'01_audio/audio.wav')) as wav:
 rate=wav.getframerate(); duration=wav.getnframes()/rate
 for start in range(0,int(duration)+1,600):
  wav.setpos(start*rate)
  audio=torch.from_numpy(np.frombuffer(wav.readframes(600*rate),dtype=np.int16).astype(np.float32)/32768)
  if not len(audio):break
  segs=get_speech_timestamps(audio,model,sampling_rate=rate,return_seconds=True,threshold=0.5,min_silence_duration_ms=400,speech_pad_ms=150)
  intervals.extend({'start':s['start']+start,'end':s['end']+start} for s in segs)
  (root/'04_transcripts/speech_intervals.json').write_text(json.dumps({'duration':duration,'complete':start+600>=duration,'intervals':intervals},ensure_ascii=False,indent=2))
  print('VAD',start,min(start+600,duration),len(segs),flush=True)
