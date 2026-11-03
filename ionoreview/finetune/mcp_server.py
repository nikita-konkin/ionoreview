"""Image-aware training sidecar. Heavy work is queued; no images enter MCP text."""
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import psutil
from mcp.server.fastmcp import FastMCP

from ..data import atomic_json,read_json,safe_child,utcnow
from .common import config,latest_dataset,PROJECT

mcp=FastMCP('ionogram-training',instructions='Prepare accepted-only ionogram datasets, start local fine-tuning and create LabelMe proposals. '
    'Training and inference are queued subprocesses sharing the local_llm_helper GPU lease. '
    'No tool automatically accepts or replaces expert annotations. Model outputs are untrusted proposals.')


def checked_name(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value):raise ValueError('Invalid name')
    return value


def launch(arguments,kind,job_id=None):
    cfg=config();job_id=job_id or uuid.uuid4().hex
    job=Path(cfg['run_root'])/'jobs'/job_id
    job.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,'-m','ionoreview.finetune','--job-dir',str(job),*arguments]
    env=os.environ.copy();env['PYTHONUTF8']='1';env['PYTHONUNBUFFERED']='1'
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    with (job/'log.txt').open('w',encoding='utf8') as log:
        process=subprocess.Popen(command,cwd=PROJECT,stdout=log,stderr=subprocess.STDOUT,
            env=env,creationflags=flags)
    try:created=psutil.Process(process.pid).create_time()
    except psutil.NoSuchProcess:created=None
    atomic_json(job/'job.json',{'job_id':job_id,'kind':kind,'pid':process.pid,'process_created':created,
        'started_at':utcnow(),'command':command})
    return {'job_id':job_id,'state':'started','log':str(job/'log.txt'),'poll_tool':'training_job_status'}


@mcp.tool()
def training_dataset_status() -> dict:
    """Counts and checks for the current immutable dataset. No model/GPU work."""
    cfg=config()
    try:folder=latest_dataset(cfg)
    except FileNotFoundError:return {'state':'not_prepared'}
    report=read_json(folder/'report.json')
    token=folder/'tokenization_report.json'
    return {'path':str(folder),'sources':report['source_images'],'tiles':report['tiles'],
        'class_coverage':report['class_coverage'],'tokenization':read_json(token) if token.exists() else 'not checked'}


@mcp.tool()
def prepare_training_data() -> dict:
    """Queue a new snapshot from accepted annotations; does not train or alter annotations."""
    return launch(['prepare'],'prepare')


@mcp.tool()
def inspect_training_data() -> dict:
    """Queue tokenization/loss-mask checks on the prepared snapshot, without GPU training."""
    return launch(['inspect'],'inspect')


@mcp.tool()
def start_finetune(run_name: str, max_steps: int = 0) -> dict:
    """Start local LoRA training. Requires sufficient free VRAM; never unloads other models."""
    checked_name(run_name)
    if not 0<=max_steps<=100000:raise ValueError('Invalid max_steps')
    args=['train','--name',run_name]
    if max_steps:args+=['--max-steps',str(max_steps)]
    return launch(args,'train')


@mcp.tool()
def propose_ionogram(pack: str, case_id: str, run_name: str = '') -> dict:
    """Queue vision inference and save a pending LabelMe proposal outside expert annotations.

    Empty run_name explicitly uses the untrained base model. Otherwise the named adapter must exist.
    """
    checked_name(pack);checked_name(case_id)
    safe_child(PROJECT/'datasets',pack)
    cfg=config();job_id=uuid.uuid4().hex
    out=Path(cfg['run_root'])/'jobs'/job_id/'prediction'
    args=['predict','--pack',pack,'--case',case_id,'--out',str(out)]
    if run_name:
        checked_name(run_name);adapter=Path(cfg['run_root'])/run_name/'adapter'
        if not (adapter/'adapter_config.json').is_file():raise ValueError('Adapter is not trained or missing')
        args+=['--adapter',str(adapter)]
    result=launch(args,'predict',job_id)
    result['uses_trained_adapter']=bool(run_name)
    return result


@mcp.tool()
def training_job_status(job_id: str) -> dict:
    """Read progress/result paths of one job; does not return raw model text or image data."""
    if not re.fullmatch(r'[a-f0-9]{32}',job_id):raise ValueError('Invalid job id')
    job=Path(config()['run_root'])/'jobs'/job_id
    metadata=read_json(job/'job.json')
    for filename,state in [('done.json','done'),('failed.json','failed')]:
        if (job/filename).is_file():return {'state':state,**read_json(job/filename),'log':str(job/'log.txt')}
    alive=False
    try:alive=abs(psutil.Process(metadata['pid']).create_time()-metadata['process_created'])<.1
    except (psutil.NoSuchProcess,TypeError):pass
    return {'state':'running' if alive else 'stopped_without_result','log':str(job/'log.txt')}


if __name__=='__main__':mcp.run(transport='stdio')
