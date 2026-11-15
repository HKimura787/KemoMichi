import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

from fastapi.testclient import TestClient
import pytest
from starlette.responses import FileResponse

from kemocore import media
from kemoserver.app import create_app
from kemoserver.security import ServerConfig


def test_cache_eviction_waits_for_http_delivery_and_releases_afterwards(demo, tmp_path, monkeypatch):
    folder = tmp_path / "cache"
    monkeypatch.setenv("KEMOMICHI_CACHE", str(folder))
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", "0")
    entered, finish = threading.Event(), threading.Event()
    original_call = FileResponse.__call__

    async def delayed_response(self, scope, receive, send):
        if scope["path"] == "/api/media/1/thumb":
            entered.set()
            assert await asyncio.to_thread(finish.wait, 5)
        await original_call(self, scope, receive, send)

    monkeypatch.setattr(FileResponse, "__call__", delayed_response)
    app = create_app(ServerConfig(open_path=demo))
    try:
        with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as executor:
            request = executor.submit(client.get, "/api/media/1/thumb")
            try:
                assert entered.wait(timeout=5)
                assert client.get("/api/media/2/thumb").status_code == 200
            finally:
                finish.set()
            response = request.result(timeout=5)
            assert response.status_code == 200 and response.content.startswith(b"\xff\xd8")
            # Once both responses finish, the next write can remove their entries.
            assert client.get("/api/media/3/thumb").status_code == 200
            assert len(list(folder.glob("*.jpg"))) == 1
    finally:
        app.state.workspace.close()


@pytest.mark.parametrize("failure", ["missing", "exception"])
def test_failed_response_generation_releases_lease(demo, tmp_path, monkeypatch, failure):
    monkeypatch.setenv("KEMOMICHI_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", "0")
    image_rendition = media.image_rendition
    generated = []

    def fail(path, size):
        generated.append(image_rendition(path, size))
        if failure == "exception":
            raise RuntimeError("conversion interrupted")
        return None

    monkeypatch.setattr(media, "image_rendition", fail)
    app = create_app(ServerConfig(open_path=demo))
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/media/1/thumb")
            assert response.status_code == (500 if failure == "exception" else 204)
            monkeypatch.setattr(media, "image_rendition", image_rendition)
            assert client.get("/api/media/2/thumb").status_code == 200
            assert not generated[0].exists()
    finally:
        app.state.workspace.close()
