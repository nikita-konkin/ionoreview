"""Strict JSON predictions and LabelMe proposals; never writes expert annotations."""
import json
import math
from pathlib import Path

from PIL import Image

from ..data import LABELS,atomic_json,validate_shapes,utcnow,ReviewStore,safe_child,digest
from .common import gpu_lease,require_gpu,rows
from .dataset import starts,instruction
from .runtime import processor_for,load_model,prompt_text


def parse_prediction(text):
    value=json.loads(text.strip())
    if not isinstance(value,dict) or set(value)!={'shapes'} or not isinstance(value['shapes'],list):
        raise ValueError('Expected exactly {"shapes": [...]}')
    if len(value['shapes'])>300:raise ValueError('Too many polygons')
    converted=[]
    for shape in value['shapes']:
        if not isinstance(shape,dict) or shape.get('label') not in LABELS:raise ValueError('Unknown label')
        points=shape.get('points')
        if not isinstance(points,list) or not 3<=len(points)<=2048:raise ValueError('Invalid polygon point count')
        for point in points:
            if not isinstance(point,list) or len(point)!=2:raise ValueError('Expected [x,y]')
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1000 for v in point):
                raise ValueError('Coordinates outside 0..1000')
        converted.append({'label':shape['label'],'points':points,'shape_type':'polygon','group_id':None,'flags':{}})
    validate_shapes(converted,1001,1001)
    return {'shapes':[{'label':s['label'],'points':s['points']} for s in converted]}


def source_shapes(row,prediction):
    x,y,w,h=row['roi']
    def native(value,length):
        v=value*(length-1)/1000
        return float(round(v)) if abs(v-round(v))<=(length-1)/2000+1e-9 else v
    return [{'label':s['label'],'points':[[x+native(px,w),y+native(py,h)] for px,py in s['points']],
             'shape_type':'polygon','group_id':None,'flags':{'vlm_proposal':True}}
            for s in prediction['shapes']]


def generate(cfg,folder,examples,out,adapter=None):
    import torch
    out=Path(out).resolve()
    if out.exists():raise ValueError('Prediction directory already exists; choose a new one')
    with gpu_lease(cfg,'ionoreview-predict'):
        require_gpu(cfg)
        processor=processor_for(cfg);model=load_model(cfg,adapter=adapter);model.eval()
        out.mkdir(parents=True)
        atomic_json(out/'request.json',{'created_at':utcnow(),'model':cfg['model_id'],
            'model_revision':cfg['model_revision'],'adapter':str(adapter) if adapter else None,
            'dataset':str(Path(folder).resolve()),'examples':[r['id'] for r in examples]})
        invalid=[]
        for index,row in enumerate(examples,1):
            images=[]
            for relative in row['images']:
                with Image.open(safe_child(Path(folder),relative)) as image:images.append(image.convert('RGB'))
            text=prompt_text(processor,row)
            batch=processor(text=[text],images=images,return_tensors='pt',add_special_tokens=False)
            tokens=batch['input_ids'].shape[-1]
            if tokens>=cfg['max_seq_length']-32:raise ValueError('Input prompt exceeds generation budget')
            batch={k:(v.to('cuda',dtype=torch.bfloat16) if v.is_floating_point() else v.to('cuda')) for k,v in batch.items()}
            limit=cfg['max_seq_length']-tokens
            with torch.inference_mode():output=model.generate(**batch,max_new_tokens=limit,do_sample=False,use_cache=True)
            answer=processor.tokenizer.decode(output[0,tokens:],skip_special_tokens=True)
            (out/(row['id']+'.txt')).write_text(answer,encoding='utf8')
            try:
                decoded=parse_prediction(answer)
                record={'ok':True,'id':row['id'],'prediction':decoded}
            except (ValueError,TypeError) as exc:
                record={'ok':False,'id':row['id'],'error':str(exc)};invalid.append(row['id'])
            atomic_json(out/(row['id']+'.json'),record)
            atomic_json(out/'progress.json',{'completed':index,'total':len(examples),'invalid':len(invalid)})
        report={'completed':len(examples),'invalid':invalid,'path':str(out),'finished_at':utcnow()}
        atomic_json(out/'finished.json',report)
        return report


def predict_split(cfg,folder,split,out,adapter=None):
    return generate(cfg,folder,rows(folder,split),out,adapter)


def prepare_case(cfg,pack,case_id,folder):
    import numpy as np
    store=ReviewStore(pack)
    item=next(i for i in store.items if i['id']==case_id)
    source=safe_child(store.root,item['image'])
    if digest(source)!=item['image_sha256']:raise ValueError('Image changed')
    folder=Path(folder);(folder/'images').mkdir(parents=True)
    with Image.open(source) as opened:image=opened.convert('RGB')
    overview=image.copy();overview.thumbnail((cfg['overview_edge'],cfg['overview_edge']),Image.Resampling.LANCZOS)
    overview.save(folder/'images/overview.png')
    f=r=None
    if item.get('axes'):
        with np.load(safe_child(store.root,item['axes'])) as z:f,r=z['freq_mhz'],z['range_km']
    examples=[]
    for y in starts(image.height,cfg['tile_size'],cfg['overlap']):
        for x in starts(image.width,cfg['tile_size'],cfg['overlap']):
            w=min(cfg['tile_size'],image.width-x);h=min(cfg['tile_size'],image.height-y)
            ident=f'{store.root.name}__{case_id}_x{x}_y{y}_w{w}_h{h}'
            image.crop((x,y,x+w,y+h)).save(folder/f'images/{ident}.png')
            row={'id':ident,'pack':store.root.name,'source_id':case_id,'roi':[x,y,w,h],
                'source_size':[image.width,image.height],'images':['images/overview.png',f'images/{ident}.png'],
                'frequency_mhz':[float(f[x]),float(f[x+w-1])] if f is not None else None,
                'range_km':[float(r[y]),float(r[y+h-1])] if r is not None else None}
            row['prompt']=instruction(row);examples.append(row)
    atomic_json(folder/'examples.json',examples)
    return item,examples


def predict_case(cfg,pack,case_id,out,adapter=None):
    out=Path(out).resolve()
    if out.exists():raise ValueError('Output directory already exists')
    item,examples=prepare_case(cfg,pack,case_id,out)
    result=generate(cfg,out,examples,out/'tiles',adapter)
    shapes=[]
    from ..data import read_json
    for row in examples:
        pred=read_json(out/'tiles'/(row['id']+'.json'))
        if pred['ok']:shapes.extend(source_shapes(row,pred['prediction']))
    validate_shapes(shapes,item['width'],item['height'])
    proposal={'version':'5.5.0','flags':{'vlm_proposal':True,'incomplete':bool(result['invalid'])},
        'imagePath':str(safe_child(Path(pack),item['image'])),'imageData':None,
        'imageWidth':item['width'],'imageHeight':item['height'],'shapes':shapes,
        'proposal':{'author':cfg['model_id']+' '+(str(adapter) if adapter else 'base'),
            'review_required':True,'invalid_tiles':result['invalid'],
            'note':'Overlapping tiles may produce overlapping contours; expert must correct and group them.'}}
    atomic_json(out/'proposal.labelme.json',proposal)
    return {'path':str(out/'proposal.labelme.json'),'polygons':len(shapes),'invalid_tiles':len(result['invalid']),
            'review_required':True,'annotations_modified':False}
