"""Explicit project Codex model/effort execution with per-task evidence."""
from pathlib import Path
import argparse
from datetime import datetime,timezone
import json,shutil,subprocess,hashlib
import yaml

PROJECT=Path(__file__).resolve().parents[2]

def execute(lesson,task,prompt,images=(),expected_outputs=(),gates=None):
    config=yaml.safe_load((PROJECT/'configs/default.yaml').read_text())['agent']
    model=config['model'];effort=config['reasoning_effort']
    cache=Path.home()/'.codex/models_cache.json'
    if cache.exists():
        available=next((m for m in json.loads(cache.read_text()).get('models',[]) if m.get('slug')==model),None)
        if available is None or effort not in {e['effort'] for e in available.get('supported_reasoning_levels',[])}:
            raise RuntimeError('本机模型列表未确认所需模型与推理强度，拒绝静默降级。')
    executable=shutil.which('codex')
    if not executable:raise RuntimeError('找不到Codex CLI。')
    folder=lesson/'_runs/workflow_validation/codex'/task;folder.mkdir(parents=True,exist_ok=True)
    completion=folder/'completed.json'
    digest=hashlib.sha256(prompt.encode()).hexdigest()
    if completion.exists() and all((lesson/x).is_file() for x in expected_outputs):
        previous=json.loads(completion.read_text())
        gates_valid=True
        for filename,fields in (gates or {}).items():
            try:
                data=json.loads((lesson/filename).read_text())
                gates_valid &= all(data.get(key)==value and type(data.get(key)) is type(value) for key,value in fields.items())
            except (OSError,ValueError):gates_valid=False
        if previous.get('model')==model and previous.get('reasoning_effort')==effort and previous.get('prompt_sha256')==digest and gates_valid:
            return previous
    if (folder/'execution.json').exists():
        history=folder.parent/'_history';history.mkdir(exist_ok=True)
        folder.rename(history/(task+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')))
        folder.mkdir()
    (folder/'prompt.md').write_text(prompt)
    command=[executable,'-a','never','exec','--sandbox','workspace-write','--skip-git-repo-check','--ephemeral','-C',str(PROJECT),'--model',model,'-c',f'model_reasoning_effort="{effort}"','--json','--output-last-message',str(folder/'last_message.md')]
    for image in images:command.extend(['--image',str(image)])
    command.extend(['--','-'])
    metadata={'model':model,'reasoning_effort':effort,'command':command,'task':task,'prompt_sha256':digest,'started_at':datetime.now(timezone.utc).isoformat(),'status':'running','images':[str(p.relative_to(lesson)) for p in images]}
    (folder/'execution.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    with (folder/'events.jsonl').open('w') as stdout,(folder/'stderr.log').open('w') as stderr:
        result=subprocess.run(command,input=prompt,text=True,stdout=stdout,stderr=stderr,cwd=PROJECT)
    metadata.update(returncode=result.returncode,status='completed' if result.returncode==0 else 'failed',finished_at=datetime.now(timezone.utc).isoformat())
    metadata['missing_outputs']=[x for x in expected_outputs if not (lesson/x).is_file()]
    if metadata['missing_outputs']:metadata['status']='failed'
    metadata['gate_errors']=[]
    for filename,fields in (gates or {}).items():
        try:
            data=json.loads((lesson/filename).read_text())
            for key,wanted in fields.items():
                if data.get(key)!=wanted:metadata['gate_errors'].append(f'{filename}: {key} != {wanted}')
        except (OSError,ValueError) as error:metadata['gate_errors'].append(f'{filename}: {error}')
    if metadata['gate_errors']:metadata['status']='incomplete'
    (folder/'execution.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    if result.returncode or metadata['missing_outputs'] or metadata['gate_errors']:raise RuntimeError(f'Codex任务{task}未完成，见{folder}；未标为完成。')
    completion.write_text(json.dumps(metadata,ensure_ascii=False,indent=2));return metadata

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--lesson',required=True);parser.add_argument('--task',required=True);parser.add_argument('--prompt',type=Path,required=True)
    args=parser.parse_args();execute((PROJECT/'outputs'/args.lesson).resolve(),args.task,args.prompt.read_text())

if __name__=='__main__':main()
