"""Captures the documentation screenshots of the annotator from a small demonstration pack built out of an existing one."""
import argparse
import ctypes
import json
import shutil
import sys
import tkinter as tk
from pathlib import Path

from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ionoreview.app import Reviewer
from ionoreview.clustering import ClusterParams

FRAMES = ['T031', 'Q030', 'T023', 'Q005', 'S229']


def demo(source, target):
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    items = [i for i in manifest['items'] if i['id'] in FRAMES]
    items.sort(key=lambda i: FRAMES.index(i['id']))
    for folder in ('images', 'arrays', 'annotations'):
        (target / folder).mkdir(parents=True)
    for item in items:
        shutil.copy2(source / item['image'], target / item['image'])
        shutil.copy2(source / item['axes'], target / item['axes'])
        note = json.loads((source / 'annotations' / f"{item['id']}.json").read_text(encoding='utf-8'))
        note.pop('correction', None)
        note['review']['note'] = ''
        note['review']['reviewer'] = 'Эксперт'
        for shape in note['shapes']:
            for key in ('corrected_from', 'correction_rule'):
                shape.get('flags', {}).pop(key, None)
        (target / 'annotations' / f"{item['id']}.json").write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest.update(items=items, name='Демонстрационный набор', annotation_policy='Пример для документации',
                    reference_origin='demonstration')
    manifest.pop('correction_rules', None)
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (target / 'settings.json').write_text(json.dumps({'reviewer': 'Эксперт', 'last_export': 'Not run yet', 'last_case': FRAMES[0],
                                                      'language': 'ru'}, ensure_ascii=False), encoding='utf-8')


def settle(root, rounds=30):
    for _ in range(rounds):
        root.update()
        root.after(15)
    root.update()


def grab(window, path):
    window.lift()
    settle(window)
    x, y = window.winfo_rootx(), window.winfo_rooty()
    ImageGrab.grab((x, y, x + window.winfo_width(), y + window.winfo_height()), all_screens=True).save(path)


def toplevels(root, known):
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w not in known]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('catalog', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    args.out.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    from ionoreview.library import choose
    picked = []

    def shoot():
        window = toplevels(root, [])[0]
        window.geometry('1100x640+40+40')
        grab(window, args.out / '01-catalog.png')
        window.destroy()
    root.after(900, shoot)
    choose(root, args.catalog)
    root.destroy()
    pack = Path('C:/IonoReview-demo/Демонстрационный набор')
    if pack.parent.exists():
        raise SystemExit(f'Remove {pack.parent} before capturing screenshots')
    try:
        demo(args.source, pack)
        root = tk.Tk()
        root.geometry('1520x960+20+20')
        reviewer = Reviewer(root, pack)
        settle(root)
        reviewer.load(0)
        settle(root)
        grab(root, args.out / '02-main-modes.png')
        target = next(i for i, s in enumerate(reviewer.document['shapes']) if s['label'] == '1F')
        reviewer.set_selection([target])
        reviewer.redraw()
        reviewer.show_label_menu()
        settle(root)
        grab(root, args.out / '03-selection-menu.png')
        reviewer.hide_label_menu()
        reviewer.deselect()
        reviewer.palette_name.set('Turbo')
        reviewer.choose_palette()
        settle(root)
        grab(root, args.out / '04-turbo.png')
        reviewer.palette_name.set('Моды')
        reviewer.choose_palette()
        reviewer.load(2)
        settle(root)
        reviewer.start_clustering(ClusterParams())
        for _ in range(200):
            settle(root, 2)
            if not reviewer.cluster_busy:
                break
        settle(root)
        grab(root, args.out / '05-auto-candidates.png')
        reviewer.clear_clusters(invalidate=True)
        known = toplevels(root, [])
        reviewer.open_cluster_dialog()
        settle(root)
        grab(toplevels(root, known)[0], args.out / '06-cluster-dialog.png')
        toplevels(root, known)[0].destroy()
        known = toplevels(root, [])
        reviewer.show_guide()
        settle(root)
        grab(toplevels(root, known)[0], args.out / '07-guide.png')
        toplevels(root, known)[0].destroy()
        known = toplevels(root, [])
        reviewer.policy()
        settle(root)
        grab(toplevels(root, known)[0], args.out / '08-help.png')
        toplevels(root, known)[0].destroy()
        reviewer.set_language('en')
        reviewer.load(0)
        settle(root)
        grab(root, args.out / '09-english.png')
        reviewer.set_language('ru')
        settle(root)
        root.destroy()
    finally:
        shutil.rmtree(pack.parent, ignore_errors=True)


if __name__ == '__main__':
    main()
