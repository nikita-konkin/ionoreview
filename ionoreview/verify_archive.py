"""Read-only verification and a reconciled preparation report."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path
import argparse
import json
import shutil

import numpy as np
from PIL import Image

from .data import atomic_json, digest, read_json, safe_child, utcnow
from .library import entries


def check_item(pair):
    pack,item=pair
    try:
        image_path=safe_child(pack,item['image'])
        if digest(image_path)!=item['image_sha256']:
            raise ValueError('checksum mismatch')
        with Image.open(image_path) as image:
            if image.size!=(item['width'],item['height']):raise ValueError('PNG dimensions')
            image.verify()
        if not item.get('axes'):return {'ok':True,'id':item['id']}
        array_path=safe_child(pack,item['axes'])
        if digest(array_path)!=item['axes_sha256']:raise ValueError('array checksum mismatch')
        with np.load(array_path,allow_pickle=False) as data:
            db,freq,ranges=data['db'],data['freq_mhz'],data['range_km']
            if db.shape!=(item['height'],item['width']) or db.shape!=(len(ranges),len(freq)):
                raise ValueError('array dimensions')
            if db.dtype!=np.float32:raise ValueError('matrix is not float32')
            if not (np.isfinite(freq).all() and np.isfinite(ranges).all()
                    and (np.diff(freq)>0).all() and (np.diff(ranges)<0).all()):
                raise ValueError('physical axes')
        return {'ok':True,'id':item['id']}
    except Exception as exc:
        return {'ok':False,'id':item['id'],'pack':str(pack),'error':str(exc)}


def verify(project, workers=4):
    project=Path(project).resolve()
    rows=entries(project/'datasets')
    pairs=[]
    for row in rows:
        pack=row['full_path']
        pairs.extend((pack,i) for i in read_json(pack/'manifest.json')['items'])
    ids=[i['id'] for _,i in pairs]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate ionogram IDs across packs')
    failures=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for number,result in enumerate(pool.map(check_item,pairs),1):
            if not result['ok']:failures.append(result)
            if number%500==0:print(f'VERIFY {number}/{len(pairs)}, errors {len(failures)}',flush=True)
    inventory=read_json(project/'reports'/'inventory.json')
    prepared={i['id'] for _,i in pairs}
    unresolved={r['id']:dict(r) for r in inventory['records'] if r['id'] not in prepared}
    fallbacks={raw_id:i['id'] for _,i in pairs for raw_id in i.get('fallback_for',[])}
    for ident,row in unresolved.items():
        if ident in fallbacks:row['png_fallback_id']=fallbacks[ident]
    error_file=project/'reports'/'preparation_errors.jsonl'
    if error_file.exists():
        for line in error_file.read_text(encoding='utf8').splitlines():
            error=json.loads(line)
            if error['id'] in unresolved:unresolved[error['id']]['errors']=error['errors']
    status=Counter()
    for pack,item in pairs:
        annotation=pack/'annotations'/f"{item['id']}.json"
        status[read_json(annotation)['review']['status'] if annotation.exists() else 'pending']+=1
    paths={p for pack,_ in pairs for p in [pack]}
    total_bytes=sum(p.stat().st_size for pack in paths for p in pack.rglob('*') if p.is_file())
    report={'schema':'ionoreview-preparation-report/1','finished_at':utcnow(),
        'project':str(project),'source_root':inventory['root'],'packs':len(rows),
        'ready':len(pairs),'new_archive_ready':sum(r['count'] for r in rows if r['path']!='pilot'),
        'numeric_ready':sum(bool(i.get('axes')) for _,i in pairs),
        'image_only_ready':sum(not i.get('axes') for _,i in pairs),
        'pilot':sum(len(read_json(r['full_path']/'manifest.json')['items']) for r in rows if r['path']=='pilot'),
        'by_kind':dict(Counter(i.get('source_kind','pilot') for _,i in pairs)),
        'review_status':dict(status),'total_bytes':total_bytes,
        'free_bytes':shutil.disk_usage(project).free,'unresolved_count':len(unresolved),
        'unresolved_with_png_fallback':sum('png_fallback_id' in r for r in unresolved.values()),
        'unresolved':list(unresolved.values()),'integrity_errors':failures,
        'verified':len(pairs)-len(failures),
        'note':'New archive records are pending expert review. Raw recordings remain at source_root.'}
    atomic_json(project/'reports'/'preparation_summary.json',report)
    lines=['# Подготовка ионограмм', '',f"Проект: `{project}`",f"Исходный архив: `{inventory['root']}`",'',
        f"Готово: **{len(pairs)}** ионограмм в **{len(rows)}** наборах.",
        f"С числовыми осями: **{report['numeric_ready']}**; только PNG: **{report['image_only_ready']}**.",
        f"Проверено без ошибок: **{report['verified']}**. Ошибок целостности: **{len(failures)}**.",
        f"Статусы разметки: {dict(status)}.",
        f"Объём наборов: {total_bytes/1024**3:.2f} ГиБ. Свободно: {report['free_bytes']/1024**3:.2f} ГиБ.",
        '',f"Не подготовлено числовых исходников: **{len(unresolved)}**.",
        f"Для {report['unresolved_with_png_fallback']} из них сохранён отдельный PNG без числовых осей.",
        'Полный список исходных путей и причин — в `preparation_summary.json`.', '',
        'Новые ионограммы ожидают экспертной разметки. Приёмка автоматически не выполнялась.',
        'Старый пилот и история сохранены. Исходные LFS/HDF5 не изменялись.', '',
        'Изображения и массивы находятся в `datasets/<набор>/images` и `arrays`.',
        'Результат разметки сохраняется в `datasets/<набор>/annotations`.',
        'Запуск каталога: `Start-Review.cmd`. Старый пилот: `Start-Pilot.cmd`.']
    (project/'reports'/'PREPARATION.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'unresolved','integrity_errors'}},ensure_ascii=True,indent=2),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Проверка готовой библиотеки ионограмм')
    parser.add_argument('project',type=Path,nargs='?',default=Path.cwd())
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    result=verify(args.project,args.workers)
    raise SystemExit(1 if result['integrity_errors'] else 0)
