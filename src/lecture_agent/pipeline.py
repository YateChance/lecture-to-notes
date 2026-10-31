"""Versioned local pipeline: fixed stages, validated reuse, no planning model."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,hashlib,json,math,os,shutil,subprocess,sys,wave
import yaml

PROJECT=Path(__file__).resolve().parents[2]
VERSION='2.0'
STAGES=('audio','frames','vad','asr','ocr','documents','finish')
DIRECTORIES=('00_sources/video','00_sources/downloads','01_audio','02_frames/full','02_frames/board',
             '03_board/raw','03_board/reviewed','04_transcripts','05_documents','06_timeline',
             '07_record/draft','07_record/ready','08_report','09_quality','_runs')

def load(path):return json.loads(path.read_text())

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2));temporary.replace(path)

def settings():return yaml.safe_load((PROJECT/'configs/default.yaml').read_text())

def configuration(root):return yaml.safe_load((root/'lesson.yaml').read_text())

def initialize(subject,week,session,title,date,roi):
    for value in (subject,title):
        if value in {'.','..'} or any(c in value for c in '/\\\0'):raise ValueError('课程名、核心内容不能包含路径分隔符')
    if week<1 or session<1:raise ValueError('周次与课次须为正整数')
    from datetime import date as date_type
    date_type.fromisoformat(date)
    if len(roi)!=4 or not (0<=roi[0]<roi[2] and 0<=roi[1]<roi[3]):raise ValueError('ROI应为x0 y0 x1 y1')
    root=PROJECT/'outputs'/subject/f'第{week:02d}周（{session}）-{title}'
    if root.exists():raise ValueError('课程目录已存在；使用pipeline plan/run接续，不能重新初始化')
    for directory in DIRECTORIES:(root/directory).mkdir(parents=True,exist_ok=True)
    defaults=settings()
    lesson={'schema_version':'1.0','lesson_id':f'lesson-{date}-{week}-{session}','subject':subject,'week':week,'session':session,
            'core_content':title,'recorded_date':date,'language':'zh','inputs':{'video':'00_sources/video/lecture.mp4','slides':None,'textbook':None},
            'asr':dict(defaults['asr']),'frames':{**defaults['frames'],'board_roi':roi,'contrast':1.35},
            'agent':{key:defaults['agent'][key] for key in ('model','reasoning_effort')},'artifacts':{'record':'07_record/ready/record.md'}}
    (root/'lesson.yaml').write_text(yaml.safe_dump(lesson,allow_unicode=True,sort_keys=False))
    save(root/'status.json',{'schema_version':'1.0','status':'waiting_input','stage':'等待素材','total_chunks':0,'frames':0,'board_images':0,
                             'record':'07_record/ready/record.md','report':'08_report/课程讲解报告.html','note':'请先使用下载工具登记原视频。','agent':lesson['agent']})
    (root/'00_sources/sources.jsonl').write_text('')
    (root/'05_documents/README.md').write_text('# 辅助资料\n\n本课未提供课件与教材；当前固定通路不解析辅助资料。\n')
    return root

def ready(root,stage):
    """Completion is structural, and semantic stages additionally require explicit gates."""
    try:
        lesson=configuration(root)
        if stage=='audio':
            if not (root/'01_audio/audio.wav').exists():
                from .retention import removed
                return removed(root,'01_audio/audio.wav') and (root/'01_audio/audio_manifest.json').is_file()
            with wave.open(str(root/'01_audio/audio.wav')) as audio:
                return audio.getnchannels()==1 and audio.getframerate()==16000 and audio.getsampwidth()==2 and audio.getnframes()>0
        if stage=='frames':
            summary=load(root/'02_frames/extraction.json');count=summary['frames']
            rows=list(csv.DictReader((root/'02_frames/帧索引.csv').open(encoding='utf-8-sig')))
            return count>0 and len(rows)==count and len(list((root/'02_frames/full').glob('*.jpg')))==count and len(list((root/'02_frames/board').glob('*.jpg')))==count and list(summary['roi'])==list(lesson['frames']['board_roi']) and summary['interval_seconds']==lesson['frames']['sample_seconds'] and all((root/'02_frames'/row[key]).is_file() for row in rows for key in ('原图','板书裁剪图'))
        if stage=='vad':
            data=load(root/'04_transcripts/speech_intervals.json')
            from .retention import audio_duration
            duration=audio_duration(root)
            return data.get('complete') is True and abs(data['duration']-duration)<.1
        if stage=='asr':
            data=load(root/'04_transcripts/lecture_segments.json');count=math.ceil(data['duration']/lesson['asr']['chunk_seconds'])
            chunks=list((root/'04_transcripts').glob('chunk_*.json'))
            from .retention import audio_duration
            duration=audio_duration(root)
            if abs(data['duration']-duration)>.1:return False
            for number,chunk in enumerate(sorted(chunks)):
                checkpoint=load(chunk)
                if checkpoint.get('chunk_start')!=number*lesson['asr']['chunk_seconds'] or Path(checkpoint.get('model_source','')).name!=lesson['asr']['model']:return False
            marker=root/'04_transcripts/asr_complete.json';log=root/'04_transcripts/progress.log'
            completion=load(marker) if marker.exists() else {}
            finished=(completion.get('complete') is True and completion.get('chunks')==count and completion.get('segments')==len(data['segments'])) or (log.exists() and log.read_text().rstrip().endswith('COMPLETE '+str(len(data['segments']))))
            return len(chunks)==count and finished and all(0<=s['start']<=s['end']<=data['duration']+.001 for s in data['segments'])
        if stage=='ocr':
            lines=[json.loads(line) for line in (root/'03_board/raw/ocr_raw.jsonl').read_text().splitlines()]
            names={p.name for p in (root/'02_frames/board').glob('*.jpg')}
            return bool(names) and len(lines)==len(names) and {item['file'] for item in lines}==names
        if stage=='documents':
            if not lesson.get('documents',{}).get('sources'):return not lesson['inputs'].get('textbook') and not lesson['inputs'].get('slides')
            from .documents import ready as documents_ready
            return documents_ready(root)
        if stage=='finish':
            files=('07_record/ready/record.md','07_record/ready/record.html','07_record/ready/record.json',
                   '03_board/reviewed/板书文本校订稿.md','03_board/reviewed/板书文本校订稿.html','08_report/课程讲解报告.md','08_report/课程讲解报告.html')
            board=load(root/'09_quality/board_review.json');record=load(root/'09_quality/record_gate.json');report=load(root/'09_quality/report_gate.json')
            complete=all((root/p).is_file() for p in files) and board.get('status')=='completed' and board.get('all_supplied_transcript_reviewed') is True and record.get('status')=='completed' and record.get('full_lesson_covered') is True and report.get('status')=='completed' and report.get('full_lesson_covered') is True and report.get('source_checks_completed') is True
            if lesson.get('documents',{}).get('sources'):
                gate=load(root/'09_quality/textbook_review.json');complete=complete and gate.get('status')=='completed' and gate.get('source_checks_completed') is True
            return complete
    except (OSError,ValueError,KeyError,TypeError,wave.Error):return False
    return False

def fingerprint(root):
    """Hash small artifacts; stat large immutable media. Paths remain lesson-relative."""
    result={'workflow_version':VERSION,'agent':settings()['agent'],'lesson':configuration(root),'files':{}}
    from .retention import receipt
    result['retention']=receipt(root)
    for path in sorted(root.rglob('*')):
        relative=path.relative_to(root)
        if not path.is_file() or relative.parts[0] in {'_runs','09_quality'} or path.name in {'status.json','index.html'}:continue
        stat=path.stat()
        if path.suffix in {'.mp4','.wav','.jpg','.png','.woff','.woff2','.ttf'}:
            result['files'][str(relative)]={'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}
        else:result['files'][str(relative)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    return hashlib.sha256(json.dumps(result,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def plan(root):
    frozen=root/'_runs/pipeline/frozen.json';same=frozen.exists() and load(frozen).get('fingerprint')==fingerprint(root)
    return {'workflow_version':VERSION,'lesson':str(root),'frozen_cache_valid':same,
            'stages':[{'stage':stage,'action':'reuse' if ready(root,stage) else 'run'} for stage in STAGES],
            'model':settings()['agent']['model'],'reasoning_effort':settings()['agent']['reasoning_effort']}

def verify(root):
    from .cli import verify as verify_lesson
    if verify_lesson(root)!=0:raise RuntimeError('课程文件检查未通过')

def freeze(root):
    if not all(ready(root,stage) for stage in STAGES):raise RuntimeError('所有阶段及完成门禁通过后才能固定缓存')
    for key in ('model','reasoning_effort'):
        if load(root/'status.json')['agent'][key]!=settings()['agent'][key]:raise RuntimeError('现有产物模型与当前配置不同，不能直接固定缓存')
    verify(root)
    lesson=configuration(root);video=root/lesson['inputs']['video']
    source=next((item for item in reversed([json.loads(x) for x in (root/'00_sources/sources.jsonl').read_text().splitlines()]) if item.get('path')==lesson['inputs']['video']),None)
    if not video.exists():
        from .retention import receipt,removed,sha
        cleanup=receipt(root)
        if not removed(root,lesson['inputs']['video']):raise RuntimeError('视频缺失且没有已确认报告的清理回执')
        entry=next(item for item in cleanup['files'] if item['path']==lesson['inputs']['video'])
        if not source or entry['sha256']!=source['sha256']:raise RuntimeError('清理回执与视频来源不一致')
        if cleanup['confirmed_report']['report_md_sha256']!=sha(root/'08_report/课程讲解报告.md'):raise RuntimeError('报告发生变化，请重新确认后再固定缓存')
        data={'workflow_version':VERSION,'fingerprint':fingerprint(root),'video_sha256':entry['sha256'],'media_deleted':True,
              'frozen_at':datetime.now(timezone.utc).isoformat(),'stages':list(STAGES),'note':'原音视频已在报告检查通过后清理；保留文字、图片、教材和来源身份。'}
        save(root/'_runs/pipeline/frozen.json',data);return data
    if not source or source.get('bytes')!=video.stat().st_size:raise RuntimeError('视频来源登记/文件大小不匹配')
    marker=root/'_runs/pipeline/frozen.json';prior=load(marker) if marker.exists() else {}
    video_stat={'size':video.stat().st_size,'mtime_ns':video.stat().st_mtime_ns}
    if prior.get('video_stat')!=video_stat or prior.get('video_sha256')!=source['sha256']:
        digest=hashlib.sha256()
        with video.open('rb') as stream:
            for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
        if digest.hexdigest()!=source['sha256']:raise RuntimeError('视频SHA-256与下载回执不匹配')
    data={'workflow_version':VERSION,'fingerprint':fingerprint(root),'video_stat':video_stat,'video_sha256':source['sha256'],
          'frozen_at':datetime.now(timezone.utc).isoformat(),'stages':list(STAGES),'note':'同一输入及产物重复运行仅验证，不调用模型。输入变化需重新核对，禁止盲目覆盖。'}
    save(marker,data);return data

def assets(root):
    destination=root/'08_report/assets/katex'
    if (destination/'katex.js').exists():return
    source=PROJECT/'node_modules/katex/dist'
    if not source.is_dir():raise RuntimeError('缺少离线公式依赖，请先在项目根目录运行npm ci --ignore-scripts')
    shutil.copytree(source,destination)

def ocr(root):
    binary=Path(settings().get('runtime',{}).get('ocr_binary','~/.local/share/codex-course-tools/board-ocr')).expanduser()
    if not binary.is_file():
        compiler=shutil.which('swiftc')
        if not compiler:raise RuntimeError('Apple Vision OCR需要macOS与swiftc')
        binary.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run([compiler,str(PROJECT/'scripts/board_ocr.swift'),'-o',str(binary)],check=True)
    target=root/'03_board/raw/ocr_raw.jsonl'
    if target.exists():
        history=root/'_runs/pipeline/ocr_partial';history.mkdir(parents=True,exist_ok=True)
        target.rename(history/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.jsonl'))
    subprocess.run([str(binary),str(root/'02_frames/board'),str(target)],check=True)

def run(root):
    lesson=configuration(root)
    if lesson['inputs'].get('slides'):raise RuntimeError('课件解析尚未接入；教材PDF可通过documents配置接入')
    frozen=root/'_runs/pipeline/frozen.json'
    if frozen.exists():
        if load(frozen).get('fingerprint')==fingerprint(root) and all(ready(root,stage) for stage in STAGES):
            verify(root);print('CACHE_HIT: 全流程产物有效，模型调用=0。',flush=True);return
        if ready(root,'finish'):raise RuntimeError('已固定课程的输入或产物发生变化；请先核对变化并verify/freeze，不自动重做整课')
    if not (root/lesson['inputs']['video']).is_file():
        from .retention import removed
        if not removed(root,lesson['inputs']['video']):raise RuntimeError('缺少原视频；先使用download工具获取并登记')
    assets(root)
    commands={'audio':['prepare_media.py','--stage','audio'],'frames':['prepare_media.py','--stage','frames'],
              'vad':['detect_speech.py'],'asr':['transcribe_vad.py'],'finish':['finish_lesson.py']}
    for stage in STAGES:
        if ready(root,stage):print('REUSE',stage,flush=True);continue
        print('START',stage,flush=True)
        save(root/'_runs/pipeline/status.json',{'stage':stage,'status':'running','workflow_version':VERSION})
        if stage=='ocr':ocr(root)
        elif stage=='documents':
            from .documents import prepare
            prepare(root)
        else:
            command=commands[stage]
            subprocess.run([sys.executable,'-u',str(PROJECT/'scripts'/command[0]),'--lesson',str(root),*command[1:]],cwd=PROJECT,check=True)
        if not ready(root,stage):raise RuntimeError(f'{stage}完成检查未通过')
        if stage=='audio':
            with wave.open(str(root/'01_audio/audio.wav')) as audio:count=math.ceil(audio.getnframes()/audio.getframerate()/lesson['asr']['chunk_seconds'])
            state=load(root/'status.json');state['total_chunks']=count;save(root/'status.json',state)
    freeze(root);save(root/'_runs/pipeline/status.json',{'status':'completed','workflow_version':VERSION})

def main():
    from .cli import lesson_path
    parser=argparse.ArgumentParser(description='固定流程v2：25秒抽帧、教材页级证据、报告确认后媒体清理')
    sub=parser.add_subparsers(dest='action',required=True)
    init=sub.add_parser('init')
    for key in ('subject','title','date'):init.add_argument('--'+key,required=True)
    init.add_argument('--week',required=True,type=int);init.add_argument('--session',required=True,type=int)
    init.add_argument('--roi',nargs=4,type=int,required=True)
    for action in ('plan','freeze','run'):
        item=sub.add_parser(action);item.add_argument('--lesson')
        if action=='run':item.add_argument('--foreground',action='store_true')
    document=sub.add_parser('documents');document.add_argument('--lesson')
    document.add_argument('--source',required=True,type=Path);document.add_argument('--id',required=True);document.add_argument('--title',required=True)
    document.add_argument('--pages',nargs=2,type=int,action='append',required=True);document.add_argument('--visual-pages',nargs='*',type=int,default=[])
    document.add_argument('--printed-offset',type=int)
    cleanup=sub.add_parser('cleanup');cleanup.add_argument('--lesson')
    args=parser.parse_args()
    if args.action=='init':print(initialize(args.subject,args.week,args.session,args.title,args.date,args.roi));return 0
    root=lesson_path(args.lesson)
    if args.action=='documents':
        lesson=configuration(root);item={'id':args.id,'path':str(args.source.expanduser().resolve()),'title':args.title,'role':'textbook',
                                         'pdf_page_ranges':args.pages,'visual_pages':args.visual_pages}
        if args.printed_offset is not None:item['printed_page_offset']=args.printed_offset
        sources=lesson.setdefault('documents',{}).setdefault('sources',[])
        sources[:]=[entry for entry in sources if entry['id']!=args.id]+[item];lesson['inputs']['textbook']=item['path']
        (root/'lesson.yaml').write_text(yaml.safe_dump(lesson,allow_unicode=True,sort_keys=False))
        from .documents import prepare
        print(json.dumps(prepare(root),ensure_ascii=False,indent=2));return 0
    if args.action=='cleanup':
        from .retention import confirm_and_cleanup
        print(json.dumps(confirm_and_cleanup(root),ensure_ascii=False,indent=2));return 0
    if args.action=='plan':print(json.dumps(plan(root),ensure_ascii=False,indent=2));return 0
    if args.action=='freeze':print(json.dumps(freeze(root),ensure_ascii=False,indent=2));return 0
    if args.foreground:
        try:run(root)
        except Exception as error:
            save(root/'_runs/pipeline/status.json',{'status':'failed','error':str(error),'workflow_version':VERSION});raise
    else:
        frozen=root/'_runs/pipeline/frozen.json'
        if frozen.exists() and load(frozen).get('fingerprint')==fingerprint(root) and all(ready(root,stage) for stage in STAGES):
            run(root);return 0
        subprocess.run([str(PROJECT/'bin/lecture-agent'),'background','start','--lesson',str(root),'--stage','pipeline','--',sys.executable,
                        '-m','lecture_agent.pipeline','run','--foreground','--lesson',str(root)],cwd=PROJECT,check=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
