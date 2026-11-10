"""The `kemo` command."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path


def _serve(args) -> None:
    import uvicorn

    from .app import create_app
    from .security import ServerConfig

    config = ServerConfig(
        host=args.host, port=args.port,
        password=args.password or os.environ.get("KEMOMICHI_PASSWORD", ""),
        roots=[Path(r).resolve() for r in args.root],
        open_path=Path(args.path).resolve() if args.path else None,
    )
    config.check()
    app = create_app(config)
    url = f"http://{'127.0.0.1' if config.host in ('0.0.0.0', '::') else config.host}:{config.port}/"
    print(f"KemoMichi: {url}")
    if not args.no_browser and not config.server_mode:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=config.host, port=config.port, log_level="warning")


def _demo(args) -> None:
    from kemocore.demo import create_demo_project

    ddb = create_demo_project(Path(args.folder))
    print(ddb)


def _export_csv(args) -> None:
    from kemocore.timelapse.csv_export import export_csv
    from kemocore.timelapse.project import TimelapseProject

    project = TimelapseProject(args.ddb, read_only=True)
    print(export_csv(project, Path(args.output) if args.output else None))


def _import_recognitions(args) -> None:
    import json

    from kemocore.timelapse.project import TimelapseProject
    from kemocore.timelapse.recognitions import import_recognitions

    project = TimelapseProject(args.ddb)
    report = import_recognitions(project, Path(args.json))
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


def _new(args) -> None:
    from kemocore.timelapse.create import create_data_file

    folder = Path(args.folder).resolve()
    template = Path(args.template)
    count = create_data_file(folder / template.with_suffix(".ddb").name, template)
    print(f"{count} files")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kemo", description="KemoMichi")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the app (opens your browser)")
    serve.add_argument("path", nargs="?", help=".ddb file or folder to open")
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on (default: this computer only)")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--password", default="", help="required when --host is a network address")
    serve.add_argument("--root", action="append", default=[], help="folder people may open (repeatable)")
    serve.add_argument("--no-browser", action="store_true")
    serve.set_defaults(func=_serve)

    demo = sub.add_parser("demo", help="create a demo project with dummy images and videos")
    demo.add_argument("folder")
    demo.set_defaults(func=_demo)

    csv = sub.add_parser("export-csv", help="write a CSV with the same name as the data file")
    csv.add_argument("ddb")
    csv.add_argument("--output")
    csv.set_defaults(func=_export_csv)

    rec = sub.add_parser("import-recognitions", help="import a MegaDetector/AddaxAI recognition JSON")
    rec.add_argument("ddb")
    rec.add_argument("json")
    rec.set_defaults(func=_import_recognitions)

    new = sub.add_parser("new", help="create a .ddb in a folder with the same name as the template")
    new.add_argument("folder")
    new.add_argument("--template", required=True)
    new.set_defaults(func=_new)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["serve", *(argv if argv is not None else sys.argv[1:])])
    args.func(args)


if __name__ == "__main__":
    main()
