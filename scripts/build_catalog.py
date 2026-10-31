"""Build a local file catalog, with relative links only."""
from pathlib import Path
import html
import json
from urllib.parse import quote
import yaml

project = Path(__file__).resolve().parents[1]
outputs = project / 'outputs'
style = 'body{font:17px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#f2f5f4;color:#183b35;margin:0}main{max-width:960px;margin:40px auto;background:white;padding:36px;border-radius:12px}a{color:#12695d}li{margin:12px 0}small{color:#61716b}code{background:#eef3f0;padding:3px 6px}'


def page(title, body):
    return f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{style}</style><main><h1>{html.escape(title)}</h1>{body}</main></html>'


items = []
for config in sorted(outputs.glob('*/*/lesson.yaml')):
    lesson = config.parent
    data = yaml.safe_load(config.read_text())
    status = json.loads((lesson / 'status.json').read_text())
    links = [
        ('课程讲解报告', '08_report/课程讲解报告.html'),
        ('正式课堂record', '07_record/ready/record.html'),
        ('板书文字与公式', '03_board/reviewed/板书文本校订稿.html'),
        ('抽帧图片索引', '02_frames/index.html'),
        ('带时间戳的语音转写', '04_transcripts/lecture_timestamped.txt'),
        ('语音识别字幕', '04_transcripts/lecture.srt'),
        ('时间戳汇总', '06_timeline/timeline.md'),
        ('原始视频', '00_sources/video/lecture.mp4'),
        ('音轨', '01_audio/audio.wav'),
        ('检查结果', '09_quality/deployment_checks.json'),
    ]
    body = f'<p>{html.escape(data["subject"])} · 第{data["week"]}周第{data["session"]}次课 · {html.escape(data["recorded_date"])}</p>'
    body += f'<p>{html.escape(status["note"])}</p><ul>'
    for label, target in links:
        if not (lesson / target).is_file():
            continue
        body += f'<li><a href="{quote(target)}">{html.escape(label)}</a></li>'
    body += '</ul><p><a href="../../index.html">返回课程总目录</a></p>'
    body += '<small>源数据、编修稿与报告分开保存；本页链接均指向本项目中的文件。</small>'
    (lesson / 'index.html').write_text(page(lesson.name, body))
    relative = lesson.relative_to(outputs) / 'index.html'
    items.append(f'<li><a href="{quote(str(relative))}">{html.escape(data["subject"])} / {html.escape(lesson.name)}</a></li>')
(outputs / 'index.html').write_text(page('课程材料目录', '<ul>' + ''.join(items) + '</ul>'))
print('Catalog updated:', outputs / 'index.html')
