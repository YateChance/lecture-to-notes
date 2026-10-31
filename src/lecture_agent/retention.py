"""Delete only lesson-local audio/video after a verified, source-linked report."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess,sys,wave
import yaml

EXTENSIONS={'.mp4','.mkv','.mov','.webm','.avi','.m4v','.wav','.mp3','.m4a','.aac','.flac','.ogg'}

def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):result.update(block)
    return result.hexdigest()

def save(path,data):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2));temporary.replace(path)

def receipt(root):
    path=root/'09_quality/media_cleanup.json'
    return json.loads(path.read_text()) if path.exists() else {}

def removed(root,relative):
    data=receipt(root)
    return data.get('status')=='completed' and any(item['path']==relative and item['status']=='deleted' for item in data.get('files',[]))

def audio_duration(root):
    audio=root/'01_audio/audio.wav'
    if audio.exists():
        with wave.open(str(audio)) as wav:return wav.getnframes()/wav.getframerate()
    if removed(root,'01_audio/audio.wav'):return json.loads((root/'01_audio/audio_manifest.json').read_text())['duration_seconds']
    raise FileNotFoundError(audio)

def confirm_and_cleanup(root):
    from .cli import verify
    root=root.resolve();lesson=yaml.safe_load((root/'lesson.yaml').read_text())
    for file,fields in [('record_gate.json',['full_lesson_covered']),('report_gate.json',['full_lesson_covered','source_checks_completed'])]:
        gate=json.loads((root/'09_quality'/file).read_text())
        if gate.get('status')!='completed' or not all(gate.get(key) is True for key in fields):raise RuntimeError('正式record/报告门禁未完成，禁止删除媒体')
    if lesson.get('documents',{}).get('sources'):
        gate=json.loads((root/'09_quality/textbook_review.json').read_text())
        if gate.get('status')!='completed' or gate.get('source_checks_completed') is not True:raise RuntimeError('教材融合未核完，禁止删除媒体')
    if verify(root)!=0:raise RuntimeError('报告确认检查失败，禁止删除媒体')
    data=receipt(root);prior={item['path']:item for item in data.get('files',[])}
    candidates=[]
    for path in root.rglob('*'):
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in EXTENSIONS:
            if not path.resolve().is_relative_to(root):raise RuntimeError('媒体路径越界，禁止删除')
            candidates.append(path)
    for path in candidates:
        relative=str(path.relative_to(root))
        prior[relative]={'path':relative,'bytes':path.stat().st_size,'sha256':sha(path),'status':'pending'}
    audio=root/'01_audio/audio.wav'
    if audio.exists():
        with wave.open(str(audio)) as wav:
            save(root/'01_audio/audio_manifest.json',{'duration_seconds':wav.getnframes()/wav.getframerate(),'sample_rate':wav.getframerate(),
                 'channels':wav.getnchannels(),'sample_width':wav.getsampwidth(),'frames':wav.getnframes(),'sha256':sha(audio),'availability':'deleted_after_verified_report'})
    # Remove live media hyperlinks before deletion; source hashes and timestamps remain.
    targets={str((root/item).resolve()) for item in prior}
    for path in root.rglob('*'):
        if '_runs' in path.relative_to(root).parts or not path.is_file() or path.suffix not in {'.md','.html'}:continue
        content=path.read_text();original=content
        def replace_md(match):
            label,target=match.groups();plain=target.split('#')[0]
            if '://' not in plain and str((path.parent/plain).resolve()) in targets:
                source=os.path.relpath(root/'00_sources/sources.jsonl',path.parent)
                return f'{label}（音视频已按策略清理；[来源登记]({source})）'
            return match.group(0)
        def replace_html(match):
            href,label=match.groups()
            from urllib.parse import unquote
            if '://' not in href and str((path.parent/unquote(href.split('#')[0])).resolve()) in targets:return label+'（音视频已按策略清理，来源登记保留）'
            return match.group(0)
        content=re.sub(r'\[([^\]]*)\]\(([^)]+)\)',replace_md,content)
        content=re.sub(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',replace_html,content,flags=re.S)
        if content!=original:path.write_text(content)
    project=Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable,str(project/'scripts/render_report.py'),'--lesson',str(root)],check=True)
    if verify(root)!=0:raise RuntimeError('媒体链接更新后检查失败，禁止删除')
    confirmation={'confirmed_at':datetime.now(timezone.utc).isoformat(),'report_md_sha256':sha(root/'08_report/课程讲解报告.md'),
                  'report_html_sha256':sha(root/'08_report/课程讲解报告.html'),'record_sha256':sha(root/'07_record/ready/record.md'),'checks_passed':True}
    save(root/'09_quality/report_confirmation.json',confirmation)
    data={'status':'deleting','confirmed_report':confirmation,'files':list(prior.values()),'policy':'本课报告、教材融合及链接检查通过后清理课内音视频；不删除外部教材、图片、转写或模型。'}
    journal=root/'09_quality/media_cleanup.json';save(journal,data)
    for item in data['files']:
        path=root/item['path']
        if item['status']=='deleted':continue
        if path.exists():path.unlink()
        item['status']='deleted';save(journal,data)
    data.update(status='completed',completed_at=datetime.now(timezone.utc).isoformat(),freed_bytes=sum(item['bytes'] for item in data['files']))
    save(journal,data)
    state=json.loads((root/'status.json').read_text());state['media_retention']='deleted_after_verified_report';save(root/'status.json',state)
    if verify(root)!=0:raise RuntimeError('清理后检查失败，请检查保留的报告及清理回执')
    return data
