from course_context import LESSON_ROOT, LESSON, MODEL_PATH, MODEL_CACHE
from pathlib import Path
import re,json,subprocess,html,os,shutil
import markdown2

root=LESSON_ROOT
def render(source, target):
 text=source.read_text();formulas=[]
 def capture(m):
  display=m.group(1) is not None
  formulas.append({'text':m.group(1) if display else m.group(2),'display':display})
  token=f'MATHPLACEHOLDER{len(formulas)-1}END'
  return '\n\n<div>'+token+'</div>\n\n' if display else token
 text=re.sub(r'\\\[(.*?)\\\]|\\\((.*?)\\\)',capture,text,flags=re.S)
 renderer='''const fs=require('fs');const katex=require(process.argv[1]);const formulas=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(formulas.map(x=>katex.renderToString(x.text,{displayMode:x.display,throwOnError:true,output:'htmlAndMathml',strict:'warn'}))));'''
 p=subprocess.run([shutil.which('node') or 'node','-e',renderer,str(root/'08_report/assets/katex/katex.js')],input=json.dumps(formulas),text=True,capture_output=True,check=True)
 rendered=json.loads(p.stdout)
 body=markdown2.markdown(text,extras=['tables','header-ids','fenced-code-blocks','toc'])
 body=body.replace('href="board-text/板书文本校订稿.md"','href="板书文本校订稿.html"')
 toc=getattr(body,'toc_html','') or ''
 for i,value in enumerate(rendered):body=body.replace(f'MATHPLACEHOLDER{i}END',value)
 # The board source lives one level down, but its HTML copy is beside the report.
 if source.parent.name=='board-text':
  body=body.replace('href="板书逐帧OCR原文.md"','href="board-text/板书逐帧OCR原文.md"')
 title=source.stem
 target.write_text('''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+html.escape(title)+'''</title><link rel="stylesheet" href="assets/katex/katex.min.css"><style>
:root{color-scheme:light;--ink:#172c39;--accent:#12665b}*{box-sizing:border-box}body{margin:0;color:var(--ink);background:#f3f5f5;font:17px/1.9 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}main{max-width:1050px;margin:36px auto;background:white;padding:54px 66px;border-radius:10px}h1{font-size:32px;line-height:1.45;margin:0 0 30px}h2{font-size:25px;margin:48px 0 18px;color:var(--accent)}h3{font-size:20px;margin-top:32px}p{margin:15px 0}a{color:#116f65;text-underline-offset:4px}img{max-width:100%;height:auto}table{border-collapse:collapse;width:100%;font-size:15px;margin:24px 0}td,th{border:1px solid #d6dfdd;padding:12px;text-align:left}th{background:#e9f1ef}strong{font-weight:650}.katex-display{padding:10px 0;overflow-x:auto;overflow-y:hidden}.katex{font-size:1.08em}details{padding:14px 20px;background:#edf4f2;border-radius:8px}details ul{line-height:1.6}li{margin:7px 0}footer{margin-top:50px;font-size:13px;color:#63716e}@media(max-width:700px){main{margin:0;padding:24px 18px;border-radius:0}h1{font-size:27px}h2{font-size:22px}table{display:block;overflow:auto}}@media print{body{background:white}main{margin:0;padding:0;max-width:none}details{display:none}h2,h3{break-after:avoid}table{font-size:12px}.katex-display{overflow:visible}a{color:inherit}}
</style></head><body><main>'''+('<details><summary>展开目录</summary>'+toc+'</details>' if toc else '')+str(body)+'''<footer>本地离线报告 · 公式可选择和复制 · 原始材料通过文中链接回查</footer></main></body></html>''',encoding='utf-8')
 asset_rel=os.path.relpath(root/'08_report/assets',target.parent)
 target.write_text(target.read_text().replace('href="assets/katex/',f'href="{asset_rel}/katex/'))
 content=target.read_text().replace('../03_board/reviewed/板书文本校订稿.md','../03_board/reviewed/板书文本校订稿.html').replace('../07_record/ready/动力系统_2026-09-18_第2周_record.md','../07_record/ready/record.html').replace('../07_record/ready/record.md','../07_record/ready/record.html')
 target.write_text(content)
 print(target.name,'formulas',len(formulas),'bytes',target.stat().st_size)
render(root/'08_report/课程讲解报告.md',root/'08_report/课程讲解报告.html')
render(root/'03_board/reviewed/板书文本校订稿.md',root/'03_board/reviewed/板书文本校订稿.html')
record=root/LESSON.get('artifacts',{}).get('record','07_record/ready/动力系统_2026-09-18_第2周_record.md')
if record.exists():render(record,root/'07_record/ready/record.html')
