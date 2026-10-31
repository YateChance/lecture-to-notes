"""Local ASR after VAD; checkpoints retain decoded-to-source time mappings."""
from course_context import LESSON_ROOT as ROOT, LESSON, MODEL_PATH, MODEL_CACHE
import json,math,time,wave
import numpy as np
import mlx_whisper

OUT=ROOT/'04_transcripts';OUT.mkdir(exist_ok=True)
MODEL=str(MODEL_PATH)
PROMPT=LESSON.get('asr',{}).get('initial_prompt','以下是普通话课堂录音，请根据实际语音转写。')
CHUNK=int(LESSON.get('asr',{}).get('chunk_seconds',300))
vad=json.loads((OUT/'speech_intervals.json').read_text())
assert vad.get('complete'),'VAD must finish before ASR'

def timestamp(t,srt=False):
    ms=round(t*1000);sep=',' if srt else '.'
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d}{sep}{ms%1000:03d}'

def voiced_groups(start,end):
    groups=[]
    for item in vad['intervals']:
        a=max(start,item['start']-.15);b=min(end,item['end']+.15)
        if b<=a:continue
        if groups and a-groups[-1][1]<=3:groups[-1][1]=max(groups[-1][1],b)
        else:groups.append([a,b])
    return groups

def restore(t,mapping,end_point=False):
    for piece in mapping:
        if t<piece['decoded_end'] or (end_point and t<=piece['decoded_end']):
            return piece['source_start']+max(0,min(t-piece['decoded_start'],piece['decoded_end']-piece['decoded_start']))
    return mapping[-1]['source_end']

with wave.open(str(ROOT/'01_audio/audio.wav')) as wav:
    rate=wav.getframerate();length=wav.getnframes()/rate
    assert rate==16000 and wav.getnchannels()==1
    all_segments=[]
    for chunk,start in enumerate(range(0,math.ceil(length),CHUNK)):
        path=OUT/f'chunk_{chunk:03d}.json'
        if path.exists():result=json.loads(path.read_text())
        else:
            arrays=[];mapping=[];position=0.
            for a,b in voiced_groups(start,min(start+CHUNK,length)):
                first=round(a*rate);last=round(b*rate);wav.setpos(first)
                samples=np.frombuffer(wav.readframes(last-first),dtype=np.int16).astype(np.float32)/32768
                if not len(samples):continue
                seconds=len(samples)/rate;arrays.append(samples)
                mapping.append({'decoded_start':position,'decoded_end':position+seconds,'source_start':first/rate-start,'source_end':first/rate-start+seconds})
                position+=seconds
            began=time.monotonic();print(f'START {chunk+1} {timestamp(start)} voiced_seconds={position:.2f}',flush=True)
            if arrays:
                result=mlx_whisper.transcribe(np.concatenate(arrays),path_or_hf_repo=MODEL,language=LESSON.get('language','zh'),task='transcribe',verbose=False,condition_on_previous_text=False,initial_prompt=PROMPT,word_timestamps=False,temperature=(0.,.2,.4,.6,.8,1.))
                result['decoder_segments']=[dict(s) for s in result['segments']]
                for segment in result['segments']:
                    segment['start']=restore(max(0,segment['start']),mapping)
                    segment['end']=max(segment['start'],restore(max(0,segment['end']),mapping,True))
            else:result={'text':'','segments':[],'language':LESSON.get('language','zh'),'decoder_segments':[]}
            result.update(chunk_start=start,model_source=MODEL,vad_before_decode=True,time_mapping=mapping)
            temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2));temporary.replace(path)
            print(f'DONE {chunk+1} elapsed={time.monotonic()-began:.1f}s segments={len(result["segments"])}',flush=True)
        for segment in result['segments']:
            s=dict(segment);s['start']+=start;s['end']+=start;s['id']=len(all_segments)
            s['model_source']=result.get('model_source',str(MODEL_CACHE/'whisper-large-v3-turbo'));all_segments.append(s)
        merged={'models':sorted({s['model_source'] for s in all_segments}),'language':LESSON.get('language','zh'),'duration':length,'segments':all_segments}
        (OUT/'lecture_segments.json').write_text(json.dumps(merged,ensure_ascii=False,indent=2))
        (OUT/'lecture_timestamped.txt').write_text('\n'.join(f'[{timestamp(s["start"])} --> {timestamp(s["end"])}] {s["text"].strip()}' for s in all_segments))
        (OUT/'lecture.srt').write_text('\n\n'.join(f'{i}\n{timestamp(s["start"],True)} --> {timestamp(s["end"],True)}\n{s["text"].strip()}' for i,s in enumerate(all_segments,1)))
print('COMPLETE',len(all_segments),flush=True)
(OUT/'asr_complete.json').write_text(json.dumps({'complete':True,'chunks':math.ceil(length/CHUNK),'segments':len(all_segments),'duration':length,'vad_before_decode':True},ensure_ascii=False,indent=2))
