"""Copy the completed course into this project without modifying its sources."""
from pathlib import Path
import csv
import hashlib
import json
import shutil
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = Path('/Users/wens/Downloads/动力系统课程视频')
OLD = SOURCE / '第2周-课程报告'
LESSON = PROJECT / 'outputs/动力系统/第02周（1）-一维系统分岔'
ARCHIVE = LESSON / '_runs/import_20261031'


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if src.stat().st_size != dst.stat().st_size:
            raise FileExistsError(f'Conflicting destination: {dst}')
        return
    # APFS copy-on-write when available; ordinary copy elsewhere.
    result = subprocess.run(['/bin/cp', '-c', str(src), str(dst)], capture_output=True)
    if result.returncode:
        shutil.copy2(src, dst)


def copy_tree(src, dst):
    for file in sorted(src.rglob('*')):
        if file.is_file():
            copy_file(file, dst / file.relative_to(src))


def replace_text(path, replacements):
    content = path.read_text()
    for old, new in replacements:
        content = content.replace(old, new)
    path.write_text(content)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    if (ARCHIVE / 'migration_complete.json').exists():
        print('Import already completed:', LESSON)
        return
    for folder in ['00_sources/video', '00_sources/slides', '00_sources/textbook',
                   '01_audio', '02_frames/full', '02_frames/board', '03_board/raw',
                   '03_board/reviewed', '04_transcripts', '05_documents', '06_timeline',
                   '07_record/draft', '07_record/ready', '08_report', '09_quality']:
        (LESSON / folder).mkdir(parents=True, exist_ok=True)

    copy_file(SOURCE / '动力系统-第2周-教师视频.mp4', LESSON / '00_sources/video/lecture.mp4')
    copy_file(OLD / 'audio/lecture.wav', LESSON / '01_audio/audio.wav')
    frames = SOURCE / '第2周-每10秒抽帧'
    copy_tree(frames / 'frames', LESSON / '02_frames/full')
    copy_tree(frames / 'boards', LESSON / '02_frames/board')
    copy_file(frames / '源帧时间戳.txt', LESSON / '02_frames/source_timestamps.txt')
    rows = list(csv.DictReader((frames / '帧索引.csv').open(encoding='utf-8-sig')))
    with (LESSON / '02_frames/帧索引.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            row['原图'] = row['原图'].replace('frames/', 'full/')
            row['板书裁剪图'] = row['板书裁剪图'].replace('boards/', 'board/')
            writer.writerow(row)
    index = (frames / 'index.html').read_text().replace('frames/', 'full/').replace('boards/', 'board/')
    (LESSON / '02_frames/index.html').write_text(index)

    for name in ['ocr_raw.jsonl', 'ocr_progress.log', '板书逐帧OCR原文.md', '板书OCR变化索引.md']:
        copy_file(OLD / 'board-text' / name, LESSON / '03_board/raw' / name)
    copy_tree(OLD / 'board-text/contact-sheets', LESSON / '03_board/raw/contact-sheets')
    copy_file(OLD / 'board-text/板书文本校订稿.md', LESSON / '03_board/reviewed/板书文本校订稿.md')
    for name in ['板书逐帧OCR原文.md', '板书OCR变化索引.md']:
        replace_text(LESSON / '03_board/raw' / name, [
            ('../../第2周-每10秒抽帧/boards/', '../../02_frames/board/'),
            ('../../第2周-每10秒抽帧/frames/', '../../02_frames/full/'),
            ('(板书文本校订稿.md)', '(../reviewed/板书文本校订稿.md)'),
        ])
    replace_text(LESSON / '03_board/reviewed/板书文本校订稿.md', [
        ('(板书逐帧OCR原文.md)', '(../raw/板书逐帧OCR原文.md)'),
    ])

    copy_tree(OLD / 'transcript', LESSON / '04_transcripts')
    copy_tree(OLD / 'record/待编修', LESSON / '07_record/draft')
    copy_tree(OLD / 'record/待处理', LESSON / '07_record/ready')
    for file in (LESSON / '07_record/ready').glob('*.md'):
        replace_text(file, [('transcript/', '04_transcripts/'), ('board-text/', '03_board/'),
                            ('record/待编修', '07_record/draft'), ('record/待处理', '07_record/ready')])

    copy_file(OLD / '课程讲解报告.md', LESSON / '08_report/课程讲解报告.md')
    copy_tree(OLD / 'assets', LESSON / '08_report/assets')
    replace_text(LESSON / '08_report/课程讲解报告.md', [
        ('record/待处理/', '../07_record/ready/'),
        ('transcript/', '../04_transcripts/'),
        ('board-text/板书文本校订稿.md', '../03_board/reviewed/板书文本校订稿.md'),
        ('board-text/板书逐帧OCR原文.md', '../03_board/raw/板书逐帧OCR原文.md'),
        ('../第2周-每10秒抽帧/index.html', '../02_frames/index.html'),
    ])

    # Historical code and PID/log records are evidence, never executable entrypoints.
    copy_tree(OLD / 'scripts', PROJECT / 'legacy/current-course/scripts')
    copy_file(frames / 'build_index.py', PROJECT / 'legacy/current-course/build_index.py')
    for name in ['后台运行日志.txt', '后台进程.json', '处理状态.json', '使用说明.md']:
        copy_file(OLD / name, ARCHIVE / 'original' / name)
    copy_file(OLD / 'record/流程说明.md', ARCHIVE / 'original/record流程说明.md')
    copy_file(OLD / 'transcript/quality_summary.json', LESSON / '09_quality/asr_quality.json')
    copy_file(Path('/Users/wens/.local/share/codex-course-tools/requirements.lock.txt'),
              PROJECT / 'configs/imported-environment.lock.txt')

    # Active metadata uses paths relative to the lesson, not Downloads paths or old PIDs.
    for location in ['07_record/draft/record.json', '07_record/ready/record.json']:
        p = LESSON / location
        d = json.loads(p.read_text())
        mapping = {
            'source_video': '00_sources/video/lecture.mp4',
            'board_text': '03_board/reviewed/板书文本校订稿.md',
            'next_directory': '07_record/ready',
            'formal_record': '07_record/ready/动力系统_2026-09-18_第2周_record.md',
            'report_file': '08_report/课程讲解报告.html',
        }
        for key, value in mapping.items():
            if key in d:
                d[key] = value
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2))

    source_video = SOURCE / '动力系统-第2周-教师视频.mp4'
    target_video = LESSON / '00_sources/video/lecture.mp4'
    source_audio = OLD / 'audio/lecture.wav'
    target_audio = LESSON / '01_audio/audio.wav'
    checks = {}
    for label, a, b in [('video', source_video, target_video), ('audio', source_audio, target_audio)]:
        checks[label] = {'sha256': digest(a), 'target_sha256': digest(b), 'bytes': b.stat().st_size}
        assert checks[label]['sha256'] == checks[label]['target_sha256']
    assert len(list((LESSON / '02_frames/full').glob('*.jpg'))) == 890
    assert len(list((LESSON / '02_frames/board').glob('*.jpg'))) == 890
    assert len(list((LESSON / '04_transcripts').glob('chunk_*.json'))) == 30
    sources = [{'source_id': 'video_main', 'role': 'video', 'path': '00_sources/video/lecture.mp4',
                'sha256': checks['video']['sha256'], 'source_page':
                'https://classroom.msa.buaa.edu.cn/livingroom?course_id=156270&sub_id=5951230&tenant_code=21'}]
    (LESSON / '00_sources/sources.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in sources))
    status = {'schema_version': '1.0', 'status': 'complete_with_notes',
              'stage': '已导入整课转写 主干record与报告', 'imported': True,
              'completed_chunks': 30, 'total_chunks': 30, 'frames': 890, 'board_images': 890,
              'record': '07_record/ready/动力系统_2026-09-18_第2周_record.md',
              'report': '08_report/课程讲解报告.html',
              'note': '主干编修已完成，未对整段音频逐字人工听校；无课件和教材。'}
    (LESSON / 'status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2))
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    (ARCHIVE / 'migration_complete.json').write_text(json.dumps(
        {'source': str(SOURCE), 'destination': str(LESSON), 'checks': checks,
         'copied_originals_retained': True, 'frames': 890, 'asr_chunks': 30}, ensure_ascii=False, indent=2))
    print('Imported and verified:', LESSON)


if __name__ == '__main__':
    main()
