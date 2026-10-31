from course_context import LESSON_ROOT, LESSON, MODEL_PATH, MODEL_CACHE
from pathlib import Path
import json, time, wave
import numpy as np
import mlx_whisper

ROOT = LESSON_ROOT
OUT = ROOT / '04_transcripts'
MODEL = str(MODEL_PATH)
PROMPT = '以下是普通话动力系统课程。一维微分方程，不动点，平衡点，稳定性，鞍结分岔，跨临界分岔，叉式分岔，超临界，亚临界，泰勒展开，无量纲化，磁滞效应。'

PROMPT = LESSON.get('asr', {}).get('initial_prompt', PROMPT)

def timestamp(t, srt=False):
    ms = round(t * 1000)
    sep = ',' if srt else '.'
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d}{sep}{ms%1000:03d}'

with wave.open(str(ROOT / '01_audio/audio.wav')) as wav:
    rate = wav.getframerate()
    length = wav.getnframes() / rate
    all_segments = []
    for chunk, start in enumerate(range(0, int(length) + 1, 300)):
        path = OUT / f'chunk_{chunk:03d}.json'
        if path.exists():
            result = json.loads(path.read_text())
        else:
            wav.setpos(start * rate)
            audio = np.frombuffer(wav.readframes(300 * rate), dtype=np.int16).astype(np.float32) / 32768
            if not len(audio): break
            began = time.monotonic()
            print(f'START {chunk+1} {timestamp(start)}', flush=True)
            result = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL,
                language='zh', task='transcribe', verbose=False,
                condition_on_previous_text=False, initial_prompt=PROMPT,
                word_timestamps=False, temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0))
            result['chunk_start'] = start
            result['model_source'] = MODEL
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(f'DONE {chunk+1} elapsed={time.monotonic()-began:.1f}s segments={len(result["segments"])}', flush=True)
        for segment in result['segments']:
            s = dict(segment)
            s['start'] += start
            s['end'] += start
            s['id'] = len(all_segments)
            s['model_source'] = result.get('model_source', str(MODEL_CACHE / 'whisper-large-v3-turbo'))
            all_segments.append(s)
        (OUT / 'lecture_segments.json').write_text(json.dumps({'models': sorted({s['model_source'] for s in all_segments}), 'language':'zh','duration':length,'segments': all_segments}, ensure_ascii=False, indent=2))
        (OUT / 'lecture_timestamped.txt').write_text('\n'.join(f'[{timestamp(s["start"])} --> {timestamp(s["end"])}] {s["text"].strip()}' for s in all_segments))
        (OUT / 'lecture.srt').write_text('\n\n'.join(f'{i}\n{timestamp(s["start"], True)} --> {timestamp(s["end"], True)}\n{s["text"].strip()}' for i,s in enumerate(all_segments,1)))
print('COMPLETE', len(all_segments), flush=True)
