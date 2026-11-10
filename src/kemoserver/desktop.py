"""Double-click launcher: a private local server and a small native control window."""

from __future__ import annotations

import argparse
import hmac
import http.cookiejar
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
import webbrowser

import uvicorn
from starlette.responses import JSONResponse, RedirectResponse, Response

from .app import create_app
from .security import ServerConfig

log = logging.getLogger(__name__)


def application_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "KemoMichi"


def local_opener():
    # Corporate proxy environment variables must not send local requests elsewhere.
    return build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))


class InstanceLock:
    """An OS lock survives stale state files and is released even after a crash."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.file = None

    def acquire(self) -> bool:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = (self.directory / "desktop.lock").open("a+b")
        if self.file.seek(0, 2) == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            return False
        return True

    def release(self):
        if not self.file:
            return
        (self.directory / "desktop.json").unlink(missing_ok=True)
        self.file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        self.file.close()
        self.file = None


class DesktopSession:
    """Only the browser launched for this instance may use its local filesystem API."""

    def __init__(self, app, port: int, token: str):
        self.app, self.port, self.token = app, port, token
        self.cookie = f"kemomichi_{port}"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        host = f"127.0.0.1:{self.port}"
        if headers.get(b"host", b"").decode() != host:
            await Response("Invalid host", status_code=403)(scope, receive, send)
            return
        if scope["path"] == "/_desktop/status":
            given = headers.get(b"x-kemomichi-instance", b"").decode()
            response = JSONResponse({"ready": True}, headers={"Cache-Control": "no-store"}) if hmac.compare_digest(
                given, self.token) else Response(status_code=403)
            await response(scope, receive, send)
            return
        if scope["path"] == "/_desktop/launch" and scope["method"] == "GET":
            given = parse_qs(scope.get("query_string", b"").decode()).get("token", [""])[0]
            if hmac.compare_digest(given, self.token):
                response = RedirectResponse("/", status_code=303, headers={"Cache-Control": "no-store"})
                response.set_cookie(self.cookie, self.token, httponly=True, samesite="strict")
            else:
                response = Response("Please open KemoMichi from the launcher.", status_code=403)
            await response(scope, receive, send)
            return
        from http.cookies import SimpleCookie
        cookies = SimpleCookie()
        try:
            cookies.load(headers.get(b"cookie", b"").decode())
            given = cookies[self.cookie].value if self.cookie in cookies else ""
        except Exception:
            given = ""
        origin = headers.get(b"origin", b"").decode()
        if not hmac.compare_digest(given, self.token) or (origin and origin != f"http://{host}"):
            await Response("Please open KemoMichi from the launcher.", status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)


class DesktopServer:
    def __init__(self, directory: Path):
        self.directory = directory
        self.token = secrets.token_urlsafe(32)
        self.url = ""
        self.server = self.thread = self.socket = self.app = None

    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", 0))
        port = self.socket.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}/_desktop/launch?token={self.token}"
        self.app = create_app(ServerConfig(port=port))
        wrapped = DesktopSession(self.app, port, self.token)
        config = uvicorn.Config(wrapped, host="127.0.0.1", port=port, loop="asyncio", http="h11",
                                ws="none", log_config=None, access_log=False, proxy_headers=False)
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 20
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                self.stop()
                raise RuntimeError("ローカルの作業画面を起動できませんでした。")
            time.sleep(0.05)
        state = self.directory / "desktop.json"
        state.write_text(json.dumps({"url": self.url}), encoding="utf-8")
        state.chmod(0o600)

    def stop(self):
        if self.server:
            self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join()
        if self.app:
            # Project creation runs outside HTTP requests; let it finish before closing SQLite.
            jobs = self.app.state.jobs
            while any(job.status == "running" for job in list(jobs.jobs.values())):
                time.sleep(0.1)
            self.app.state.workspace.close()
        if self.socket:
            self.socket.close()


def existing_instance(directory: Path) -> str | None:
    try:
        url = json.loads((directory / "desktop.json").read_text(encoding="utf-8"))["url"]
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
            return None
        token = parse_qs(parsed.query)["token"][0]
        request = Request(f"http://127.0.0.1:{parsed.port}/_desktop/status",
                          headers={"X-KemoMichi-Instance": token})
        with local_opener().open(request, timeout=1) as response:
            return url if response.status == 200 and json.load(response).get("ready") else None
    except (OSError, ValueError, KeyError):
        return None


def open_folder(path: Path):
    import subprocess
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


def run_window(server: DesktopServer):
    import tkinter as tk
    from tkinter import ttk

    window = tk.Tk()
    window.title("KemoMichi")
    window.minsize(460, 250)
    frame = ttk.Frame(window, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="KemoMichi", font=("", 24, "bold")).pack(anchor="w")
    ttk.Label(frame, text="HDDのデータを、いつものブラウザで。", padding=(0, 8)).pack(anchor="w")
    status = tk.StringVar(value="起動しています…")
    ttk.Label(frame, textvariable=status, wraplength=440).pack(anchor="w", pady=12)
    row = ttk.Frame(frame)
    row.pack(anchor="w", pady=8)
    opened = ttk.Button(row, text="ブラウザで開く", state="disabled")
    opened.pack(side="left", padx=(0, 8))
    exit_button = ttk.Button(row, text="終了")
    exit_button.pack(side="left")
    ttk.Button(frame, text="ログフォルダを開く", command=lambda: open_folder(server.directory)).pack(anchor="w")
    failure: list[str] = []
    ready = threading.Event()
    stopped = threading.Event()
    closing = False

    def start():
        try:
            from kemocore.runtime import bundled_tools, tool_path
            if getattr(sys, "frozen", False):
                folder = bundled_tools()
                for name in ("ffmpeg", "ffprobe"):
                    found = tool_path(name)
                    if not found or Path(found).parent != folder:
                        raise RuntimeError("動画ツールが同梱されていません。アプリを入れ直してください。")
            server.start()
        except Exception as exc:
            log.exception("Startup failed")
            failure.append(str(exc))
            server.stop()
        finally:
            ready.set()

    def stop():
        ready.wait()
        server.stop()
        stopped.set()

    def browser():
        if not webbrowser.open(server.url):
            status.set("ブラウザが開かない場合は、既定のブラウザを設定してからもう一度お試しください。")

    def close():
        nonlocal closing
        if closing:
            return
        closing = True
        opened.configure(state="disabled")
        exit_button.configure(state="disabled")
        status.set("処理の完了を待って終了しています…")
        threading.Thread(target=stop, daemon=True).start()

    def poll():
        if stopped.is_set():
            window.destroy()
            return
        if ready.is_set() and opened.instate(["disabled"]) and not closing:
            if failure:
                status.set(f"起動できませんでした。{failure[0]} ログフォルダをご確認ください。")
            else:
                status.set("作業画面を開きました。終了するときは、このウィンドウの「終了」を押してください。")
                opened.configure(state="normal")
                opened.focus_set()
                browser()
        window.after(150, poll)

    opened.configure(command=browser)
    exit_button.configure(command=close)
    window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Control-o>", lambda event: browser() if ready.is_set() and not failure and not closing else None)
    if sys.platform == "darwin":
        window.bind("<Command-o>", lambda event: browser() if ready.is_set() and not failure and not closing else None)
        window.createcommand("tk::mac::Quit", close)
        window.createcommand("tk::mac::ReopenApplication", lambda: browser() if ready.is_set() and not failure and not closing else None)
    threading.Thread(target=start, daemon=True).start()
    window.after(150, poll)
    try:
        window.mainloop()
    finally:
        ready.wait()
        server.stop()


def smoke_test(directory: Path) -> dict:
    """Exercise the packaged runtime, static files, SQLite and both bundled video tools."""
    import tempfile
    from kemocore.demo import create_demo_project
    from kemocore.runtime import run_tool, tool_path

    result = {"ffmpeg": tool_path("ffmpeg"), "ffprobe": tool_path("ffprobe")}
    for name in ("ffmpeg", "ffprobe"):
        run_tool(name, ["-version"], capture_output=True, check=True)
    with tempfile.TemporaryDirectory(prefix="kemomichi-check-") as folder:
        server = DesktopServer(directory)
        try:
            ddb = create_demo_project(Path(folder) / "HDD data 日本語")
            server.start()
            client = local_opener()
            with client.open(server.url) as response:
                assert b"root" in response.read()
            base = server.url.split("/_desktop/", 1)[0]
            request = Request(base + "/api/project/open", data=json.dumps({"path": str(ddb)}).encode(),
                              headers={"Content-Type": "application/json"})
            with client.open(request) as response:
                project = json.load(response)
                assert project["total"] == 27, project
            with client.open(base + "/api/files?limit=100") as response:
                rows = json.load(response)["rows"]
            video = next(row for row in rows if row["values"]["File"].endswith(".MP4"))
            with client.open(f"{base}/api/media/{video['id']}/video-info") as response:
                info = json.load(response)
                assert info["available"] and len(info["frameTimes"]) > 0, info
            with client.open(f"{base}/api/media/{video['id']}/video") as response:
                assert len(response.read()) > 100
            with client.open(base + "/api/media/1/preview") as response:
                assert response.headers["Content-Type"] == "image/jpeg"
            result.update(ok=True, mediaCount=project["total"], videoFrames=len(info["frameTimes"]))
        finally:
            server.stop()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="KemoMichi browser launcher")
    parser.add_argument("--state-dir", type=Path, default=application_dir())
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    directory = args.state_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    handler = RotatingFileHandler(directory / "launcher.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    lock = InstanceLock(directory)
    if not lock.acquire():
        for _ in range(40):
            url = existing_instance(directory)
            if url:
                webbrowser.open(url)
                return
            time.sleep(0.1)
        import tkinter.messagebox
        tkinter.messagebox.showerror("KemoMichi", "別のKemoMichiが起動中です。起動完了を待ってからもう一度開いてください。")
        return
    try:
        if args.smoke_test:
            try:
                result = smoke_test(directory)
            except Exception as exc:
                log.exception("Packaged smoke test failed")
                result = {"ok": False, "error": str(exc)}
            if args.report:
                args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            if sys.stdout:
                print(json.dumps(result, ensure_ascii=False))
            if not result["ok"]:
                raise SystemExit(1)
        else:
            run_window(DesktopServer(directory))
    finally:
        lock.release()


if __name__ == "__main__":
    main()
