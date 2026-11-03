# Build with an isolated environment from requirements-build.txt.
from pathlib import Path

repo = Path(SPECPATH).parent
a = Analysis(
    [str(repo / 'packaging' / 'windows_entry.py')],
    pathex=[str(repo)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={'matplotlib': {'backends': ['Agg']}},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'transformers', 'peft', 'bitsandbytes', 'accelerate',
              'tensorflow', 'IPython', 'notebook', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
              'pytest', '_pytest', 'sklearn.datasets', 'sklearn.tests',
              'ionoreview.finetune', 'ionoreview.archive', 'ionoreview.prepare'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='IonoReview',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='IonoReview')
