"""Prepare original HDF5 soundings corresponding to the existing selected PNGs."""
from pathlib import Path
from datetime import datetime, timezone
import re

from ionoreview.prepare import prepare


def main():
    root = Path("F:/MyData/ND/lfs")
    selected = sorted((root / "ionozond_data_selected").glob("lfm_ionogram-*.png"))
    paths = []
    for image in selected:
        match = re.search(r"-(\d+)\.\d+\.png$", image.name)
        if not match:
            continue
        day = datetime.fromtimestamp(int(match[1]), timezone.utc).strftime("%Y.%m.%d")
        source = root / "ionozond_data" / day / image.with_suffix(".h5").name
        if source.exists():
            paths.append(source)
    if not paths:
        raise SystemExit("Не найдены исходные HDF5 для отобранных изображений")
    project=Path(__file__).resolve().parent
    prepare(paths, project / "datasets" / "pilot", project / "vendor" / "ionograms_handler")


if __name__ == "__main__":
    main()
