from dataclasses import replace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from ionoreview.clustering import ClusterParams, cluster_ionogram, image_features, _contours_without_holes
from ionoreview.data import validate_shapes, ReviewStore, atomic_json
from ionoreview.folders import import_image_folder, copy_pack


def tracks():
    db = np.full((80, 100), 20.0)
    db[15:18, 10:75] = 50
    db[55:58, 15:80] = 50
    db[2:70, 95:97] = 50  # narrow-frequency interference
    db[30, 3] = 80         # isolated noise
    return db, np.arange(100) * .04, np.arange(80)[::-1] * 7.3


def test_dbscan_finds_unknown_count_and_rejects_carrier_and_noise():
    db, f, r = tracks()
    result = cluster_ionogram(db, f, r, [0, 0, 99, 79])
    assert result.stats['clusters'] == 2
    assert result.stats['noise_points'] >= 1
    assert result.stats['discarded_clusters'] >= 1
    assert all(s['label'] == 'Signal' for s in result.shapes)
    validate_shapes(result.shapes, 100, 80)
    again = cluster_ionogram(db, f, r, [0, 0, 99, 79])
    assert result.shapes == again.shapes


def test_manual_count_and_roi_are_explicit():
    db, f, r = tracks()
    params = ClusterParams(method='K-means', n_clusters=2, min_span_mhz=0)
    result = cluster_ionogram(db, f, r, [5, 5, 85, 70], params)
    assert result.stats['clusters'] == 2
    assert result.params['n_clusters'] == 2
    roi = cluster_ionogram(db, f, r, [5, 5, 85, 30])
    assert roi.stats['clusters'] == 1
    assert all(5 <= p[0] <= 85 and 5 <= p[1] <= 30 for s in roi.shapes for p in s['points'])


def test_empty_nonfinite_data_and_density_limit():
    db, f, r = tracks()
    db[:] = np.nan
    assert not cluster_ionogram(db, f, r, [0, 0, 99, 79]).shapes
    large = np.ones((200, 200)) * 70
    with pytest.raises(ValueError, match='20000'):
        cluster_ionogram(large, np.arange(200), np.arange(200)[::-1], [0, 0, 199, 199])
    with pytest.raises(ValueError):
        replace(ClusterParams(), n_clusters=0).validate()
    with pytest.raises(ValueError):
        replace(ClusterParams(), frequency_gap_mhz=0).validate()


def test_contours_do_not_fill_hollow_trace_interior():
    mask = np.zeros((40, 40), dtype=np.uint8)
    mask[5:35, 5:8] = 1
    mask[5:35, 32:35] = 1
    mask[5:8, 5:35] = 1
    mask[32:35, 5:35] = 1
    polygons = _contours_without_holes(mask, 0, 0, 40, 40)
    assert len(polygons) >= 2
    image = Image.new('L', (40, 40))
    draw = ImageDraw.Draw(image)
    for polygon in polygons:
        draw.polygon([tuple(p) for p in polygon], fill=255)
    assert image.getpixel((20, 20)) == 0
    assert image.getpixel((6, 20)) == 255


def test_image_folder_roundtrip_has_pixels_and_unassigned_split(tmp_path):
    folder = tmp_path/'source'
    folder.mkdir()
    Image.new('RGB', (100, 60), 'blue').save(folder/'first.jpg')
    atomic_json(folder/'first.json', {'imagePath':'first.jpg','imageWidth':100,'imageHeight':60,
                'shapes':[{'label':'1F','points':[[10,10],[40,10],[40,20],[10,20]],'shape_type':'polygon'}]})
    (folder/'broken.png').write_bytes(b'not an image')
    pack = import_image_folder(folder, tmp_path/'pack')
    store = ReviewStore(pack)
    assert len(store.items) == 1
    item = store.items[0]
    assert item['axes'] is None
    assert item['split'] == 'unassigned'
    assert store.load(item)['review']['status'] == 'pending'
    assert store.load(item)['shapes'][0]['label'] == '1F'
    assert len(store.manifest['errors']) == 1
    with Image.open(pack/item['image']) as image:
        assert image.size == (100, 60)
    copied = copy_pack(pack, tmp_path/'copy')
    assert ReviewStore(copied).items == store.items
    with pytest.raises(ValueError):
        copy_pack(pack, pack/'recursive_copy')


def test_colour_image_features_exclude_white_plot_margin():
    image = Image.new('RGB', (100, 80), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 90, 70), fill='blue')
    draw.line((15, 40, 85, 40), fill='yellow', width=3)
    score = image_features(image)
    assert score[0, 0] == 0
    assert score[40, 30] > score[20, 30]


def test_manual_regression_on_pilot_case_010():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    path=root/'datasets/pilot/arrays/case_010.npz'
    if not path.exists():path=root/'review_data/pilot/arrays/case_010.npz'
    if not path.exists():
        pytest.skip('Optional real pilot array is not installed')
    with np.load(path) as z:
        f,r=z['freq_mhz'],z['range_km']
        x=np.interp([8.4,30.7],f,np.arange(len(f)))
        y=np.interp([4027.3,3046.4],r[::-1],np.arange(len(r))[::-1])
        result=cluster_ionogram(z['db'],f,r,[x[0],y[0],x[1],y[1]],
                                ClusterParams(method='K-means',n_clusters=4))
    assert result.stats['clusters']==4
    assert result.stats['noise_points']>0
    assert len(result.shapes)<40  # Old conversion generated 143 fragments.


def test_rectangle_intersection_uses_polygon_not_only_bounding_box():
    from ionoreview.geometry import intersects_rect
    triangle=[[0,0],[10,0],[0,10]]
    assert not intersects_rect(triangle,(8,8,9,9))
    assert intersects_rect(triangle,(2,2,3,3))
    assert intersects_rect(triangle,(-1,4,11,5))
