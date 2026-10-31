from course_context import LESSON_ROOT, LESSON, MODEL_PATH, MODEL_CACHE
from pathlib import Path
import math
import json,csv,re,shutil

root=LESSON_ROOT;out=root/'04_transcripts'
data=json.loads((out/'lecture_segments.json').read_text())
vad=json.loads((out/'speech_intervals.json').read_text())
assert vad['complete']
assert len(list(out.glob('chunk_*.json')))==math.ceil(data['duration']/LESSON.get('asr',{}).get('chunk_seconds',300)),'整课转写尚未完成'

def ts(t,srt=False):
 m=round(t*1000);sep=',' if srt else '.'
 return f'{m//3600000:02d}:{m//60000%60:02d}:{m//1000%60:02d}{sep}{m%1000:03d}'

for name in ['lecture_timestamped.txt','lecture.srt','lecture_segments.json']:
 p=out/name;raw=p.with_name(p.stem+'_raw'+p.suffix)
 if not raw.exists():shutil.copy2(p,raw)

terms={'安结分叉':'鞍结分岔','鞍结分叉':'鞍结分岔','鞍节分叉':'鞍结分岔','安节分叉':'鞍结分岔','安捷分叉':'鞍结分岔','鞍节分岔':'鞍结分岔','安洁分叉':'鞍结分岔','跨临界分叉':'跨临界分岔','跨林界分叉':'跨临界分岔','叉式分叉':'叉式分岔','差式分叉':'叉式分岔','差式分岔':'叉式分岔','无量刚化':'无量纲化','无量钢化':'无量纲化','磁制效应':'磁滞效应','磁质效应':'磁滞效应','异为方程':'一维方程'}
terms.update({v:'鞍结分岔' for v in ['安结分岔','安节分岔','安洁分岔','安杰分岔','安阶分叉','安杰分叉','鸩节分叉','安阶分岔']})
terms.update({v:'跨临界分岔' for v in ['跨离界分叉','跨离界分差','跨灵界分场','跨连接分叉','跨运界分叉','跨运界分差','跨连接分差']})
terms['分叉']='分岔'
kept=[];audit=[]
for s in data['segments']:
 s=dict(s)
 if s['start']>=data['duration']:
  audit.append({'start':ts(s['start']),'end':ts(s['end']),'action':'isolated','reason':'模型时间戳完全超出实际音轨时长','raw_text':s['text'].strip(),'speech_seconds':0});continue
 if s['end']>data['duration']:
  audit.append({'start':ts(s['start']),'end':ts(s['end']),'action':'timestamp_clamped','reason':'末尾时间戳截到实际音轨结尾','raw_text':s['text'].strip(),'speech_seconds':''})
  s['end']=data['duration']
 t=s['text'].strip();length=max(s['end']-s['start'],0.001)
 overlap=sum(max(0,min(s['end'],v['end'])-max(s['start'],v['start'])) for v in vad['intervals'] if v['start']<s['end'] and v['end']>s['start'])
 reason=''
 if re.search('不吝点赞|明镜与点点|字幕志愿者|字幕由.*社区|Amara.org',t,re.I):reason='与课程无关的典型字幕或宣传幻觉，隔离待核'
 elif overlap<0.12 and length>1.2:reason='语音活动检测未支持该段存在语音，隔离待核'
 elif s.get('compression_ratio',0)>3 and len(t)>70:reason='过度重复，疑似模型幻觉，隔离待核'
 if reason:
  audit.append({'start':ts(s['start']),'end':ts(s['end']),'action':'isolated','reason':reason,'raw_text':t,'speech_seconds':round(overlap,2)});continue
 changes=[]
 for old,new in terms.items():
  if old in t:t=t.replace(old,new);changes.append(old+'→'+new)
 if changes:audit.append({'start':ts(s['start']),'end':ts(s['end']),'action':'term_normalized','reason':'；'.join(changes),'raw_text':s['text'].strip(),'speech_seconds':round(overlap,2)})
 s=dict(s);s['text']=t
 if s.get('avg_logprob',0)<-1 or s.get('compression_ratio',0)>2.4:
  s['review_flag']='自动识别存疑，需听音核对'
  audit.append({'start':ts(s['start']),'end':ts(s['end']),'action':'review_flag','reason':s['review_flag'],'raw_text':t,'speech_seconds':round(overlap,2)})
 kept.append(s)

header=LESSON['subject']+' 本地 Whisper 自动转写清理版\n说明：已隔离语音检测不支持、典型字幕幻觉和严重重复片段，并规范少量已核对术语；不是逐字人工校对稿。隔离项见清理审计.csv，原始结果见 lecture_timestamped_raw.txt。数学公式以板书校订稿为准。\n\n'
(out/'lecture_timestamped.txt').write_text(header+'\n'.join(f'[{ts(s["start"])} --> {ts(s["end"])}] '+('[识别存疑] ' if s.get('review_flag') else '')+s['text'] for s in kept))
(out/'lecture.srt').write_text('\n\n'.join(f'{i}\n{ts(s["start"],True)} --> {ts(s["end"],True)}\n'+('[识别存疑] ' if s.get('review_flag') else '')+s['text'] for i,s in enumerate(kept,1)))
(out/'lecture_segments_clean.json').write_text(json.dumps({**data,'segments':kept,'cleaning':'Silero VAD and explicit artifact isolation; limited term normalization'},ensure_ascii=False,indent=2))
with (out/'清理审计.csv').open('w',encoding='utf-8-sig',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=['start','end','action','reason','raw_text','speech_seconds']);writer.writeheader();writer.writerows(audit)
summary={'duration_seconds':data['duration'],'chunks':len(list(out.glob('chunk_*.json'))),'raw_segments':len(data['segments']),'clean_segments':len(kept),'isolated':sum(x['action']=='isolated' for x in audit),'term_normalized':sum(x['action']=='term_normalized' for x in audit),'review_flags':sum(x['action']=='review_flag' for x in audit),'last_segment_end':max(s['end'] for s in kept),'models':data.get('models',[])}
(out/'quality_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))
