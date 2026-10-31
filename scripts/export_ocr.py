from course_context import LESSON_ROOT, LESSON, MODEL_PATH, MODEL_CACHE
from pathlib import Path
import json,csv
from difflib import SequenceMatcher

root=LESSON_ROOT
source=root/'02_frames'
index={r['板书裁剪图'].split('/')[-1]:r for r in csv.DictReader((source/'帧索引.csv').open(encoding='utf-8-sig'))}
records=[json.loads(x) for x in (root/'03_board/raw/ocr_raw.jsonl').read_text().splitlines()]
out=['# 板书逐帧 OCR 原始文本','', f'以下是本机 Apple Vision 对 {len(records)} 张板书裁剪图的自动识别。空白画面会显示未识别到文字。手写公式、上下标、箭头和曲线可能识别失败；未经校正，不应直接用来判断数学结论。校对后的主干内容见 ../reviewed/板书文本校订稿.md。','']
changes=['# 板书 OCR 变化索引','','此索引按文本相似度筛选，供定位画面变化；不是已校订笔记。','']
last=''
for r in records:
 row=index[r['file']]
 lines=sorted(r['lines'],key=lambda a:(-round(a['bbox'][1],2),a['bbox'][0]))
 text='\n'.join(x['text'] for x in lines)
 block=[f'## {row["视频时间"]} 帧 {row["序号"]}', '',f'[板书图](../../02_frames/{row["板书裁剪图"]}) · [课堂原图](../../02_frames/{row["原图"]})','',text or '（未识别到文字）','']
 out.extend(block)
 if text and SequenceMatcher(None,last,text).ratio()<0.6:
  changes.extend(block);last=text
(root/'03_board/raw/板书逐帧OCR原文.md').write_text('\n'.join(out))
(root/'03_board/raw/板书OCR变化索引.md').write_text('\n'.join(changes))
print('OCR records',len(records),'nonempty',sum(bool(x['lines']) for x in records))
