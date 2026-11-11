import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from fastapi.testclient import TestClient

from kemocore.runtime import tool_path
from kemoserver.app import create_app
from kemoserver.desktop import DesktopServer, DesktopSession, InstanceLock, existing_instance, local_opener
from kemoserver.security import ServerConfig


def test_desktop_requires_launch_cookie_and_rejects_foreign_origins(tmp_path):
    app = DesktopSession(create_app(ServerConfig(roots=[tmp_path])), 8765, "test-secret")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/info").status_code == 403
        assert client.get("/_desktop/launch?token=wrong").status_code == 403
        response = client.get("/_desktop/launch?token=test-secret")
        assert response.status_code == 200 and 'id="root"' in response.text
        assert client.get("/api/info").status_code == 200
        assert client.get("/api/browse", params={"path": str(tmp_path)}).status_code == 200
        assert client.post("/api/project/close", headers={"Origin": "https://untrusted.example"}).status_code == 403
        assert client.get("/api/info", headers={"Host": "untrusted.example:8765"}).status_code == 403
        assert client.get("/_desktop/status").status_code == 403
        assert client.get("/_desktop/status", headers={"X-KemoMichi-Instance": "test-secret"}).json() == {"ready": True}
    with TestClient(app, base_url="http://127.0.0.1:8765") as other:
        assert other.get("/api/info").status_code == 403


def test_instance_lock_can_recover_after_stale_state(tmp_path):
    (tmp_path / "desktop.json").write_text('{"url": "https://untrusted.example"}')
    assert existing_instance(tmp_path) is None
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    assert first.acquire()
    try:
        assert not second.acquire()
    finally:
        first.release()
    assert second.acquire()
    second.release()
    assert not (tmp_path / "desktop.json").exists()


def test_local_server_uses_free_port_and_closes_the_project(tmp_path, demo, monkeypatch):
    # An unrelated listener on the CLI's default port cannot interfere with port=0.
    monkeypatch.setenv("HTTP_PROXY", "http://unreachable.invalid:1234")
    server = DesktopServer(tmp_path)
    try:
        server.start()
        assert existing_instance(tmp_path) == server.url
        base = server.url.split("/_desktop/", 1)[0]
        client = local_opener()
        with pytest.raises(HTTPError) as error:
            client.open(base + "/api/info")
        assert error.value.code == 403
        with client.open(server.url) as response:
            assert response.status == 200
        request = Request(base + "/api/project/open", data=json.dumps({"path": str(demo)}).encode(),
                          headers={"Content-Type": "application/json"})
        with client.open(request) as response:
            assert json.load(response)["path"] == str(demo)
        assert server.app.state.workspace.project is not None
    finally:
        server.stop()
    assert server.app.state.workspace.project is None
    assert not server.thread.is_alive()
    assert existing_instance(tmp_path) is None


def test_bundled_ffmpeg_is_used_without_path(tmp_path, monkeypatch):
    folder = tmp_path / "bin"
    folder.mkdir()
    suffix = ".exe" if sys.platform == "win32" else ""
    for name in ("ffmpeg", "ffprobe"):
        (folder / (name + suffix)).write_bytes(b"bundled")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setenv("PATH", "")
    for name in ("ffmpeg", "ffprobe"):
        assert Path(tool_path(name)).parent == folder


def test_shutdown_cancels_video_process_in_http_worker(tmp_path, monkeypatch):
    import threading
    from kemoserver import desktop
    from kemocore import runtime

    entered = threading.Event()
    cancelled = threading.Event()
    original_create = desktop.create_app

    def app_with_slow_video(config):
        app = original_create(config)

        @app.get('/test-slow-video')
        def slow_video():
            entered.set()
            try:
                runtime.run_tool('ffmpeg', ['-c', 'import time; time.sleep(600)'], capture_output=True)
            except InterruptedError:
                cancelled.set()
            return {'cancelled': cancelled.is_set()}
        # StaticFiles is mounted at '/', so the test endpoint must precede it.
        app.router.routes.insert(0, app.router.routes.pop())
        return app

    monkeypatch.setattr(desktop, 'create_app', app_with_slow_video)
    monkeypatch.setattr(runtime, 'tool_path', lambda name: sys.executable)
    server = DesktopServer(tmp_path)
    server.start()
    client = local_opener()
    with client.open(server.url) as response:
        response.read()
    result = []

    def request_video():
        with client.open(server.url.split('/_desktop/')[0] + '/test-slow-video', timeout=15) as response:
            result.append(json.load(response))

    request = threading.Thread(target=request_video, daemon=True)
    request.start()
    try:
        assert entered.wait(3)
        server.stop()
        request.join(3)
        assert not request.is_alive()
        assert result == [{'cancelled': True}]
        assert not server.thread.is_alive()
        assert not server.tools.processes
    finally:
        server.stop()


def test_shutdown_timeout_does_not_close_database_under_running_requests(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock

    server = DesktopServer(tmp_path)
    server.thread = Mock()
    server.thread.is_alive.return_value = True
    workspace = Mock()
    server.app = SimpleNamespace(state=SimpleNamespace(workspace=workspace, jobs=SimpleNamespace(stopping=Mock())))
    with pytest.raises(RuntimeError, match='通信処理'):
        server.stop(timeout=0)
    workspace.close.assert_not_called()
    server.thread.join.assert_called_once_with(0)


def test_shutdown_cancels_project_creation_and_rolls_back_partial_ddb(tmp_path, monkeypatch):
    import threading
    from kemocore.timelapse import create
    from kemocore.demo import make_image
    from kemoserver.workspace import Jobs

    source = tmp_path / 'survey.tdb'
    target = source.with_suffix('.ddb')
    create.create_template(source)
    for i in range(3):
        make_image(tmp_path / f'{i}.jpg', None, 'test')
    entered, release = threading.Event(), threading.Event()
    original_datetime = create.file_datetime

    def slow_datetime(path):
        entered.set()
        assert release.wait(3)
        return original_datetime(path)

    monkeypatch.setattr(create, 'file_datetime', slow_datetime)
    jobs = Jobs()
    job = jobs.start('create', lambda progress: create.create_data_file(target, source, progress))
    try:
        assert entered.wait(3)
        jobs.stopping.set()
    finally:
        release.set()
        assert jobs.wait(3)
    assert job.status == 'failed'
    assert not target.exists()
    assert source.is_file()
