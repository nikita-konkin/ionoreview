"""Reproducible blind student/model experiment; source datasets are read-only."""
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
import copy
import csv
import json
from pathlib import Path
import random
import shutil

from .data import ReviewStore,atomic_json,read_json,digest,safe_child,utcnow

MSK=timezone(timedelta(hours=3))


def choose_test(library,excluded_days=()):
    groups=defaultdict(list)
    for path in sorted(Path(library).glob('chirp_h5_*/manifest.json')):
        for item in read_json(path)['items']:
            if item['tx'].casefold() not in {'nic1','nic2'} or item['rx'].casefold()!='yoshkar-ola':continue
            dt=datetime.fromisoformat(item['when'])
            if dt.astimezone(timezone.utc).date().isoformat() in excluded_days:continue
            local=dt.astimezone(MSK)
            groups[local.date().isoformat()].append((path.parent,item,local))
    days=[]
    for day,items in groups.items():
        count=Counter((i['tx'].casefold(),t.hour) for _,i,t in items)
        if all(count[(tx,h)]>=1 for tx in ['nic1','nic2'] for h in range(24)):days.append(day)
    if not days:raise ValueError('No full day with NIC1 and NIC2 in every Moscow hour')
    day=max(days);selected=[]
    for hour in range(24):
        for tx,minute in [('nic1',15),('nic2',45)]:
            available=[r for r in groups[day] if r[2].hour==hour and r[1]['tx'].casefold()==tx]
            target=datetime.fromisoformat(day).replace(hour=hour,minute=minute,tzinfo=MSK)
            chosen=min(available,key=lambda r:(abs((r[2]-target).total_seconds()),r[1]['id']))
            selected.append(chosen)
    return day,selected


def copy_pack(destination,sources,split,prefix,annotations=False,blind=False):
    destination=Path(destination)
    if destination.exists():raise ValueError('Pack exists: '+str(destination))
    for folder in ['images','arrays','annotations']:(destination/folder).mkdir(parents=True)
    items=[];mapping=[]
    for index,(root,source) in enumerate(sources,1):
        ident=f'{prefix}{index:02d}'
        item=copy.deepcopy(source);item.update(id=ident,split=split,source=f'measurement://{ident}')
        for field,folder,extension in [('image','images','.png'),('axes','arrays','.npz')]:
            if not source.get(field):continue
            relative=f'{folder}/{ident}{extension}'
            shutil.copy2(safe_child(root,source[field]),destination/relative)
            item[field]=relative
            expected=source['image_sha256' if field=='image' else 'axes_sha256']
            if digest(destination/relative)!=expected:raise ValueError('Copy checksum mismatch')
        item['display_name']=ident
        items.append(item)
        mapping.append({'id':ident,'source_pack':root.name,'source_id':source['id'],'source':source['source'],
            'when_utc':source['when'],'when_msk':datetime.fromisoformat(source['when']).astimezone(MSK).isoformat(),
            'image_sha256':item['image_sha256'],'axes_sha256':item.get('axes_sha256')})
    manifest={'schema':'ionoreview/1','created_at':utcnow(),'items':items,
        'assistance_disabled':blind,'experiment':'student-model-v1','annotation_policy':
        'Независимая ручная разметка. Не использовать автокластеры, импорт, ответы модели или чужую тестовую разметку. '
        'Размечать только видимую полосу сигнала; при неизвестной моде — Signal. Пустой случай требует no_signal.'}
    atomic_json(destination/'manifest.json',manifest)
    if annotations:
        store=ReviewStore(destination)
        for item,(root,source) in zip(items,sources):
            doc=copy.deepcopy(ReviewStore(root).load(source))
            if doc['review']['status']!='accepted':raise ValueError('Training source is not accepted')
            doc['imagePath']='../'+item['image']
            doc['provenance']['source']=item['source']
            store.validate(item,doc)
            atomic_json(store.path(item),doc)
    return items,mapping


def create(project):
    project=Path(project).resolve();out=project/'experiments/student-model-v1'
    if (out/'plan.json').exists():return read_json(out/'plan.json')
    if out.exists():raise ValueError('Incomplete experiment directory exists; inspect before rebuilding')
    pilot=ReviewStore(project/'datasets/pilot');accepted=[];excluded=set()
    for item in pilot.items:
        if pilot.load(item)['review']['status']!='accepted':continue
        accepted.append((pilot.root,item))
        excluded.add(datetime.fromisoformat(item['when']).astimezone(timezone.utc).date().isoformat())
    # The earlier technical test day is now training in a NEW protocol with an unseen test day.
    train=[r for r in accepted if r[1]['split'] in {'train','test'}]
    validation=[r for r in accepted if r[1]['split']=='validation']
    if not train or not validation:raise ValueError('Need accepted training and validation examples')
    day,selected=choose_test(project/'datasets',excluded)
    train_items,train_map=copy_pack(out/'training_library/train',train,'train','R',True)
    val_items,val_map=copy_pack(out/'training_library/validation',validation,'validation','V',True)
    test_sources=[(p,i) for p,i,_ in selected]
    test_items,test_map=copy_pack(out/'test-student',test_sources,'test','T',blind=True)
    model_items,_=copy_pack(out/'test-model-input',test_sources,'test','T')
    assert all(a['image_sha256']==b['image_sha256'] and a['axes_sha256']==b['axes_sha256'] for a,b in zip(test_items,model_items))
    assert Counter(datetime.fromisoformat(i['when']).astimezone(MSK).hour for i in test_items)==Counter({h:2 for h in range(24)})
    # Presentation order is fixed and shared by student/model; no model outputs are given to the student.
    order=list(range(48));random.Random(20261104).shuffle(order)
    for name in ['test-student','test-model-input']:
        p=out/name/'manifest.json';m=read_json(p);m['items']=[m['items'][i] for i in order];atomic_json(p,m)
    (out/'coordinator').mkdir()
    with (out/'coordinator/source_mapping.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(test_map[0]));writer.writeheader();writer.writerows(test_map)
    with (out/'student_timing.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['id','start_time','end_time','active_minutes','uncertain_modes','note'])
        for item in test_items:writer.writerow([item['id'],'','','','',''])
    cfg=read_json(project/'training/config.json')
    cfg.update(library_root=str(out/'training_library'),dataset_root=str(out/'training_data'),tile_size=192,overlap=48,
        run_root=str(Path.home()/'.cache/ionoreview-training/runs/student-model-v1'))
    atomic_json(out/'training_config.json',cfg)
    plan={'schema':'ionoreview-experiment/1','created_at':utcnow(),'name':'student-model-v1',
        'train_images':len(train_items),'validation_images':len(val_items),'test_images':48,
        'test_day_msk':day,'timezone':'UTC+03:00 Europe/Moscow','transmitter':'NIC1 and NIC2','receiver':'Yoshkar-Ola',
        'selection':'Latest complete two-transmitter day disjoint from accepted UTC days; NIC1 closest to :15 and NIC2 to :45 in each Moscow hour. No per-image signal-quality filtering.',
        'selection_note':'An earlier one-transmitter diagnostic day had almost no strong traces. The locked primary cohort covers both trained transmitters on an active day; it is not an outage benchmark or random archive sample.',
        'presentation_seed':20261104,'counts_by_hour':{str(h):2 for h in range(24)},
        'train_sources':train_map,'validation_sources':val_map,'test_sources':test_map,
        'original_packs_modified':False,'old_technical_test_promoted_to_train':True,
        'blind_student_pack':'test-student','model_pack':'test-model-input',
        'training_library':'training_library','training_config':'training_config.json',
        'note':'The prior pilot test is not used as a blind benchmark; the new unseen day is the locked test. Student/model agreement is not expert-reference accuracy.'}
    atomic_json(out/'plan.json',plan)
    return plan


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('project',type=Path,nargs='?',default=Path.cwd())
    result=create(p.parse_args().project)
    print(json.dumps({k:result[k] for k in ['train_images','validation_images','test_images','test_day_msk','timezone']},indent=2))
