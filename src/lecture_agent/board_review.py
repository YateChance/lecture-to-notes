"""Bounded, fully supplied multimodal review tasks; no giant truncated cat output."""
from pathlib import Path
import csv,json,yaml,math
from difflib import SequenceMatcher
from .codex_runner import execute

def stamp(seconds):
    s=int(seconds);return f'{s//3600:02d}:{s//60%60:02d}:{s%60:02d}'

def review(root,base):
    audio=json.loads((root/'04_transcripts/lecture_segments_clean.json').read_text())
    rows=list(csv.DictReader((root/'02_frames/帧索引.csv').open(encoding='utf-8-sig')))
    frames={Path(row['板书裁剪图']).name:row for row in rows}
    ocr=[json.loads(x) for x in (root/'03_board/raw/ocr_raw.jsonl').read_text().splitlines()]
    lesson_config=yaml.safe_load((root/'lesson.yaml').read_text())
    contact_dir=root/lesson_config.get('frames',{}).get('contact_directory','_runs/workflow_validation/contact_sheets')
    manifest=json.loads((contact_dir/'manifest.json').read_text())
    tasks=[];parts=[];reviews=[]
    for number,start in enumerate(range(0,math.ceil(audio['duration']),1800),1):
        end=min(start+1800,audio['duration']);task=f'01_board_{number:02d}';tasks.append(task)
        speech=[s for s in audio['segments'] if start<=s['start']<end]
        transcript='\n'.join(f'[{stamp(s["start"])}–{stamp(s["end"])}] {s["text"]}'+(' [识别存疑]' if s.get('review_flag') else '') for s in speech)
        changes=[];last=''
        for item in ocr:
            row=frames[item['file']];time=float(row['时间秒'])
            if not start<=time<end:continue
            text=' / '.join(line['text'] for line in sorted(item['lines'],key=lambda a:(-round(a['bbox'][1],2),a['bbox'][0])))
            if text and SequenceMatcher(None,last,text).ratio()<.6:
                changes.append(f'[{row["视频时间"]}] 02_frames/{row["板书裁剪图"]}: {text}');last=text
        images=[]
        for item in manifest:
            if any(start<=float(frames[Path(path).name]['时间秒'])<end for path in item['board_images']):images.append(contact_dir/item['file'])
        selected=[row for row in rows if start<=float(row['时间秒'])<end]
        # One complete camera frame per interval checks the crop against its context.
        if selected:images.append(root/'02_frames'/selected[len(selected)//2]['原图'])
        part=f'03_board/reviewed/part_{number:02d}.md';result=f'09_quality/board_part_{number:02d}.json'
        inputs='\n'.join(str(p.relative_to(root)) for p in images)
        prompt=base+f'''
当前只处理第{number}段：{stamp(start)}—{stamp(end)}。本段全部清理后ASR已直接附在下方，共{len(speech)}条；无需cat全课大文件，避免工具输出截断。附图为本段全部接触表和一张完整课堂原图，实际输入名单如下。接触表中的文件名对应原视频时间；需要时可读具体邻帧，但不要声称看过未作为输入或未实际调用图片工具打开的文件。
{inputs}
任务：核对本段板书主干与完整转写，将可辨文字、公式、定义、图示、关键例子、结论条件按教学顺序详细整理到 {part}。每个主干点给原视频时间和实际板书图链接，引用可从提供的OCR候选与接触表标签确定。目标文件在03_board/reviewed下，图片链接使用../../02_frames/board/文件名.jpg；不要引用不存在的图片。仅为已核主干，不是全量逐帧人工逐字校对，也不是逐字听校。难辨项可以留明确存疑；但必须覆盖本段所有主题，不能只写开头或初稿后终止。
同时写{result}，JSON字段status（完成写completed，否则incomplete）、start_ms={round(start*1000)}、end_ms={round(end*1000)}、all_supplied_transcript_reviewed（布尔）、topics（每项title/start_ms/end_ms/summary）、uncertainties（数组）、input_images（使用上述实际输入名单）、additional_images_opened（仅实际额外打开的图片，未打开则空数组）、limitations。务必真实记录完成情况，不要把输入名单以外的图片列为已查看。
先完成核对再写status；不要在完成后说尚未通读本段。阅读图片与以下文本足以完成主干整理，不能辨识的具体符号可以明确存疑，不需要把整项任务留在初稿。

【本时间段完整ASR】
{transcript}

【本时间段OCR变化候选；手写公式可能严重误识，以附图为准】
{chr(10).join(changes)}
'''
        execute(root,task,prompt,images=images,expected_outputs=[part,result],gates={result:{'status':'completed','all_supplied_transcript_reviewed':True}})
        data=json.loads((root/result).read_text())
        if data.get('status')!='completed' or data.get('all_supplied_transcript_reviewed') is not True:
            raise RuntimeError(f'{task}明确未完成本段核对，禁止进入record')
        supplied={str(p.relative_to(root)) for p in images}
        if not set(data.get('input_images',[])).issubset(supplied):
            raise RuntimeError(f'{task}报告了未提供的输入图片，需核实')
        parts.append(root/part);reviews.append(data)
    introduction='# 板书文本校订稿\n\n全课按约30分钟分段，将各段完整自动转写、OCR变化候选及全部接触表直接提供给gpt-6.1-terra / medium核对。以下为主干文字和公式整理，非全量逐帧人工校对、非逐字听校。原始OCR与帧索引另存，具体存疑保留在各节。\n\n'
    (root/'03_board/reviewed/板书文本校订稿.md').write_text(introduction+'\n\n---\n\n'.join(p.read_text() for p in parts))
    all_topics=[topic for r in reviews for topic in r['topics']]
    uncertainties=[item for r in reviews for item in r['uncertainties']]
    core=yaml.safe_load((root/'lesson.yaml').read_text()).get('core_content','课程主干')
    (root/'09_quality/content_outline.json').write_text(json.dumps({'core_content':core,'topics':all_topics,'uncertainties':uncertainties,'status':'completed'},ensure_ascii=False,indent=2))
    (root/'09_quality/board_review.json').write_text(json.dumps({'status':'completed','tasks':tasks,'all_supplied_transcript_reviewed':True,'segment_reviews':reviews,'note':'输入图像是模型实际收到的图片；主干整理不等于逐帧或逐字听校。首轮未完成结果保留在_runs，未采纳其全部图片查看声明。'},ensure_ascii=False,indent=2))
    return tasks
