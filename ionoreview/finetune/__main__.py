import argparse
import json
from pathlib import Path
import sys

from ..data import atomic_json,utcnow
from .common import config,latest_dataset,PROJECT


def main(argv=None):
    parser=argparse.ArgumentParser(description='Local ionogram VLM fine-tuning and proposals')
    parser.add_argument('--config',type=Path)
    parser.add_argument('--job-dir',type=Path)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('prepare');sub.add_parser('fetch')
    inspect=sub.add_parser('inspect');inspect.add_argument('--dataset',type=Path)
    diag=sub.add_parser('doctor');diag.add_argument('--cuda-smoke',action='store_true');diag.add_argument('--load-cpu',action='store_true')
    train=sub.add_parser('train');train.add_argument('--name',required=True);train.add_argument('--max-steps',type=int);train.add_argument('--dataset',type=Path)
    pred=sub.add_parser('predict');pred.add_argument('--pack',required=True);pred.add_argument('--case',required=True);pred.add_argument('--out',type=Path,required=True);pred.add_argument('--adapter',type=Path)
    predict_set=sub.add_parser('predict-set');predict_set.add_argument('--dataset',type=Path);predict_set.add_argument('--split',choices=['validation','test'],default='validation');predict_set.add_argument('--out',type=Path,required=True);predict_set.add_argument('--adapter',type=Path)
    pack_pred=sub.add_parser('predict-pack');pack_pred.add_argument('--pack-path',type=Path,required=True);pack_pred.add_argument('--out',type=Path,required=True);pack_pred.add_argument('--adapter',type=Path)
    evaluate=sub.add_parser('evaluate');evaluate.add_argument('--dataset',type=Path);evaluate.add_argument('--split',choices=['validation','test'],default='validation');evaluate.add_argument('--predictions',type=Path,required=True)
    merge=sub.add_parser('merge');merge.add_argument('--adapter',type=Path,required=True);merge.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv);cfg=config(args.config)
    try:
        if args.command=='prepare':
            from .dataset import prepare
            result=prepare(cfg)
        elif args.command=='fetch':
            from .common import snapshot
            result={'path':str(snapshot(cfg,download=True))}
        elif args.command=='doctor':
            from .diagnostics import doctor
            result=doctor(cfg,args.cuda_smoke,args.load_cpu)
        elif args.command=='inspect':
            from .runtime import inspect_data
            result=inspect_data(cfg,args.dataset or latest_dataset(cfg))
        elif args.command=='train':
            from .runtime import train
            if args.max_steps is not None and args.max_steps<1:raise ValueError('max-steps must be positive')
            result=train(cfg,args.dataset or latest_dataset(cfg),args.name,args.max_steps)
        elif args.command=='predict':
            from .predict import predict_case
            from ..data import safe_child
            result=predict_case(cfg,safe_child(PROJECT/'datasets',args.pack),args.case,args.out,args.adapter)
        elif args.command=='predict-set':
            from .predict import predict_split
            result=predict_split(cfg,args.dataset or latest_dataset(cfg),args.split,args.out,args.adapter)
        elif args.command=='predict-pack':
            from .predict import predict_pack
            result=predict_pack(cfg,args.pack_path,args.out,args.adapter)
        elif args.command=='evaluate':
            from .evaluate import evaluate
            result=evaluate(args.dataset or latest_dataset(cfg),args.split,args.predictions)
        elif args.command=='merge':
            from .runtime import merge_adapter
            result=merge_adapter(cfg,args.adapter,args.out)
        if args.job_dir:atomic_json(args.job_dir/'done.json',{'finished_at':utcnow(),'result':result})
        print(json.dumps(result,ensure_ascii=True,indent=2))
        return 0
    except Exception as exc:
        if args.job_dir:atomic_json(args.job_dir/'failed.json',{'failed_at':utcnow(),'error':str(exc),'type':type(exc).__name__})
        print(f'{type(exc).__name__}: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
