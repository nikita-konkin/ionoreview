from pathlib import Path

import numpy as np
import pytest
from matplotlib import colormaps

from ionoreview.archive import discover, kind_of, palette_image, split_day, write_manifests
from ionoreview.data import atomic_json, read_json
from ionoreview.library import entries


def test_inventory_excludes_parameter_files_and_pilot_but_keeps_alternatives(tmp_path):
    source=tmp_path/'raw'
    for folder in ['first','mirror']:
        (source/folder).mkdir(parents=True)
        for name in ['lfm_ionogram-A.h5','lfm_ionogram-pilot.h5']:
            (source/folder/name).write_bytes(b'source')
    (source/'first'/'digisonde_ionogram-B.h5').write_bytes(b'digisonde')
    (source/'first'/'parameters-B.h5').write_bytes(b'parameters')
    (source/'first'/'raw.lfs').write_bytes(b'raw')
    pilot=tmp_path/'pilot'
    atomic_json(pilot/'manifest.json',{'items':[{'source':str(source/'first'/'lfm_ionogram-pilot.h5')}]})
    result=discover(source,pilot)
    assert len(result['records'])==3
    assert result['duplicate_paths']==1
    assert result['ignored']=={'already_in_pilot':2,'non_ionogram_h5':1}
    assert sorted(len(r['sources']) for r in result['records'])==[1,1,2]
    assert kind_of('other.h5') is None


def test_palette_png_preserves_original_turbo_pixels(tmp_path):
    db=np.linspace(-20,100,3000,dtype=np.float32).reshape(30,100)
    expected=colormaps['turbo'](np.clip((db-15)/45,0,1),bytes=True)[:,:,:3]
    file=tmp_path/'image.png'
    palette_image(db).save(file)
    from PIL import Image
    with Image.open(file) as image:
        assert image.mode=='P'
        np.testing.assert_array_equal(np.asarray(image.convert('RGB')),expected)


def test_split_policy_matches_pilot_and_is_stable_per_day():
    assert [split_day(d) for d in ['2026-10-17','2026-10-18','2026-10-24']]==['train','validation','test']
    assert split_day('2026-08-01')==split_day('2026-08-01')
    assert {split_day(f'2026-08-{day:02d}') for day in range(1,32)}=={'train','validation','test'}


def test_manifest_refresh_keeps_previous_phase_and_all_annotations(tmp_path):
    for name,ident in [('chirp_h5_001','a'),('lfs_001','b')]:
        atomic_json(tmp_path/name/'records'/f'{ident}.json',{
            'id':ident,'source_kind':'lfs' if ident=='b' else 'chirp_h5',
            'when':'2026-08-01T12:00:00+00:00','tx':'A','rx':'B'})
    annotation=tmp_path/'lfs_001'/'annotations'/'b.json'
    atomic_json(annotation,{'review':{'status':'accepted'},'shapes':[{'points':[[1,2]]}]})
    before=annotation.read_bytes()
    write_manifests(tmp_path,{'chirp_h5_001'},{'root':'F:/raw'})
    assert {r['path'] for r in entries(tmp_path)}=={'chirp_h5_001','lfs_001'}
    assert read_json(tmp_path/'catalog.json')['count']==2
    assert annotation.read_bytes()==before


def test_catalog_cannot_escape_dataset_directory(tmp_path):
    atomic_json(tmp_path/'catalog.json',{'schema':'ionoreview-library/1','datasets':[
        {'path':'../elsewhere','title':'bad','count':1}]})
    with pytest.raises(ValueError):entries(tmp_path)


def test_verifier_detects_corruption_and_bad_axes(tmp_path):
    from ionoreview.data import digest
    from ionoreview.verify_archive import check_item
    (tmp_path/'images').mkdir()
    (tmp_path/'arrays').mkdir()
    palette_image(np.ones((4,5),dtype=np.float32)*35).save(tmp_path/'images/a.png')
    np.savez_compressed(tmp_path/'arrays/a.npz',db=np.ones((4,5),dtype=np.float32),
        freq_mhz=np.arange(5),range_km=np.arange(4)[::-1])
    item={'id':'a','image':'images/a.png','axes':'arrays/a.npz','width':5,'height':4,
        'image_sha256':digest(tmp_path/'images/a.png'),'axes_sha256':digest(tmp_path/'arrays/a.npz')}
    assert check_item((tmp_path,item))['ok']
    np.savez_compressed(tmp_path/'arrays/a.npz',db=np.ones((4,5),dtype=np.float32),
        freq_mhz=np.array([0,1,2,2,4]),range_km=np.arange(4)[::-1])
    assert not check_item((tmp_path,item))['ok']
    item['axes_sha256']=digest(tmp_path/'arrays/a.npz')
    assert check_item((tmp_path,item))['error']=='physical axes'
