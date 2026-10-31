"""Create a timestamp index from existing speech segments and observed video frames."""
from pathlib import Path
import csv
import json
import subprocess

from course_context import LESSON_ROOT as root

out = root / '06_timeline'
out.mkdir(exist_ok=True)
sources=[json.loads(line) for line in (root/'00_sources/sources.jsonl').read_text().splitlines() if line.strip()]
video_source=next((item for item in reversed(sources) if item.get('path')=='00_sources/video/lecture.mp4'),None)
if not video_source or not video_source.get('source_id'):
    raise RuntimeError('来源登记中缺少当前视频及source_id，不能生成伪造引用')
video_source_id=video_source['source_id']
audio = json.loads((root / '04_transcripts/lecture_segments_clean.json').read_text())
probe = json.loads(subprocess.check_output([
    'ffprobe', '-v', 'error', '-show_entries',
    'format=duration,size:stream=index,codec_type,codec_name,width,height,start_time,sample_rate',
    '-of', 'json', str(root / '00_sources/video/lecture.mp4')], text=True))
duration_ms = round(float(probe['format']['duration']) * 1000)
starts={s['codec_type']:float(s.get('start_time',0)) for s in probe['streams'] if s['codec_type'] in {'video','audio'}}
if any(abs(value)>0.001 for value in starts.values()):
    raise RuntimeError('当前时间轴入口只验证了音视频从0开始的素材；请先实现非零起点偏移映射，不能假称已对齐。')
probe.update({'video_source': '00_sources/video/lecture.mp4', 'audio_source': '01_audio/audio.wav',
              'audio_offset_ms': 0, 'note': '两个原始流start_time均为0；当前音轨未裁剪。'})
(root / '01_audio/media.json').write_text(json.dumps(probe, ensure_ascii=False, indent=2))
events = []
for i, segment in enumerate(audio['segments']):
    events.append({'schema_version': '1.0', 'event_id': f'speech_{i:06d}', 'kind': 'speech_candidate',
                   'start_ms': round(segment['start'] * 1000), 'end_ms': round(segment['end'] * 1000),
                   'text': segment['text'], 'review_flag': segment.get('review_flag'),
                   'artifact': '04_transcripts/lecture_segments_clean.json', 'source_segment_id': segment['id']})
rows = list(csv.DictReader((root / '02_frames/帧索引.csv').open(encoding='utf-8-sig')))
ocr = {x['file']: x for x in (json.loads(line) for line in (root / '03_board/raw/ocr_raw.jsonl').read_text().splitlines())}
frame_events = []
for i, row in enumerate(rows):
    start = round(float(row['时间秒']) * 1000)
    end = round(float(rows[i + 1]['时间秒']) * 1000) if i + 1 < len(rows) else duration_ms
    board = ocr[Path(row['板书裁剪图']).name]
    event = {'schema_version': '1.0', 'event_id': f'frame_{i+1:04d}', 'kind': 'board_frame',
             'start_ms': start, 'end_ms': end, 'source_time_seconds': float(row['时间秒']),
             'full_image': '02_frames/' + row['原图'], 'board_image': '02_frames/' + row['板书裁剪图'],
             'ocr_text': '\n'.join(line['text'] for line in board['lines']),
             'ocr_reviewed': False, 'source_id': video_source_id}
    frame_events.append(event)
events.extend(frame_events)
events.sort(key=lambda e: (e['start_ms'], e['event_id']))
for event in events:
    assert 0 <= event['start_ms'] <= event['end_ms'] <= duration_ms
(out / 'events.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in events))
(root / '02_frames/frames.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in frame_events))
segments = []
for start in range(0, duration_ms, 300000):
    end = min(duration_ms, start + 300000)
    refs = [x for x in events if x['start_ms'] < end and x['end_ms'] > start]
    segments.append({'schema_version': '1.0', 'segment_id': f'window_{len(segments):03d}',
                     'start_ms': start, 'end_ms': end,
                     'speech_refs': [x['event_id'] for x in refs if x['kind'] == 'speech_candidate'],
                     'frame_refs': [x['event_id'] for x in refs if x['kind'] == 'board_frame'],
                     'document_refs': [], 'semantic_alignment_reviewed': False})
(out / 'segments.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in segments))
(out / 'source_links.jsonl').write_text('')
lines = ['# 时间戳汇总', '', '按原视频时间汇总语音与图片，5分钟一组。此文件是确定性的时间索引，不表示已完成每一句语音与每条公式的语义对应。原语音和OCR候选仍可能有误；正式内容见record和报告。未提供课件或教材，故没有资料页码关联。', '',
         '| 视频区间 | 语音片段数 | 图片数 |', '|---|---:|---:|']
for segment in segments:
    def stamp(ms):
        sec = ms // 1000
        return f'{sec//3600:02d}:{sec//60%60:02d}:{sec%60:02d}'
    lines.append(f'| {stamp(segment["start_ms"])}—{stamp(segment["end_ms"])} | {len(segment["speech_refs"])} | {len(segment["frame_refs"])} |')
(out / 'timeline.md').write_text('\n'.join(lines) + '\n')
(out / 'summary.json').write_text(json.dumps({'events': len(events), 'frames': len(frame_events),
    'speech_segments': len(audio['segments']), 'windows': len(segments), 'duration_ms': duration_ms,
    'semantic_alignment_reviewed': False}, ensure_ascii=False, indent=2))
print('Created timeline:', len(events), 'events;', len(segments), 'windows')
