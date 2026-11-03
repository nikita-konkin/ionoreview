import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

pytest.importorskip('shapely')

from ionoreview.data import ReviewStore,atomic_json,digest,read_json
from ionoreview.finetune.dataset import prepare,accepted_sources,starts,polygons_in_crop
from ionoreview.finetune.predict import parse_prediction,source_shapes
from ionoreview.finetune.evaluate import evaluate


def fixture_library(tmp_path,same_day=False):
    library=tmp_path/'datasets';pack=library/'fixture'
    (pack/'images').mkdir(parents=True)
    items=[]
    for index,(split,colour,day) in enumerate([
        ('train','navy','17'),('validation','green','17' if same_day else '18'),('test','maroon','24')]):
        image=pack/f'images/c{index}.png';Image.new('RGB',(32,32),colour).save(image)
        items.append({'id':f'c{index}','source_kind':'image','source':str(image),'image':f'images/c{index}.png',
            'axes':None,'width':32,'height':32,'image_sha256':digest(image),'split':split,
            'when':f'2026-10-{day}T01:00:00+00:00','tx':'A','rx':'B'})
    atomic_json(pack/'manifest.json',{'schema':'ionoreview/1','items':items})
    store=ReviewStore(pack)
    for item in items:
        doc=store.blank(item);doc['review'].update(status='accepted',reviewer='test')
        doc['shapes']=[{'label':'1F','points':[[0,0],[31,0],[31,31],[0,31]],'shape_type':'polygon','flags':{}}]
        store.save(item,doc)
    return library,pack


def cfg(tmp_path):
    return {'dataset_root':str(tmp_path/'prepared'),'tile_size':32,'overlap':8,
        'overview_edge':64,'simplify_pixels':.1,'min_polygon_area':.5}


def test_accepted_only_snapshot_no_day_or_image_leak_and_no_source_writes(tmp_path):
    library,pack=fixture_library(tmp_path)
    before={p.name:p.read_bytes() for p in (pack/'annotations').glob('*.json')}
    result=prepare(cfg(tmp_path),library)
    assert result['source_images']=={'train':1,'validation':1,'test':1}
    folder=Path(result['path'])
    assert set(read_json(folder/'ground_truth.json'))=={'fixture__c0','fixture__c1','fixture__c2'}
    for split in ['train','validation','test']:
        row=json.loads((folder/f'{split}.jsonl').read_text())
        assert row['split']==split
        assert all(0<=v<=1000 for s in row['target']['shapes'] for p in s['points'] for v in p)
    assert before=={p.name:p.read_bytes() for p in (pack/'annotations').glob('*.json')}
    assert prepare(cfg(tmp_path),library)['fingerprint']==result['fingerprint']
    store=ReviewStore(pack);doc=store.load(store.items[0]);doc['review']['status']='pending';store.save(store.items[0],doc)
    assert len(accepted_sources(library))==2


def test_split_rejects_same_utc_day_in_train_and_validation(tmp_path):
    library,_=fixture_library(tmp_path,same_day=True)
    with pytest.raises(ValueError,match='day leaks'):accepted_sources(library)


def test_clipping_disconnected_concave_polygon_preserves_two_pieces(tmp_path):
    shape={'label':'1F','points':[[0,0],[10,0],[10,10],[7,10],[7,3],[3,3],[3,10],[0,10]]}
    shapes,dropped=polygons_in_crop([shape],(0,5,11,6),cfg(tmp_path))
    assert len(shapes)==2
    assert len(starts(1093,256,64))==6
    assert starts(1093,256,64)[-1]==837


@pytest.mark.parametrize('text',[
    '{"shapes":[{"label":"unknown","points":[[0,0],[1,0],[1,1]]}]}',
    '{"shapes":[{"label":"1F","points":[[0,0],[1001,0],[1,1]]}]}',
    '{"shapes":[{"label":"1F","points":[[0,0],[NaN,0],[1,1]]}]}',
    '```json\n{"shapes":[]}\n```'])
def test_predictions_reject_invalid_geometry_or_free_text(text):
    with pytest.raises(ValueError):parse_prediction(text)


def test_evaluation_unions_overlap_and_penalizes_invalid_json(tmp_path):
    library,_=fixture_library(tmp_path);prepared=prepare(cfg(tmp_path),library);folder=Path(prepared['path'])
    predictions=tmp_path/'predictions';predictions.mkdir()
    row=json.loads((folder/'validation.jsonl').read_text())
    atomic_json(predictions/(row['id']+'.json'),{'ok':True,'id':row['id'],'prediction':row['target']})
    report=evaluate(folder,'validation',predictions)
    assert report['classes']['1F']['iou']==1.0
    atomic_json(predictions/(row['id']+'.json'),{'ok':False,'id':row['id'],'error':'bad JSON'})
    report=evaluate(folder,'validation',predictions)
    assert report['classes']['1F']['iou']==0 and report['valid_json_rate']==0


def test_full_frame_mapping_uses_pixel_centres():
    row={'roi':[30,40,256,256]}
    parsed=parse_prediction('{"shapes":[{"label":"1F","points":[[0,0],[1000,0],[1000,1000]]}]}')
    shapes=source_shapes(row,parsed)
    assert shapes[0]['points']==[[30,40],[285,40],[285,295]]


def test_collator_masks_prompt_and_rejects_silent_truncation(tmp_path):
    torch=pytest.importorskip('torch')
    from types import SimpleNamespace
    from ionoreview.finetune.runtime import Collator
    Image.new('RGB',(8,8)).save(tmp_path/'image.png')
    class Processor:
        tokenizer=SimpleNamespace(eos_token='!')
        def apply_chat_template(self,*args,**kwargs):return 'PROMPT'
        def __call__(self,text,**kwargs):
            ids=[[ord(c) for c in s] for s in text];length=max(map(len,ids))
            return {'input_ids':torch.tensor([s+[0]*(length-len(s)) for s in ids]),
                'attention_mask':torch.tensor([[1]*len(s)+[0]*(length-len(s)) for s in ids])}
    row={'id':'a','prompt':'x','images':['image.png','image.png'],'target':{'shapes':[]}}
    batch=Collator(Processor(),tmp_path,100)([row])
    assert (batch['labels'][0,:6]==-100).all()
    assert (batch['labels'][0,6:]!=-100).all()
    with pytest.raises(ValueError,match='no truncation'):Collator(Processor(),tmp_path,6)([row])
