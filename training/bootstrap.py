"""Install the optional training stack outside the editor's environment."""
from pathlib import Path
import subprocess
import sys
import venv

project=Path(__file__).resolve().parents[1]
environment=Path.home()/'.t3/training-envs/ionoreview'
if not (environment/'pyvenv.cfg').exists():venv.create(environment,system_site_packages=True,with_pip=True)
python=environment/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
torch_check=subprocess.run([str(python),'-c','import torch; assert torch.version.cuda is not None'],capture_output=True)
if torch_check.returncode:
    subprocess.run([str(python),'-m','pip','install','torch==2.11.0','torchvision==0.26.0',
        '--index-url','https://download.pytorch.org/whl/cu128'],check=True)
subprocess.run([str(python),'-m','pip','install','-r',str(project/'training/requirements.txt')],check=True)
site=subprocess.check_output([str(python),'-c','import sysconfig; print(sysconfig.get_path("purelib"))'],text=True).strip()
(Path(site)/'ionoreview_train.pth').write_text(str(project)+'\n',encoding='utf8')
print('Training Python:',python)
