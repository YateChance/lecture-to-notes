"""Detached local supervision. Reporting never invokes a language model."""
from pathlib import Path
from datetime import datetime, timezone
import argparse,json,os,subprocess,sys,time,uuid

PROJECT=Path(__file__).resolve().parents[2]

def now():return datetime.now(timezone.utc).isoformat()

def write(path,data):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    temporary.replace(path)

def snapshot(lesson,log):
    def count(folder,pattern):return sum(1 for _ in (lesson/folder).glob(pattern))
    video=lesson/'00_sources/video/lecture.mp4'
    return {'asr_chunks':count('04_transcripts','chunk_*.json'),
            'frames':count('02_frames/full','*.jpg'),
            'board_images':count('02_frames/board','*.jpg'),
            'video_bytes':video.stat().st_size if video.exists() else 0,
            'worker_log_bytes':log.stat().st_size if log.exists() else 0}

def supervise(job):
    os.umask(0o077)
    config=json.loads((job/'request.json').read_text())
    lesson=Path(config['lesson']);log=job/'worker.log'
    interval=config['report_interval_seconds'];check=config['process_check_seconds']
    state={**config,'status':'starting','supervisor_pid':os.getpid(),'started_at':now()}
    began=time.monotonic();last=None;unchanged=0
    def report(reason):
        nonlocal last,unchanged
        progress=snapshot(lesson,log)
        unchanged=unchanged+1 if progress==last else 0;last=progress
        state.update(progress=progress,elapsed_seconds=round(time.monotonic()-began,1),updated_at=now(),reason=reason,
                     attention='连续两次20分钟回报无可见进展，请检查' if unchanged>=2 else None)
        write(job/'status.json',state)
        with (job/'reports.jsonl').open('a') as stream:stream.write(json.dumps(state,ensure_ascii=False)+'\n')
    try:
        with log.open('ab',buffering=0) as stream:
            process=subprocess.Popen(config['command'],cwd=PROJECT,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,close_fds=True)
            state.update(status='running',worker_pid=process.pid);report('started')
            deadline=time.monotonic()+interval
            while True:
                try:
                    code=process.wait(timeout=min(check,max(.01,deadline-time.monotonic())))
                    state.update(status='completed' if code==0 else 'failed',exit_code=code,finished_at=now())
                    report('completed' if code==0 else 'failed');return code
                except subprocess.TimeoutExpired:
                    if time.monotonic()>=deadline:
                        report('periodic');deadline=time.monotonic()+interval
    except Exception as error:
        state.update(status='failed',error=str(error),finished_at=now());report('supervisor_error');return 1

def main():
    from .cli import lesson_path,settings
    parser=argparse.ArgumentParser(description='本地后台监督；20分钟写回报，无模型轮询')
    sub=parser.add_subparsers(dest='action',required=True)
    start=sub.add_parser('start');start.add_argument('--lesson');start.add_argument('--stage',required=True)
    start.add_argument('command',nargs=argparse.REMAINDER)
    status=sub.add_parser('status');status.add_argument('--lesson');status.add_argument('--job')
    worker=sub.add_parser('worker');worker.add_argument('--job',required=True,type=Path)
    args=parser.parse_args()
    if args.action=='worker':return supervise(args.job.resolve())
    lesson=lesson_path(args.lesson);jobs=lesson/'_runs/background'
    if args.action=='start':
        command=args.command[1:] if args.command[:1]==['--'] else args.command
        if not command:parser.error('在 -- 后提供实际命令')
        options=settings().get('background',{})
        interval=float(options.get('report_interval_seconds',1200));check=float(options.get('process_check_seconds',5))
        if interval<=0 or check<=0:parser.error('监督时间间隔必须大于0')
        identifier=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
        job=jobs/identifier;job.mkdir(parents=True,mode=0o700)
        request={'job_id':identifier,'stage':args.stage,'lesson':str(lesson),'command':command,
                 'report_interval_seconds':interval,'process_check_seconds':check,'created_at':now(),
                 'scope':'仅此命令，不代表整课完成；启动后的聊天回报须由Codex登记20分钟心跳'}
        write(job/'request.json',request)
        write(job/'status.json',{**request,'status':'queued'})
        with (job/'supervisor.log').open('ab') as stream:
            process=subprocess.Popen([sys.executable,'-m','lecture_agent.background','worker','--job',str(job)],cwd=PROJECT,
                                     stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        print(json.dumps({'job_id':identifier,'supervisor_pid':process.pid,'report_interval_minutes':interval/60,
                          'status_file':str(job/'status.json'),'reports_file':str(job/'reports.jsonl'),
                          'next_action':'Codex登记20分钟聊天心跳后结束当前轮；不要持续轮询。'},ensure_ascii=False,indent=2));return 0
    paths=[jobs/args.job] if args.job else sorted(jobs.glob('*')) if jobs.exists() else []
    results=[]
    for job in paths:
        path=job/'status.json'
        if path.is_file():
            data=json.loads(path.read_text())
            if data.get('status')=='running':
                try:os.kill(data['supervisor_pid'],0)
                except ProcessLookupError:data.update(status='supervisor_unavailable',attention='监督进程已退出，阶段是否完成需核对；不把旧PID视为正在运行。')
            results.append({key:value for key,value in data.items() if key!='command'})
    print(json.dumps(results,ensure_ascii=False,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
