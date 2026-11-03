from __future__ import annotations

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="ИоноРазметка: локальная экспертная приёмка")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review")
    review.add_argument("pack", type=Path)
    library = commands.add_parser('library')
    library.add_argument('folder',type=Path)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("files", nargs="+", type=Path)
    prepare.add_argument("--out", required=True, type=Path)
    prepare.add_argument("--project", type=Path, default=Path(__file__).resolve().parent.parent/'vendor/ionograms_handler')
    prepare.add_argument("--gate", nargs=2, type=float, default=(0, 8000))
    imp = commands.add_parser("import", help="Импорт предварительной разметки LabelMe")
    imp.add_argument("pack", type=Path)
    imp.add_argument("case_id")
    imp.add_argument("candidate", type=Path)
    imp.add_argument("--author", required=True)
    export = commands.add_parser("export")
    export.add_argument("pack", type=Path)
    export.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.command == 'library':
        from .app import run_library
        run_library(args.folder)
    elif args.command == "review":
        from .app import run
        run(args.pack)
    elif args.command == "prepare":
        from .prepare import prepare as build
        build(args.files, args.out, args.project, tuple(args.gate))
    else:
        from .data import ReviewStore
        store = ReviewStore(args.pack)
        if args.command == "import":
            item = next((i for i in store.items if i["id"] == args.case_id), None)
            if item is None:
                parser.error("Нет такого case_id")
            store.import_labelme(item, args.candidate, args.author)
            print("Импортировано как предварительная разметка; нужна приёмка экспертом")
        else:
            print(f"Экспортировано {store.export(args.destination)} принятых изображений")


if __name__ == "__main__":
    main()
