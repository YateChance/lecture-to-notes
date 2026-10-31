"""Prepare lesson audio or timestamped frames using the registered local video."""
from course_context import LESSON_ROOT as root, LESSON
from pathlib import Path
import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import subprocess
import uuid
import wave
from PIL import Image, ImageEnhance, ImageDraw

parser=argparse.ArgumentParser()
parser.add_argument('--lesson')
parser.add_argument('--stage',choices=['audio','frames','contacts'],required=True)
args=parser.parse_args()
video=root/LESSON['inputs']['video']
run=root/'_runs'/('prepare_'+uuid.uuid4().hex[:10]);run.mkdir(parents=True)
if args.stage=='contacts':
    files=sorted((root/'02_frames/board').glob('*.jpg'))
    if not files:raise RuntimeError('请先生成板书裁剪图')
    stride=max(1,round(100/float(LESSON.get('frames',{}).get('sample_seconds',10))))
    selected=files[::stride]
    if selected[-1]!=files[-1]:selected.append(files[-1])
    target=root/'_runs/workflow_validation/contact_sheets';target.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for i in range(0,len(selected),3):
        sheet=Image.new('RGB',(1270,1560),'white');draw=ImageDraw.Draw(sheet)
        for j,path in enumerate(selected[i:i+3]):
            with Image.open(path) as source:
                image=source.convert('RGB');image.thumbnail((1270,485))
                sheet.paste(image,(0,j*520+30));draw.text((10,j*520+5),path.name,fill='black')
        name=f'contact_{i//3+1:02d}.jpg';sheet.save(target/name,quality=90)
        manifest.append({'file':name,'board_images':[str(p.relative_to(root)) for p in selected[i:i+3]]})
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print('Contact sheets:',len(manifest))
elif args.stage=='audio':
    target=root/'01_audio/audio.wav'
    if target.exists():
        with wave.open(str(target)) as wav:assert wav.getnframes()>0 and wav.getframerate()==16000
        print('Reuse audio:',target)
    else:
        temporary=run/'audio.wav'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(video),'-vn','-ar','16000','-ac','1','-c:a','pcm_s16le',str(temporary)],check=True)
        with wave.open(str(temporary)) as wav:assert wav.getnframes()>0 and wav.getnchannels()==1
        temporary.rename(target)
        print('Audio ready:',target)
else:
    stage=root/'02_frames'
    if (stage/'extraction.json').exists():
        summary=json.loads((stage/'extraction.json').read_text())
        assert len(list((stage/'full').glob('*.jpg')))==summary['frames']
        print('Reuse verified frame extraction:',summary['frames'])
        raise SystemExit(0)
    interval=float(LESSON.get('frames',{}).get('sample_seconds',10))
    roi=tuple(LESSON.get('frames',{}).get('board_roi',[0,0,1920,1080]))
    frames=run/'frames';frames.mkdir()
    log=run/'ffmpeg.log'
    expression=f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{interval})',showinfo"
    with log.open('w') as handle:
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','info','-i',str(video),'-vf',expression,'-fps_mode','vfr','-q:v','3',str(frames/'frame_%04d.jpg')],stdout=handle,stderr=subprocess.STDOUT,check=True)
    times=[float(x) for x in re.findall(r'Parsed_showinfo[^\n]*?\bn:\s*\d+[^\n]*?pts_time:([\d.e+-]+)',log.read_text())]
    paths=sorted(frames.glob('*.jpg'))
    assert len(times)==len(paths) and len(paths)>0,(len(times),len(paths))
    rows=[];cards=[]
    for number,(source,t) in enumerate(zip(paths,times),1):
        seconds=int(t);stamp=f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}'
        target=stage/'full'/source.name
        if target.exists():
            assert hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(source.read_bytes()).digest(),'Existing original differs'
        else:shutil.copy2(source,target)
        name=f'{number:04d}_{stamp.replace(":","-")}.jpg'
        crop=stage/'board'/name
        if not crop.exists():
            im=Image.open(target);assert roi[2]<=im.width and roi[3]<=im.height
            ImageEnhance.Contrast(im.crop(roi)).enhance(float(LESSON.get('frames',{}).get('contrast',1))).save(crop,quality=92)
        rows.append({'序号':number,'视频时间':stamp,'时间秒':t,'原图':'full/'+target.name,'板书裁剪图':'board/'+name})
        cards.append(f'<article id="frame_{number:04d}"><h2>{stamp}</h2><a href="full/{target.name}"><img loading="lazy" src="board/{name}" alt="{stamp}板书"></a></article>')
    with (stage/'帧索引.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    (stage/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>'+html.escape(root.name)+'</title><style>body{max-width:1300px;margin:30px auto;font:17px system-ui}img{width:100%}article{margin:30px 0}</style><h1>'+html.escape(root.name)+'</h1>'+''.join(cards))
    summary={'frames':len(rows),'interval_seconds':interval,'timestamps':'actual selected video frame PTS','roi':roi,'log':str(log.relative_to(root))}
    (stage/'extraction.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print('Frames ready:',len(rows),flush=True)
