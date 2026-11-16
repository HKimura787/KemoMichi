"""Start KemoMichi for the Playwright tests, with a layer-0 demo project ready to copy.

Layer 0 (docs/test-data.md): synthetic data from kemocore.demo only, nothing real.
The pristine demo is written to web/e2e/.tmp/pristine; each test copies it to its own folder,
so tests never see each other's edits. No project is opened at start, so the start screen shows.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from kemocore.demo import create_demo_project
from kemoserver.cli import main

HERE = Path(__file__).resolve().parent
TMP = HERE / ".tmp"


def prepare() -> Path:
    if TMP.exists():
        shutil.rmtree(TMP)
    ddb = create_demo_project(TMP / "pristine")
    (TMP / "runs").mkdir()
    return ddb


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "8790"
    print("demo:", prepare(), flush=True)
    main(["serve", "--port", port, "--no-browser"])
