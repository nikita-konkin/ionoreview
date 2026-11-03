"""Collect archived PNG-only soundings without duplicating prepared raw data."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from PIL import Image

from .archive import split_day, write_manifests
from .data import atomic_json, digest, read_json


def sounding_key(name):
    name=Path(name).name.lower()
    for suffix in ['.png','.h5','.lfs']:
        name=name.removesuffix(suffix)
    if name.startswith('lfm_ionogram-'):
        match=re.search(r'(ch\d+-\d+-\d+\.\d+)$',name)
        if match:return 'lfm|'+match[1]
    return name


def collect(project):
    project=Path(project).resolve()
    inventory=read_json(project/'reports/inventory.json')
    root=project/'datasets'
    prepared=set()
    existing_ids=set()
    for manifest in root.glob('*/manifest.json'):
        for item in read_json(manifest)['items']:
            existing_ids.add(item['id'])
            if item.get('axes'):prepared.add(sounding_key(item['source']))
    raw=defaultdict(list)
    for record in inventory['records']:raw[sounding_key(record['name'])].append(record['id'])
    candidates={}
    for folder,dirs,files in os.walk(inventory['root']):
        dirs[:]=sorted(d for d in dirs if not d.startswith('.'))
        for name in sorted(files):
            if not name.lower().endswith('.png') or not name.startswith(('lfm_ionogram-','digisonde_ionogram-')):continue
            key=sounding_key(name)
            if key not in prepared:candidates.setdefault(key,Path(folder)/name)
    errors=[];added=0;packs=set()
    for number,(key,source) in enumerate(sorted(candidates.items())):
        ident='png_'+hashlib.sha256(key.encode()).hexdigest()[:20]
        name=f'image_png_{number//300+1:03d}'
        packs.add(name)
        if ident in existing_ids:continue
        try:
            if shutil.disk_usage(root).free<3.1*1024**3:raise OSError('free disk reserve reached')
            with Image.open(source) as image:
                width,height=image.size
                image.verify()
            if width*height>30_000_000:raise ValueError('image too large')
            pack=root/name
            for sub in ['images','annotations','records']:(pack/sub).mkdir(parents=True,exist_ok=True)
            relative=f'images/{ident}.png'
            temporary=pack/(relative+'.tmp')
            shutil.copy2(source,temporary)
            temporary.replace(pack/relative)
            match=re.search(r'-(\d+\.\d+)(?:\.h5)?\.png$',source.name)
            when=datetime.fromtimestamp(float(match[1]),timezone.utc).isoformat() if match else ''
            tx=rx=''
            if source.name.startswith('digisonde_ionogram-'):
                parts=source.name.removeprefix('digisonde_ionogram-').split('-')
                if len(parts)>=3:tx,rx=parts[0],'-'.join(parts[1:-1])
            sha=digest(pack/relative)
            item={'id':ident,'image':relative,'axes':None,'width':width,'height':height,
                'image_sha256':sha,'source_sha256':digest(source),'source':str(source),
                'source_bytes':source.stat().st_size,'image_bytes':(pack/relative).stat().st_size,
                'source_kind':'image','original_name':source.name,'when':when,'tx':tx,'rx':rx,
                'split':split_day(when[:10]) if when else 'unassigned','fallback_for':raw.get(key,[]),
                'warnings':['Архивный PNG: числовой исходник недоступен. Подписи и поля графика сохранены.'],
                'render':{'filters':'none','numeric_axes':False,'original_plot_preserved':True}}
            atomic_json(pack/'records'/f'{ident}.json',item)
            added+=1
            if added%50==0:print(f'PNG {added}/{len(candidates)}',flush=True)
        except Exception as exc:errors.append({'source':str(source),'error':str(exc)})
    write_manifests(root,packs,inventory)
    report={'candidates':len(candidates),'added':added,'errors':errors}
    atomic_json(project/'reports/png_collection.json',report)
    print(json.dumps(report,ensure_ascii=True),flush=True)
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('project',type=Path,nargs='?',default=Path.cwd())
    collect(parser.parse_args().project)
