"""Find bundled video tools before consulting the user's development environment."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path


class ToolProcesses:
    """Video processes belonging to one desktop session, cancellable on exit."""

    def __init__(self):
        self.lock = threading.Lock()
        self.processes: set[subprocess.Popen] = set()
        self.stopping = False

    def cancel(self):
        with self.lock:
            self.stopping = True
            for process in self.processes:
                if process.poll() is None:
                    try:
                        process.kill()
                    except OSError:
                        pass  # Already exited while shutdown was requested.

    def run(self, command, **kwargs):
        check = kwargs.pop("check", False)
        timeout = kwargs.pop("timeout", None)
        input_data = kwargs.pop("input", None)
        if input_data is not None:
            if kwargs.get("stdin") not in (None, subprocess.DEVNULL):
                raise ValueError("stdin and input arguments may not both be used")
            kwargs["stdin"] = subprocess.PIPE
        if kwargs.pop("capture_output", False):
            if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
                raise ValueError("stdout and stderr arguments may not be used with capture_output")
            kwargs["stdout"] = kwargs["stderr"] = subprocess.PIPE
        with self.lock:
            if self.stopping:
                raise InterruptedError("Video processing cancelled: KemoMichi is shutting down")
            process = subprocess.Popen(command, **kwargs)
            self.processes.add(process)
        try:
            with process:
                try:
                    stdout, stderr = process.communicate(input_data, timeout=timeout)
                except subprocess.TimeoutExpired as exc:
                    process.kill()
                    exc.stdout, exc.stderr = process.communicate()
                    raise
                except BaseException:
                    process.kill()
                    raise
                with self.lock:
                    cancelled = self.stopping
                if cancelled:
                    raise InterruptedError("Video processing cancelled: KemoMichi is shutting down")
                if check and process.returncode:
                    raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        finally:
            with self.lock:
                self.processes.discard(process)


_tool_processes: ContextVar[ToolProcesses | None] = ContextVar("tool_processes", default=None)


@contextmanager
def tool_processes(session: ToolProcesses):
    token = _tool_processes.set(session)
    try:
        yield
    finally:
        _tool_processes.reset(token)


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
    session = _tool_processes.get()
    runner = session.run if session else subprocess.run
    return runner([executable, *args], **kwargs)
