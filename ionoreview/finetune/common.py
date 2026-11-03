from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
DEFAULT_CONFIG=PROJECT/'training/config.json'


def config(path=None):
    from ..data import read_json
    cfg=read_json(path or DEFAULT_CONFIG)
    for key in ['cache_dir','run_root','helper_root','dataset_root']:
        p=Path(os.path.expandvars(cfg[key])).expanduser()
        cfg[key]=str((PROJECT/p).resolve() if not p.is_absolute() else p.resolve())
    return cfg


def snapshot(cfg,download=False):
    from huggingface_hub import snapshot_download
    return Path(snapshot_download(cfg['model_id'],revision=cfg['model_revision'],
        cache_dir=cfg['cache_dir'],local_files_only=not download,token=False,
        allow_patterns=['*.json','*.safetensors','*.jinja','*.txt','*.model'],max_workers=4))


def rows(folder,split):
    if split not in {'train','validation','test'}:raise ValueError('Unknown split')
    return [json.loads(line) for line in (Path(folder)/f'{split}.jsonl').read_text(encoding='utf8').splitlines()]


def latest_dataset(cfg):
    from ..data import read_json
    return Path(read_json(Path(cfg['dataset_root'])/'latest.json')['path'])


@contextmanager
def gpu_lease(cfg,purpose):
    helper=Path(cfg['helper_root'])
    if not (helper/'llmhelper/lock.py').is_file():
        raise ValueError('local_llm_helper not found; check helper_root')
    sys.path.insert(0,str(helper))
    from llmhelper.config import get_config
    from llmhelper.lock import gpu_lease as acquire
    with acquire(get_config(),purpose,wait_s=0):yield


def require_gpu(cfg,training=False):
    import torch
    if not torch.cuda.is_available():raise RuntimeError('CUDA PyTorch is required')
    free,total=torch.cuda.mem_get_info()
    needed=cfg['min_train_vram_gib'] if training else cfg['min_inference_vram_gib']
    if free/1024**3<needed:
        raise RuntimeError(f'Only {free/1024**3:.1f} GiB GPU memory free; need {needed} GiB. '
            'Finish other GPU work and unload LM Studio models manually. No processes were stopped.')
    return {'name':torch.cuda.get_device_name(),'free_gib':free/1024**3,'total_gib':total/1024**3}
