from collections import Counter
from datetime import datetime, timedelta, timezone

from ionoreview.data import atomic_json
from ionoreview.experiment import choose_test, MSK


def test_blind_test_is_two_transmitters_per_local_hour_and_excludes_training_days(tmp_path):
    items=[]
    for day in [27,28]:
        for hour in range(24):
            for tx,minute in [('NIC1',15),('NIC2',45)]:
                local=datetime(2026,8,day,hour,minute,tzinfo=MSK)
                items.append({'id':f'{day}-{hour}-{tx}','tx':tx,'rx':'Yoshkar-Ola',
                              'when':local.astimezone(timezone.utc).isoformat()})
    path=tmp_path/'chirp_h5_fixture/manifest.json'
    atomic_json(path,{'items':items})
    before=path.read_bytes()
    day,selected=choose_test(tmp_path)
    assert day=='2026-08-28'
    assert len({i['id'] for _,i,_ in selected})==48
    assert Counter((i['tx'],t.hour) for _,i,t in selected)==Counter({(tx,h):1 for tx in ['NIC1','NIC2'] for h in range(24)})
    assert selected[0][2].astimezone(timezone.utc).date().isoformat()=='2026-08-27'
    day,selected=choose_test(tmp_path,{'2026-08-28'})
    assert day=='2026-08-27'
    assert path.read_bytes()==before
