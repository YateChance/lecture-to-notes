"""Small, working maintenance CLI. Full orchestration remains in the project plan."""
from pathlib import Path
import argparse
from html.parser import HTMLParser
import json
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit

import yaml

PROJECT = Path(__file__).resolve().parents[2]


def settings():
    return yaml.safe_load((PROJECT / 'configs/default.yaml').read_text())


def lesson_path(value):
    requested = Path(value or settings()['default_lesson']).expanduser()
    path = (requested if requested.is_absolute() else PROJECT / 'outputs' / requested).resolve()
    if not (path / 'lesson.yaml').is_file():
        raise ValueError(f'找不到课程: {path}')
    return path


def status(lesson, as_json=False):
    result = json.loads((lesson / 'status.json').read_text())
    result['actual_files'] = {
        'frames': len(list((lesson / '02_frames/full').glob('*.jpg'))),
        'board_images': len(list((lesson / '02_frames/board').glob('*.jpg'))),
        'asr_chunks': len(list((lesson / '04_transcripts').glob('chunk_*.json'))),
    }
    result['completed_chunks'] = result['actual_files']['asr_chunks']
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f'课程：{lesson.parent.name} / {lesson.name}')
        print(f'状态：{result["status"]}；{result["stage"]}')
        print(f'转写：{result["actual_files"]["asr_chunks"]}/{result["total_chunks"]} 段')
        print(f'图片：{result["actual_files"]["frames"]} 原图，{result["actual_files"]["board_images"]} 板书图')
        report = lesson / result['report']
        print(f'报告：{report}' if report.is_file() else '报告：尚未生成')
        print(f'说明：{result["note"]}')


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {'href', 'src'} and value:
                self.refs.append(value)


def verify(lesson):
    errors = []
    count = 0
    checked = 0
    for path in lesson.rglob('*'):
        if '_runs' in path.parts or not path.is_file():
            continue
        if path.suffix == '.md' and 'assets' in path.parts and 'katex' in path.parts:
            continue  # Vendored package documentation is not part of the course report.
        if path.suffix == '.md':
            refs = re.findall(r'\]\(([^)]+)\)', path.read_text())
        elif path.suffix == '.html':
            parser = Refs()
            parser.feed(path.read_text())
            refs = parser.refs
            text = path.read_text()
            if 'MATHPLACEHOLDER' in text or 'katex-error' in text:
                errors.append(f'公式渲染错误: {path.relative_to(lesson)}')
        elif path.suffix == '.css':
            refs = [ref.strip('\"\'') for ref in re.findall(r'url\(([^)]+)\)', path.read_text())]
        else:
            continue
        checked += 1
        for ref in refs:
            url = urlsplit(ref)
            if url.scheme or url.netloc or not url.path:
                continue
            count += 1
            target = (path.parent / unquote(url.path)).resolve()
            if not target.exists():
                errors.append(f'{path.relative_to(lesson)} -> {ref}')
    state = json.loads((lesson / 'status.json').read_text())
    course=yaml.safe_load((lesson/'lesson.yaml').read_text())
    if course.get('documents',{}).get('sources'):
        from .documents import ready as documents_ready
        if not documents_ready(lesson):errors.append('教材资料未解析或归档不完整')
        gate_path=lesson/'09_quality/textbook_review.json'
        if not gate_path.exists():errors.append('缺少教材融合核对记录')
        else:
            gate=json.loads(gate_path.read_text());manifest=json.loads((lesson/'05_documents/documents.json').read_text())
            page_ids={page['page_id'] for item in manifest['documents'] for page in item['selected_pages']}
            if gate.get('status')!='completed' or gate.get('source_checks_completed') is not True:errors.append('教材融合核对未完成')
            references=gate.get('references',[])
            if not references:errors.append('教材融合缺少实际页面引用')
            for reference in references:
                if reference.get('page_id') not in page_ids:errors.append('教材页码来源不存在: '+str(reference.get('page_id')))
    for name in ['record', 'report']:
        if not (lesson / state[name]).is_file():
            errors.append(f'缺少{name}: {state[name]}')
    segments = json.loads((lesson / '04_transcripts/lecture_segments_clean.json').read_text())
    if any(not 0 <= item['start'] <= item['end'] <= segments['duration'] for item in segments['segments']):
        errors.append('清理版转写存在越界时间戳')
    record_json = lesson / '07_record/ready/record.json'
    if record_json.is_file():
        record_data = json.loads(record_json.read_text())
        for section in record_data.get('sections', []):
            if not 0 <= section.get('start_ms', -1) <= section.get('end_ms', -1) <= (segments['duration'] + 0.1) * 1000:
                errors.append(f'record章节时间戳越界: {section.get("title")}')
            for source in section.get('source_frames', []):
                if not (lesson / source).is_file():
                    errors.append(f'record引用图片不存在: {source}')
    if state.get('agent'):
        for task in state['agent'].get('tasks', ['01_board', '02_record', '03_report']):
            evidence = lesson / '_runs/workflow_validation/codex' / task / 'execution.json'
            if not evidence.is_file():
                errors.append(f'缺少模型执行证据: {task}')
                continue
            execution = json.loads(evidence.read_text())
            for field in ['model', 'reasoning_effort']:
                if execution.get(field) != state['agent'].get(field):
                    errors.append(f'{task}的{field}与课程配置不一致')
            if execution.get('status') != 'completed' or execution.get('returncode') != 0:
                errors.append(f'模型执行未成功完成: {task}')
    for folder, pattern, expected in [('02_frames/full', '*.jpg', state['frames']),
                                       ('02_frames/board', '*.jpg', state['board_images']),
                                       ('04_transcripts', 'chunk_*.json', state['total_chunks'])]:
        actual = len(list((lesson / folder).glob(pattern)))
        if actual != expected:
            errors.append(f'{folder}: {actual} != {expected}')
    result = {'passed': not errors, 'documents_checked': checked, 'local_links_checked': count,
              'errors': errors, 'note': '文件、数量、时间戳与链接检查；不是识别准确率评测。'}
    (lesson / '09_quality/deployment_checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


def main():
    if sys.argv[1:2] == ['pipeline']:
        from .pipeline import main as pipeline_main
        original=sys.argv[:];sys.argv=[sys.argv[0],*sys.argv[2:]]
        try:return pipeline_main()
        finally:sys.argv=original
    if sys.argv[1:2] == ['background']:
        from .background import main as background_main
        original=sys.argv[:];sys.argv=[sys.argv[0],*sys.argv[2:]]
        try:return background_main()
        finally:sys.argv=original
    if sys.argv[1:2] == ['download']:
        return subprocess.run([sys.executable, str(PROJECT / 'tools/video_download/download.py'), *sys.argv[2:]], cwd=PROJECT).returncode
    parser = argparse.ArgumentParser(prog='lecture-agent', description='课程文件部署与维护入口；完整agent按PLAN逐步实现。')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor', help='检查当前运行环境')
    sub.add_parser('download', help='视频下载策略、直链下载与本地导入；download --help查看详情')
    sub.add_parser('background', help='独立后台运行和20分钟本地回报；background --help查看详情')
    sub.add_parser('pipeline', help='固定流程：init、plan、run、freeze')
    for name in ['status', 'paths', 'render', 'verify', 'finish']:
        item = sub.add_parser(name)
        item.add_argument('--lesson', help='outputs下的课程相对路径，或课程目录绝对路径')
        if name == 'status':
            item.add_argument('--json', action='store_true')
            item.add_argument('--watch', action='store_true')
    options = parser.parse_args()
    if options.command == 'doctor':
        import importlib.util
        cache = Path(settings()['runtime']['model_cache']).expanduser()
        result = {'project': str(PROJECT), 'python': sys.executable,
                  'ffmpeg': shutil.which('ffmpeg'), 'ffprobe': shutil.which('ffprobe'),
                  'node': shutil.which('node'), 'model_cache': str(cache),
                  'codex': shutil.which('codex'), 'semantic_agent': settings().get('agent'),
                  'asr_model_present': (cache / settings()['asr']['model'] / 'weights.safetensors').is_file(),
                  'packages': {name: importlib.util.find_spec(name) is not None
                               for name in ['mlx_whisper', 'silero_vad', 'PIL', 'markdown2', 'matplotlib']}}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    lesson = lesson_path(options.lesson)
    if options.command == 'status':
        while True:
            status(lesson, options.json)
            if not options.watch:
                return 0
            time.sleep(2)
    if options.command == 'paths':
        print(json.dumps({'project': str(PROJECT), 'lesson': str(lesson),
                          'stages': [str(x.relative_to(lesson)) for x in sorted(lesson.iterdir()) if x.is_dir()]}, ensure_ascii=False, indent=2))
        return 0
    if options.command == 'render':
        return subprocess.run([sys.executable, str(PROJECT / 'scripts/render_report.py'), '--lesson', str(lesson)], cwd=PROJECT).returncode
    if options.command == 'finish':
        return subprocess.run([sys.executable, str(PROJECT / 'scripts/finish_lesson.py'), '--lesson', str(lesson)], cwd=PROJECT).returncode
    if options.command == 'verify':
        return verify(lesson)
    return 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except (ValueError, FileNotFoundError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
