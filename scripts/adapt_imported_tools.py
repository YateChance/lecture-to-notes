"""One-time relocation of the existing course tools, preserving originals in legacy/."""
from pathlib import Path

project = Path(__file__).resolve().parents[1]
old = project / 'legacy/current-course/scripts'
shared = 'from course_context import LESSON_ROOT, LESSON, MODEL_PATH, MODEL_CACHE\n'

for name in ['transcribe.py', 'detect_speech.py', 'clean_transcript.py', 'draw_figures.py', 'export_ocr.py', 'render_report.py']:
    text = (old / name).read_text()
    text = shared + text
    text = text.replace('ROOT = Path(__file__).resolve().parents[1]', 'ROOT = LESSON_ROOT')
    text = text.replace('root=Path(__file__).resolve().parents[1]', 'root=LESSON_ROOT')
    text = text.replace("ROOT / 'transcript'", "ROOT / '04_transcripts'")
    text = text.replace("ROOT / 'audio/lecture.wav'", "ROOT / '01_audio/audio.wav'")
    text = text.replace("root/'audio/lecture.wav'", "root/'01_audio/audio.wav'")
    text = text.replace("root/'transcript", "root/'04_transcripts")
    text = text.replace("MODEL = '/Users/wens/.local/share/codex-course-tools/models/whisper-large-v3-turbo-4bit'", 'MODEL = str(MODEL_PATH)')
    text = text.replace("'/Users/wens/.local/share/codex-course-tools/models/whisper-large-v3-turbo'", "str(MODEL_CACHE / 'whisper-large-v3-turbo')")
    if name == 'transcribe.py':
        text = text.replace('\ndef timestamp', "\nPROMPT = LESSON.get('asr', {}).get('initial_prompt', PROMPT)\n\ndef timestamp")
    if name == 'clean_transcript.py':
        text = text.replace('from pathlib import Path', 'from pathlib import Path\nimport math')
        text = text.replace("assert len(list(out.glob('chunk_*.json')))==30", "assert len(list(out.glob('chunk_*.json')))==math.ceil(data['duration']/300)")
        text = text.replace("'chunks':30", "'chunks':len(list(out.glob('chunk_*.json')))")
        text = text.replace("header='动力系统第2周 本地", "header=LESSON['subject']+' 本地")
    if name == 'draw_figures.py':
        text = text.replace("out=root/'assets'", "out=root/'08_report/assets'")
    if name == 'export_ocr.py':
        text = text.replace("source=root.parent/'第2周-每10秒抽帧'", "source=root/'02_frames'")
        text = text.replace("root/'board-text/", "root/'03_board/raw/")
        text = text.replace('../../第2周-每10秒抽帧/', '../../02_frames/')
        text = text.replace('见《板书文本校订稿.md》', '见 ../reviewed/板书文本校订稿.md')
    if name == 'render_report.py':
        text = text.replace('import re,json,subprocess,html', 'import re,json,subprocess,html,os,shutil')
        text = text.replace("root/'assets/katex/katex.js'", "root/'08_report/assets/katex/katex.js'")
        text = text.replace("'/opt/homebrew/bin/node'", "shutil.which('node') or 'node'")
        text = text.replace("render(root/'课程讲解报告.md',root/'课程讲解报告.html')",
                            "render(root/'08_report/课程讲解报告.md',root/'08_report/课程讲解报告.html')")
        text = text.replace("render(root/'board-text/板书文本校订稿.md',root/'板书文本校订稿.html')",
                            "render(root/'03_board/reviewed/板书文本校订稿.md',root/'03_board/reviewed/板书文本校订稿.html')")
        text = text.replace("root/'record/待处理/", "root/'07_record/ready/")
        text = text.replace("root/'正式课堂record.html'", "root/'07_record/ready/record.html'")
        text = text.replace(' print(target.name,', ''' asset_rel=os.path.relpath(root/'08_report/assets',target.parent)
 target.write_text(target.read_text().replace('href="assets/katex/',f'href="{asset_rel}/katex/'))
 content=target.read_text().replace('../03_board/reviewed/板书文本校订稿.md','../03_board/reviewed/板书文本校订稿.html').replace('../07_record/ready/动力系统_2026-09-18_第2周_record.md','../07_record/ready/record.html')
 target.write_text(content)
 print(target.name,''')
    (project / 'scripts' / name).write_text(text)

(project / 'scripts/board_ocr.swift').write_text((old / 'board_ocr.swift').read_text())
print('Adapted 6 maintenance scripts and the Apple Vision source.')
