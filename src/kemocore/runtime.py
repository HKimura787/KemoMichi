"""Find bundled video tools before consulting the user's development environment."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def bundled_tools() -> Path | None:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "bin" if base else None


def tool_path(name: str) -> str | None:
    if name not in {"ffmpeg", "ffprobe"}:
        raise ValueError(name)
    filename = name + (".exe" if os.name == "nt" else "")
    folders = [bundled_tools()]
    if os.environ.get("KEMOMICHI_FFMPEG_DIR"):
        folders.append(Path(os.environ["KEMOMICHI_FFMPEG_DIR"]))
    for folder in folders:
        if folder and (folder / filename).is_file():
            return str(folder / filename)
    found = shutil.which(name)
    if found:
        return found
    # Finder starts apps with a minimal PATH, even when Homebrew is installed.
    if sys.platform == "darwin":
        for folder in (Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
            if (folder / filename).is_file():
                return str(folder / filename)
    return None


def run_tool(name: str, args: list[str], **kwargs) -> subprocess.CompletedProcess:
    executable = tool_path(name)
    if not executable:
        raise FileNotFoundError(f"{name} is not installed or bundled")
    # Frozen Windows applications should not flash a console for every video.
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run([executable, *args], **kwargs)
