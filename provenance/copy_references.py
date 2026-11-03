"""One-time migration of attachments supplied in the project discussion."""
from pathlib import Path
import hashlib
import json
import shutil

root=Path('C:/Users/VV/.t3/userdata/attachments')
project=Path(__file__).resolve().parents[1]
files=[
 ('7fe09d02-d0e5-44cb-88a1-b5c5a6e3ca0f-1b379fec-7eec-4793-b44f-ad01cfcb3146-docx.docx','1595632_uid1116259_4132916d4ca5648b82744548bc083aa4f6bf628c.docx'),
 ('7fe09d02-d0e5-44cb-88a1-b5c5a6e3ca0f-09091a2a-ae02-4cf1-86e8-c5574fce59dd-pdf.pdf','Temy_NIR_IST_ionosphere.pdf'),
 ('7fe09d02-d0e5-44cb-88a1-b5c5a6e3ca0f-3e5ed327-603b-4f66-970e-b88db26ada24-pptx.pptx','ВыступлениеПроект_Последняя_версия.pptx'),
 ('7fe09d02-d0e5-44cb-88a1-b5c5a6e3ca0f-18cf2536-8a26-49c4-bfc7-e5c391ac19af-docx.docx','Текст.docx'),
 ('7fe09d02-d0e5-44cb-88a1-b5c5a6e3ca0f-780213e7-22d5-4c53-a26b-06196c01449d-docx.docx','Анализ_метода_Mask_R_CNN_для_интерпретации_ионограмм_3.docx')]
out=project/'references'
out.mkdir(exist_ok=True)
manifest=[]
for source,name in files:
    src=root/source
    dst=out/name
    shutil.copy2(src,dst)
    manifest.append({'file':name,'source':str(src),'sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'bytes':dst.stat().st_size})
(project/'provenance'/'references.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
print('References copied:',len(manifest))
