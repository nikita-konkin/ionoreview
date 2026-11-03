"""Full-frame semantic IoU/Dice, unioning overlapping tiles once per source."""
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw

from ..data import LABELS,atomic_json,read_json,utcnow
from .common import rows
from .predict import source_shapes


def masks(width,height,shapes):
    result={}
    for label in LABELS:
        image=Image.new('1',(width,height));draw=ImageDraw.Draw(image)
        for shape in shapes:
            if shape['label']==label:draw.polygon([tuple(p) for p in shape['points']],fill=1)
        result[label]=np.asarray(image)
    return result


def evaluate(folder,split,predictions):
    folder=Path(folder);predictions=Path(predictions)
    truth=read_json(folder/'ground_truth.json');examples=rows(folder,split)
    grouped=defaultdict(list);invalid=[]
    for row in examples:
        file=predictions/(row['id']+'.json')
        if not file.is_file():raise ValueError('Missing predictions; partial evaluation is not allowed: '+row['id'])
        pred=read_json(file)
        if pred.get('id')!=row['id']:raise ValueError('Prediction ID mismatch')
        source=row['pack']+'__'+row['source_id']
        grouped[source]  # include images even when every output is invalid
        if not pred['ok']:invalid.append(row['id']);continue
        from .predict import parse_prediction
        import json
        decoded=parse_prediction(json.dumps(pred['prediction']))
        grouped[source].extend(source_shapes(row,decoded))
    totals={label:[0,0,0,0] for label in LABELS}
    for source,shapes in grouped.items():
        gt=truth[source]
        if gt['split']!=split:raise ValueError('Split mismatch')
        true=masks(gt['width'],gt['height'],gt['shapes'])
        predicted=masks(gt['width'],gt['height'],shapes)
        for label in LABELS:
            a,b=true[label],predicted[label]
            for index,n in enumerate([np.count_nonzero(a&b),np.count_nonzero(a|b),np.count_nonzero(a),np.count_nonzero(b)]):
                totals[label][index]+=int(n)
    classes={}
    for label,(intersection,union,gt,pred) in totals.items():
        classes[label]={'iou':intersection/union if union else None,
            'dice':2*intersection/(gt+pred) if gt+pred else None,'gt_pixels':gt,'predicted_pixels':pred}
    scored=[v['iou'] for v in classes.values() if v['iou'] is not None]
    report={'evaluated_at':utcnow(),'split':split,'source_images':len(grouped),'tiles':len(examples),
        'invalid_outputs':invalid,'valid_json_rate':1-len(invalid)/len(examples),
        'macro_iou_present_classes':sum(scored)/len(scored) if scored else None,'classes':classes,
        'note':'Semantic full-image masks; overlapping tiles counted once. Empty classes excluded from macro IoU. Small-pilot estimate, not instance AP.'}
    atomic_json(predictions/'evaluation.json',report)
    return report
