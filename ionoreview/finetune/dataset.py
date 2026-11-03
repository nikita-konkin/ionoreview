"""Immutable, accepted-only multimodal data; all crops inherit the source split."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw
from shapely import make_valid,is_valid_reason
from shapely.geometry import Polygon,box

from ..data import ReviewStore,LABELS,atomic_json,digest,read_json,safe_child,utcnow
from .common import PROJECT

DATA_VERSION=5


def polygon_parts(geometry):
    if geometry.geom_type=='Polygon':
        yield geometry
    elif hasattr(geometry,'geoms'):
        for child in geometry.geoms:yield from polygon_parts(child)


def repaired_polygon(points):
    poly=Polygon(points)
    return poly if poly.is_valid else make_valid(poly)


def starts(length,size,overlap):
    if not 0<=overlap<size:raise ValueError('overlap must be smaller than tile size')
    if length<=size:return [0]
    result=list(range(0,length-size+1,size-overlap))
    if result[-1]!=length-size:result.append(length-size)
    return result


def polygons_in_crop(shapes,roi,cfg):
    x,y,w,h=roi
    result=[];dropped=0
    for shape in shapes:
        poly=repaired_polygon(shape['points'])
        cut=poly.intersection(box(x,y,x+w-1,y+h-1))
        pieces=list(polygon_parts(cut))
        for piece in pieces:
            if piece.interiors:raise ValueError('Polygon has holes; needs explicit hole decomposition')
            if piece.geom_type!='Polygon' or piece.area<cfg['min_polygon_area']:
                if not piece.is_empty:dropped+=1
                continue
            piece=piece.simplify(cfg['simplify_pixels'],preserve_topology=True)
            points=[[round((px-x)*1000/max(1,w-1)),round((py-y)*1000/max(1,h-1))]
                    for px,py in list(piece.exterior.coords)[:-1]]
            # Adjacent equal vertices can appear after subpixel quantization.
            unique=[]
            for point in points:
                if not unique or unique[-1]!=point:unique.append(point)
            if len(unique)>1 and unique[-1]==unique[0]:unique.pop()
            if len(set(map(tuple,unique)))<3 or Polygon(unique).area==0:
                dropped+=1;continue
            result.append({'label':shape['label'],'points':unique})
    result.sort(key=lambda s:(s['label'],min(p[1] for p in s['points']),min(p[0] for p in s['points'])))
    return result,dropped


def instruction(row):
    meta={'crop_pixels':row['roi'],'full_image_pixels':row['source_size'],
          'crop_frequency_MHz':row.get('frequency_mhz'),'crop_range_km_top_bottom':row.get('range_km')}
    return ('You annotate ionograms. Image 1 is the full overview; image 2 is the native-resolution crop. '
        'Return polygons ONLY for image 2. Coordinates are integers 0..1000: x increases right, y down; '
        '0 and 1000 correspond to the first and last pixel centers of the crop. '
        'Allowed labels: '+', '.join(LABELS)+'. Use Signal when the mode is uncertain. '
        'Trace only visible echo bands; do not fill the space between branches. '
        'Return JSON only: {"shapes":[{"label":"1F","points":[[x,y],[x,y],[x,y]]}]}. '
        'If there is no annotated signal/interference, return {"shapes":[]}. '
        'No markdown, no explanation. Context: '+json.dumps(meta,separators=(',',':')))


def accepted_sources(library):
    result=[];image_splits={};day_splits={}
    for manifest in sorted(Path(library).glob('*/manifest.json')):
        annotations=list((manifest.parent/'annotations').glob('*.json'))
        if not annotations:continue
        store=ReviewStore(manifest.parent)
        by_id={i['id']:i for i in store.items}
        for path in sorted(annotations):
            item=by_id.get(path.stem)
            if item is None:raise ValueError(f'Orphan annotation: {path}')
            raw=read_json(path)
            if raw.get('review',{}).get('status')!='accepted':continue
            doc=store.load(item)
            split=item.get('split')
            if split not in {'train','validation','test'}:raise ValueError(f'Assign a day-based split first: {path}')
            image=safe_child(store.root,item['image'])
            if digest(image)!=item['image_sha256']:raise ValueError(f'Image changed: {image}')
            if item['image_sha256'] in image_splits and image_splits[item['image_sha256']]!=split:
                raise ValueError('The same image occurs across different splits')
            image_splits[item['image_sha256']]=split
            if item.get('when'):
                date=datetime.fromisoformat(item['when'].replace('Z','+00:00'))
                if date.tzinfo is None:raise ValueError('Source time must have a timezone')
                day=date.astimezone(timezone.utc).date().isoformat()
                if day in day_splits and day_splits[day]!=split:raise ValueError('UTC day leaks across splits')
                day_splits[day]=split
            result.append({'pack':store.root.name,'root':str(store.root),'item':item,'document':doc,'image':str(image),
                'annotation':str(path),'annotation_sha256':digest(path)})
    if not result:raise ValueError('No accepted annotations')
    return result


def prepare(cfg,library=None):
    sources=accepted_sources(library or PROJECT/'datasets')
    signature={'version':DATA_VERSION,'sources':[{k:s[k] for k in ['pack','annotation_sha256']}|
        {'id':s['item']['id'],'image_sha256':s['item']['image_sha256'],'split':s['item']['split']} for s in sources],
        'options':{k:cfg[k] for k in ['tile_size','overlap','overview_edge','simplify_pixels','min_polygon_area']}}
    fingerprint=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    root=Path(cfg['dataset_root']);destination=root/fingerprint[:16]
    if (destination/'report.json').exists():
        atomic_json(root/'latest.json',{'path':str(destination.resolve()),'fingerprint':fingerprint})
        return read_json(destination/'report.json')
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'images').mkdir(exist_ok=True)
    out=defaultdict(list);counts=Counter();polygons=Counter();dropped=0;repairs=[]
    for source in sources:
        item=source['item'];ident=source['pack']+'__'+item['id'];split=item['split']
        counts[split]+=1
        with Image.open(source['image']) as opened:image=opened.convert('RGB')
        if image.size!=(item['width'],item['height']):raise ValueError('Image dimensions changed')
        for index,shape in enumerate(source['document']['shapes']):
            poly=Polygon(shape['points'])
            if poly.is_valid:continue
            a=Image.new('1',image.size);ImageDraw.Draw(a).polygon([tuple(p) for p in shape['points']],fill=1)
            b=Image.new('1',image.size);draw=ImageDraw.Draw(b)
            for piece in polygon_parts(make_valid(poly)):
                draw.polygon(list(piece.exterior.coords),fill=1)
                for ring in piece.interiors:draw.polygon(list(ring.coords),fill=0)
            aa,bb=np.asarray(a),np.asarray(b);union=np.count_nonzero(aa|bb)
            score=np.count_nonzero(aa&bb)/union if union else 1.
            if score<.98:raise ValueError(f'Geometry repair changes visible pixels: {ident} polygon {index}, IoU={score:.4f}')
            repairs.append({'source':ident,'shape':index,'reason':is_valid_reason(poly),'pixel_iou':score})
        overview=image.copy();overview.thumbnail((cfg['overview_edge'],cfg['overview_edge']),Image.Resampling.LANCZOS)
        overview_path=f'images/{ident}_overview.png';overview.save(destination/overview_path)
        freq=ranges=None
        if item.get('axes'):
            with np.load(safe_child(Path(source['root']),item['axes']),allow_pickle=False) as arrays:
                freq,ranges=arrays['freq_mhz'],arrays['range_km']
        tiles=[]
        for yy in starts(image.height,cfg['tile_size'],cfg['overlap']):
            for xx in starts(image.width,cfg['tile_size'],cfg['overlap']):
                initial=(xx,yy,min(cfg['tile_size'],image.width-xx),min(cfg['tile_size'],image.height-yy))
                shapes,removed=polygons_in_crop(source['document']['shapes'],initial,cfg)
                tiles.append((initial,shapes,removed))
        seen=set()
        for roi,shapes,removed in tiles:
                x,y,w,h=roi
                if tuple(roi) in seen:continue
                seen.add(tuple(roi));dropped+=removed
                tile_id=f'{ident}_x{x}_y{y}_w{w}_h{h}'
                crop_path=f'images/{tile_id}.png';image.crop((x,y,x+w,y+h)).save(destination/crop_path)
                row={'id':tile_id,'source_id':item['id'],'pack':source['pack'],
                    'split':split,'images':[overview_path,crop_path],'roi':[x,y,w,h],
                    'source_size':[image.width,image.height],'source_image_sha256':item['image_sha256'],
                    'annotation_sha256':source['annotation_sha256'],
                    'frequency_mhz':[float(freq[x]),float(freq[x+w-1])] if freq is not None else None,
                    'range_km':[float(ranges[y]),float(ranges[y+h-1])] if ranges is not None else None,
                    'target':{'shapes':shapes}}
                row['prompt']=instruction(row)
                out[split].append(row)
        polygons.update(s['label'] for s in source['document']['shapes'])
    if not out['train'] or not out['validation']:raise ValueError('Need accepted train and validation images')
    for split in ['train','validation','test']:
        with (destination/f'{split}.jsonl').open('w',encoding='utf8',newline='\n') as stream:
            for row in out[split]:stream.write(json.dumps(row,ensure_ascii=True,separators=(',',':'))+'\n')
    coverage={split:dict(Counter(s['label'] for source in sources if source['item']['split']==split
        for s in source['document']['shapes'])) for split in out}
    report={'schema':'ionoreview-vlm-data/1','created_at':utcnow(),'path':str(destination.resolve()),
        'fingerprint':fingerprint,'source_images':dict(counts),'tiles':{s:len(v) for s,v in out.items()},
        'class_polygons':dict(polygons),'class_coverage':coverage,'clipped_subpixel_pieces_dropped':dropped,
        'geometry_repairs_in_training_copy':repairs,
        'missing_train_classes':sorted(set(polygons)-set(coverage['train'])),
        'crop_policy':'fixed grid, independent of annotations, identical at inference',
        'note':'Crops are dependent samples. Test images are never included in training. Experimental small pilot.'}
    atomic_json(destination/'sources.json',signature)
    atomic_json(destination/'ground_truth.json',{s['pack']+'__'+s['item']['id']:{
        'width':s['item']['width'],'height':s['item']['height'],'split':s['item']['split'],
        'shapes':s['document']['shapes']} for s in sources})
    atomic_json(destination/'report.json',report)
    atomic_json(root/'latest.json',{'path':str(destination.resolve()),'fingerprint':fingerprint})
    return report
