"""Resumable archive preparation. Source recordings are never written to N:."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import time
import warnings
import zipfile

import numpy as np
from PIL import Image
from matplotlib import colormaps

from .data import atomic_json, digest, read_json, utcnow
from .prepare import POLICY

REMOTE = 0x1000 | 0x40000 | 0x400000


def kind_of(name):
    name = name.lower()
    if name.endswith('.lfs'):
        return 'lfs'
    if name.startswith('lfm_ionogram-') and name.endswith('.h5'):
        return 'chirp_h5'
    if name.startswith('digisonde_ionogram-') and name.endswith('.h5'):
        return 'digisonde_h5'
    return None


def discover(root, pilot=None):
    root = Path(root).resolve()
    known = set()
    if pilot and (Path(pilot)/'manifest.json').exists():
        known = {Path(i['source']).name.lower() for i in read_json(Path(pilot)/'manifest.json')['items']}
    records = {}
    ignored = Counter()
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for name in sorted(files):
            kind = kind_of(name)
            if kind is None:
                if name.lower().endswith('.h5'):
                    ignored['non_ionogram_h5'] += 1
                continue
            path = Path(folder)/name
            key = kind+'|'+name.lower()
            if name.lower() in known:
                ignored['already_in_pilot'] += 1
                continue
            try:
                stat = path.stat()
            except OSError:
                ignored['stat_error'] += 1
                continue
            candidate = {'path':str(path), 'size':stat.st_size, 'mtime_ns':stat.st_mtime_ns,
                         'remote':bool(getattr(stat,'st_file_attributes',0)&REMOTE)}
            if key not in records:
                records[key] = {'id':hashlib.sha256(key.encode()).hexdigest()[:20],
                                'kind':kind, 'name':name, 'sources':[]}
            records[key]['sources'].append(candidate)
    result = list(records.values())
    for record in result:
        record['sources'].sort(key=lambda s:(s['remote'], 'ionozond_data2' in s['path'], s['path']))
    result.sort(key=lambda r:(r['kind']=='lfs',r['kind'],r['name'].lower()))
    return {'schema':'ionoreview-inventory/1','created_at':utcnow(),'root':str(root),
            'records':result,'ignored':dict(ignored),
            'duplicate_paths':sum(len(r['sources'])-1 for r in result)}


def hydrate(inventory_path, checkpoint, workers=24, idle_timeout=120):
    """Read/hash cloud sources concurrently, with a bounded stalled tail.

    Workers only read files. Daemon threads let the command return if a cloud
    provider never completes one request; pending files remain in the report.
    """
    inventory = read_json(inventory_path)
    old = read_json(checkpoint) if Path(checkpoint).exists() else {'files':{}}
    completed = old['files']
    tasks = queue.Queue()
    results = queue.Queue()
    for record in inventory['records']:
        if record['kind']=='lfs':
            continue
        source = record['sources'][0]
        path = source['path']
        if not source['remote'] or completed.get(path,{}).get('ok'):
            continue
        tasks.put(source)
    total = tasks.qsize()
    print(f'HYDRATE {total} cloud products, {workers} readers',flush=True)
    def worker():
        while True:
            try: source=tasks.get_nowait()
            except queue.Empty: return
            start=time.monotonic()
            try:
                path=Path(source['path']); before=path.stat(); sha=digest(path); after=path.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                    raise ValueError('source changed while reading')
                value={'ok':True,'sha256':sha,'size':after.st_size,'mtime_ns':after.st_mtime_ns,
                       'seconds':round(time.monotonic()-start,3)}
            except Exception as exc:
                value={'ok':False,'error':str(exc),'seconds':round(time.monotonic()-start,3)}
            results.put((source['path'],value))
    for _ in range(workers):
        threading.Thread(target=worker,daemon=True).start()
    done=0; last=time.monotonic()
    while done<total:
        try: path,value=results.get(timeout=2)
        except queue.Empty:
            if time.monotonic()-last>idle_timeout:
                print('HYDRATE stalled tail deferred',flush=True)
                break
            continue
        completed[path]=value;done+=1;last=time.monotonic()
        if done%100==0 or done==total:
            atomic_json(checkpoint,{'schema':'ionoreview-hydration/1','updated_at':utcnow(),'files':completed})
            ok=sum(v['ok'] for v in completed.values())
            print(f'HYDRATE {done}/{total}; cached OK {ok}',flush=True)
    atomic_json(checkpoint,{'schema':'ionoreview-hydration/1','updated_at':utcnow(),
                           'files':completed,'attempted':done,'queued':total})


def palette_image(db):
    normalized=np.clip((np.nan_to_num(db,nan=15.,posinf=60.,neginf=15.)-15)/45,0,1)
    indices=np.minimum((normalized*256).astype(np.uint16),255).astype(np.uint8)
    image=Image.fromarray(indices)
    image=image.convert('P')
    image.putpalette(colormaps['turbo'](np.arange(256),bytes=True)[:,:3].flatten().tolist())
    return image


def save_arrays(path, db, freq, ranges):
    """Standard NPZ/NPY members, with lossless ZIP-LZMA compression.

    numpy.load reads these directly. Fortran storage improves compression of
    these range/frequency matrices without changing their shape or values.
    """
    path=Path(path)
    temporary=path.with_suffix('.npz.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_LZMA) as archive:
            arrays={'db':np.asfortranarray(db),'freq_mhz':freq,'range_km':ranges}
            for name,array in arrays.items():
                with archive.open(name+'.npy','w',force_zip64=True) as stream:
                    np.lib.format.write_array(stream,array,allow_pickle=False)
        temporary.replace(path)
    finally:
        if temporary.exists():temporary.unlink()


def split_day(day):
    fixed={'2026-10-17':'train','2026-10-18':'validation','2026-10-24':'test'}
    if day in fixed: return fixed[day]
    bucket=int(hashlib.sha256(day.encode()).hexdigest()[:8],16)%10
    return 'test' if bucket==0 else 'validation' if bucket==1 else 'train'


def initialize_worker(loader_project):
    sys.path.insert(0,str(loader_project))


def prepare_record(record, dataset_root, hydration, phase):
    from muf import loader
    errors=[]
    for source in record['sources']:
        path=Path(source['path'])
        # Avoid recalling a cloud source whose prefetch timed out/failed.
        attrs=getattr(path.stat(),'st_file_attributes',0)
        if attrs&REMOTE and not hydration.get(str(path),{}).get('ok'):
            errors.append(f'{path}: cloud product is not cached')
            continue
        try:
            started=time.monotonic()
            gate=(0.,8000.) if record['kind']=='lfs' else (-1e9,1e9)
            with warnings.catch_warnings(record=True) as notices:
                ion=loader.load(path,gate_km=gate,cache_dir=None)
            db=np.asarray(ion.db.T,dtype=np.float32)
            freq=np.asarray(ion.freq,dtype=np.float64)
            ranges=np.asarray(ion.vrange,dtype=np.float64)
            if min(db.shape)<2 or db.size>30_000_000:
                raise ValueError(f'unsupported matrix shape {db.shape}')
            if freq[0]>freq[-1]:db,freq=db[:,::-1],freq[::-1]
            if ranges[0]<ranges[-1]:db,ranges=db[::-1],ranges[::-1]
            if not np.all(np.isfinite(freq)) or not np.all(np.isfinite(ranges)) or not np.all(np.diff(freq)>0) or not np.all(np.diff(ranges)<0):
                raise ValueError('non-finite/non-monotone axes')
            day=ion.header.datetime.date().isoformat()
            pack_name=record['pack']
            pack=Path(dataset_root)/pack_name
            for folder in ('images','arrays','records','annotations'):(pack/folder).mkdir(parents=True,exist_ok=True)
            ident=record['id']
            image_file=f'images/{ident}.png'; array_file=f'arrays/{ident}.npz'
            image_path=pack/image_file; array_path=pack/array_file
            palette_image(db).save(image_path,optimize=False)
            save_arrays(array_path,db,freq,ranges)
            stat=path.stat(); cached=hydration.get(str(path),{})
            sha=(cached['sha256'] if cached.get('ok') and cached.get('size')==stat.st_size
                 and cached.get('mtime_ns')==stat.st_mtime_ns else digest(path))
            item={'id':ident,'image':image_file,'axes':array_file,
                'width':int(db.shape[1]),'height':int(db.shape[0]),
                'image_sha256':digest(image_path),'axes_sha256':digest(array_path),
                'source':str(path),'source_sha256':sha,'source_bytes':stat.st_size,
                'source_mtime_ns':stat.st_mtime_ns,'source_kind':record['kind'],
                'source_alternatives':[s['path'] for s in record['sources'] if s['path']!=str(path)],
                'when':ion.header.datetime.isoformat(),'tx':ion.header.tx_name,'rx':ion.header.rx_name,
                'split':split_day(day),'range_is_relative':bool(getattr(ion.header,'range_is_relative',False)),
                'range_is_configured':bool(getattr(ion.header,'range_is_configured',False)),
                'warnings':[str(w.message) for w in notices],
                'render':{'colormap':'turbo','vmin':15,'vmax':60,'matrix':'ion.db.T',
                          'filters':'none','palette_png':True,'numeric_precision':'float32',
                          'array_compression':'ZIP-LZMA; standard numpy.load'},
                'array_bytes':array_path.stat().st_size,'image_bytes':image_path.stat().st_size,
                'strong_points_43db':int(np.count_nonzero(np.isfinite(db)&(db>=43))),
                'processing_seconds':round(time.monotonic()-started,3)}
            atomic_json(pack/'records'/f'{ident}.json',item)
            return {'ok':True,'pack':pack_name,'item':item}
        except Exception as exc:
            errors.append(f'{path}: {type(exc).__name__}: {exc}')
    return {'ok':False,'id':record['id'],'name':record['name'],'kind':record['kind'],'errors':errors}


def write_manifests(dataset_root, pack_names, inventory):
    entries=[]
    # A resumed/subset run must retain packs prepared by an earlier phase.
    pack_names=set(pack_names)|{p.parent.name for p in Path(dataset_root).glob('*/records') if p.is_dir()}
    pilot=Path(dataset_root)/'pilot'
    if (pilot/'manifest.json').exists():
        p=read_json(pilot/'manifest.json')
        entries.append({'path':'pilot','title':'Пилот · ранее принятая разметка','count':len(p['items'])})
    for name in sorted(pack_names):
        pack=Path(dataset_root)/name
        items=[read_json(p) for p in sorted((pack/'records').glob('*.json'))]
        if not items:continue
        times=sorted(i['when'] for i in items)
        stations=sorted({i['tx']+' → '+i['rx'] for i in items if i['tx'] or i['rx']})
        kind=items[0]['source_kind']
        atomic_json(pack/'manifest.json',{'schema':'ionoreview/1','created_at':utcnow(),
            'items':items,'annotation_policy':POLICY if kind!='image' else
                'Разметка в пикселях архивного PNG. Числовых осей нет; подписи и поля сохранены. Не размечайте подписи как сигнал.',
            'errors':[],
            'sampling':'complete discovered archive batch; no signal-quality selection',
            'source_root':inventory['root'],'numeric_precision':'float32, no quantization' if kind!='image' else None,
            'date_range':[times[0],times[-1]],'stations':stations,
            'split_policy':'whole UTC day, stable SHA256 buckets; pilot day overrides'})
        kind_title={'chirp_h5':'ЛЧМ H5','digisonde_h5':'Digisonde H5','lfs':'ЛЧМ LFS',
                    'image':'PNG без числовых осей'}[kind]
        entries.append({'path':name,'title':f"{kind_title} · {name.rsplit('_',1)[-1]} · {times[0][:10]}…{times[-1][:10]}",
            'count':len(items),'date_range':[times[0],times[-1]],'stations':stations})
    pilot_entries=[e for e in entries if e['path']=='pilot']
    archive_entries=[e for e in entries if e['path']!='pilot']
    entries=pilot_entries+sorted(archive_entries,key=lambda e:e['date_range'][1],reverse=True)
    atomic_json(Path(dataset_root)/'catalog.json',{'schema':'ionoreview-library/1',
                'updated_at':utcnow(),'datasets':entries,'count':sum(e['count'] for e in entries)})
    return entries


def build(inventory_path, dataset_root, loader_project, hydration_path=None,
          workers=4, batch_size=300, min_free_gib=3, limit=None, resident_only=False):
    inventory=read_json(inventory_path)
    hydration=read_json(hydration_path)['files'] if hydration_path and Path(hydration_path).exists() else {}
    dataset_root=Path(dataset_root).resolve(); dataset_root.mkdir(parents=True,exist_ok=True)
    records=inventory['records']
    counters=Counter()
    for record in records:
        counters[record['kind']]+=1
        record['pack']=f"{record['kind']}_{(counters[record['kind']]-1)//batch_size+1:03d}"
    if resident_only:
        records=[r for r in records if any(not s['remote'] for s in r['sources'])]
    if limit: records=records[:limit]
    pack_names={r['pack'] for r in records}
    completed={p.stem for name in pack_names for p in (dataset_root/name/'records').glob('*.json')}
    pending=[r for r in records if r['id'] not in completed]
    errors_path=Path(inventory_path).parent/'preparation_errors.jsonl'
    report_path=Path(inventory_path).parent/'preparation_status.json'
    attempted=0;prepared=len(completed);failed=0;stop=None
    print(f'BUILD records {len(records)}, already prepared {prepared}, workers {workers}',flush=True)
    def report():
        atomic_json(report_path,{'updated_at':utcnow(),'inventory':len(inventory['records']),
            'prepared':prepared,'attempted_this_run':attempted,'failed_this_run':failed,
            'free_bytes':shutil.disk_usage(dataset_root).free,'stop_reason':stop})
    with ProcessPoolExecutor(max_workers=workers,initializer=initialize_worker,
                             initargs=(str(loader_project),)) as pool:
        active={}; iterator=iter(pending);exhausted=False
        while active or not exhausted:
            while len(active)<workers and not exhausted and stop is None:
                if shutil.disk_usage(dataset_root).free < min_free_gib*1024**3+512*1024**2:
                    stop='free disk reserve reached';exhausted=True;break
                try: record=next(iterator)
                except StopIteration:exhausted=True;break
                cache={s['path']:hydration[s['path']] for s in record['sources'] if s['path'] in hydration}
                future=pool.submit(prepare_record,record,str(dataset_root),cache,'all')
                active[future]=record
            if not active:break
            done,_=wait(active,timeout=3,return_when=FIRST_COMPLETED)
            if not done:continue
            for future in done:
                record=active.pop(future);attempted+=1
                try:result=future.result()
                except Exception as exc:result={'ok':False,'id':record['id'],'errors':[repr(exc)]}
                if result['ok']:prepared+=1
                else:
                    failed+=1
                    with open(errors_path,'a',encoding='utf-8') as stream:stream.write(json.dumps(result,ensure_ascii=False)+'\n')
            if attempted%50<len(done) or exhausted and not active:
                write_manifests(dataset_root,pack_names,inventory);report()
                print(f'BUILD {prepared}/{len(records)} prepared; failed {failed}; free {shutil.disk_usage(dataset_root).free/1024**3:.2f} GiB',flush=True)
    entries=write_manifests(dataset_root,pack_names,inventory);report()
    print(f'DONE {prepared} archive images, {len(entries)} packs; failed {failed}; stop {stop}',flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Подготовка архива для разметки')
    sub=parser.add_subparsers(dest='command',required=True)
    scan=sub.add_parser('inventory');scan.add_argument('root');scan.add_argument('out');scan.add_argument('--pilot')
    cache=sub.add_parser('hydrate');cache.add_argument('inventory');cache.add_argument('checkpoint');cache.add_argument('--workers',type=int,default=24)
    make=sub.add_parser('build');make.add_argument('inventory');make.add_argument('datasets');make.add_argument('--loader',required=True)
    make.add_argument('--hydration');make.add_argument('--workers',type=int,default=4);make.add_argument('--limit',type=int)
    make.add_argument('--batch-size',type=int,default=300);make.add_argument('--min-free-gib',type=float,default=3)
    make.add_argument('--resident-only',action='store_true')
    args=parser.parse_args(argv)
    if args.command=='inventory':
        result=discover(args.root,args.pilot);atomic_json(args.out,result)
        print(json.dumps({'unique_soundings':len(result['records']),'ignored':result['ignored'],
                          'duplicates':result['duplicate_paths'],'kinds':dict(Counter(r['kind'] for r in result['records']))},indent=2))
    elif args.command=='hydrate':hydrate(args.inventory,args.checkpoint,args.workers)
    else:build(args.inventory,args.datasets,args.loader,args.hydration,args.workers,args.batch_size,args.min_free_gib,args.limit,args.resident_only)


if __name__=='__main__':main()
