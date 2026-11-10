import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from subprocess import CompletedProcess
import threading

import pytest
from PIL import Image

from kemocore import media


@pytest.fixture
def cache(tmp_path, monkeypatch):
    folder = tmp_path / "cache"
    monkeypatch.setenv("KEMOMICHI_CACHE", str(folder))
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", str(2 * 1024**3))
    folder.mkdir()
    return folder


def image(tmp_path, name="source.jpg", color="blue"):
    path = tmp_path / name
    Image.new("RGB", (24, 24), color).save(path)
    return path


def old_entry(cache, name, size, used, accessed=100):
    path = cache / f"{hashlib.sha1(name.encode()).hexdigest()}.mp4"
    path.write_bytes(b"x" * size)
    os.utime(path, ns=(accessed, used))
    return path


@pytest.fixture
def video_tools(monkeypatch, tmp_path):
    path = tmp_path / "source.avi"
    path.write_bytes(b"source video")
    calls = []

    def run(name, args, **kwargs):
        calls.append((name, args))
        if name == "ffprobe":
            if "-of" in args and args[args.index("-of") + 1] == "json":
                output = json.dumps({"streams": [{"codec_name": "mjpeg", "width": 24, "height": 24,
                                                  "avg_frame_rate": "1/1", "time_base": "1/1"}],
                                     "format": {"format_name": "avi", "duration": "2"}})
            else:
                output = "0\n1\n"
        else:
            Path(args[-1]).write_bytes(b"converted media")
            output = b""
        return CompletedProcess(args, 0, output)

    monkeypatch.setattr(media, "has_ffmpeg", lambda: True)
    monkeypatch.setattr(media, "run_tool", run)
    return path, calls


def test_under_limit_preserves_existing_cache(cache, tmp_path):
    older = old_entry(cache, "older", 1000, 1)
    newer = old_entry(cache, "newer", 1000, 2)
    target = media.image_rendition(image(tmp_path), 320)
    assert older.exists() and newer.exists() and target.exists()


def test_eviction_orders_by_recorded_last_use(cache, tmp_path, monkeypatch):
    # mtime records app use; filesystem atime alone cannot reliably represent it.
    oldest = old_entry(cache, "oldest", 1000, 10, accessed=300)
    middle = old_entry(cache, "middle", 1000, 20, accessed=200)
    newest = old_entry(cache, "newest", 1000, 30, accessed=100)
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", "1800")
    target = media.image_rendition(image(tmp_path), 320)
    assert not oldest.exists() and not middle.exists()
    assert newest.exists() and target.exists()
    assert sum(path.stat().st_size for path in cache.iterdir()) <= 1800


def test_reuse_updates_last_use_without_regenerating(cache, tmp_path, monkeypatch):
    source = image(tmp_path)
    target = media.image_rendition(source, 320)
    before = target.stat()
    os.utime(target, ns=(1, 1))

    def unexpected_open(*args, **kwargs):
        raise AssertionError("A cached image should not be regenerated")

    monkeypatch.setattr(media.Image, "open", unexpected_open)
    assert media.image_rendition(source, 320) == target
    after = target.stat()
    assert after.st_ino == before.st_ino and after.st_size == before.st_size
    assert after.st_mtime_ns > 1


def test_recently_reused_entry_survives_next_write(cache, tmp_path, monkeypatch):
    first_source = image(tmp_path, "first.jpg", "blue")
    first = media.image_rendition(first_source, 320)
    second = media.image_rendition(image(tmp_path, "second.jpg", "red"), 320)
    os.utime(first, ns=(10, 10))
    os.utime(second, ns=(20, 20))
    assert media.image_rendition(first_source, 320) == first
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", "1500")
    third = media.image_rendition(image(tmp_path, "third.jpg", "green"), 320)
    assert first.exists() and third.exists() and not second.exists()
    assert sum(p.stat().st_size for p in cache.iterdir()) <= 1500


@pytest.mark.parametrize("limit", ["0", "1"])
def test_current_file_larger_than_limit_is_kept(cache, tmp_path, monkeypatch, limit):
    old = old_entry(cache, "old", 2000, 1)
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", limit)
    target = media.image_rendition(image(tmp_path), 320)
    with Image.open(target) as generated:
        assert generated.size == (24, 24)
    assert not old.exists() and target.stat().st_size > int(limit)


def test_temporaries_unrelated_files_and_symlinks_are_untouched(cache, tmp_path, monkeypatch):
    paths = [cache / ("a" * 40 + suffix) for suffix in (".tmp", ".tmp.jpg", ".tmp.mp4", ".tmp.webm", ".tmp.json")]
    paths.append(cache / "keep.txt")
    for path in paths:
        path.write_bytes(b"in progress or unrelated")
    folder = cache / ("b" * 40 + ".mp4")
    folder.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"original")
    link = cache / ("c" * 40 + ".mp4")
    try:
        link.symlink_to(outside)
    except OSError:
        link = None  # Windows accounts may not have permission to create symlinks.
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", "0")
    media.image_rendition(image(tmp_path), 320)
    assert all(path.exists() for path in paths) and folder.is_dir()
    assert outside.read_bytes() == b"original"
    if link:
        assert link.is_symlink()


@pytest.mark.parametrize("kind", ["thumbnail", "info", "mp4", "webm"])
def test_video_writers_evict_and_reuse(cache, monkeypatch, video_tools, kind):
    source, calls = video_tools
    old = old_entry(cache, "old", 2000, 1)
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", "1024")
    if kind == "thumbnail":
        create = lambda: media.video_thumbnail(source)
    elif kind == "info":
        create = lambda: media.video_info(source)
    else:
        create = lambda: media.playable_video(source, kind)
    result = create()
    assert result is not None and not old.exists()
    count = len(calls)
    assert create() == result and len(calls) == count
    assert sum(p.stat().st_size for p in cache.iterdir()) <= 1024
    assert all(".tmp" not in path.name for path in cache.iterdir())


@pytest.mark.parametrize("kind", ["thumbnail", "mp4", "webm"])
@pytest.mark.parametrize("raises", [False, True])
def test_failed_video_conversion_removes_temporary(cache, monkeypatch, video_tools, kind, raises):
    source, _ = video_tools
    monkeypatch.setattr(media, "video_info", lambda path: {"codec": "mjpeg"})

    def fail(name, args, **kwargs):
        Path(args[-1]).write_bytes(b"partial conversion")
        if raises:
            raise OSError("conversion interrupted")
        return CompletedProcess(args, 1, b"")

    monkeypatch.setattr(media, "run_tool", fail)
    create = lambda: media.video_thumbnail(source) if kind == "thumbnail" else media.playable_video(source, kind)
    if raises:
        with pytest.raises(OSError, match="conversion interrupted"):
            create()
    else:
        assert create() is None
    assert list(cache.iterdir()) == []


def test_failed_image_conversion_removes_temporary(cache, tmp_path, monkeypatch):
    source = image(tmp_path)

    def fail(self, fp, *args, **kwargs):
        Path(fp).write_bytes(b"partial JPEG")
        raise OSError("image conversion interrupted")

    monkeypatch.setattr(Image.Image, "save", fail)
    with pytest.raises(OSError, match="image conversion interrupted"):
        media.image_rendition(source, 320)
    assert list(cache.iterdir()) == []


def test_failed_metadata_write_removes_temporary(cache, video_tools, monkeypatch):
    source, _ = video_tools
    write_text = Path.write_text

    def fail(self, *args, **kwargs):
        write_text(self, "partial JSON", encoding="utf-8")
        raise OSError("metadata write interrupted")

    monkeypatch.setattr(Path, "write_text", fail)
    with pytest.raises(OSError, match="metadata write interrupted"):
        media.video_info(source)
    assert list(cache.iterdir()) == []


def test_failed_probe_does_not_publish_metadata(cache, video_tools, monkeypatch):
    source, _ = video_tools
    monkeypatch.setattr(media, "run_tool", lambda *args, **kwargs: CompletedProcess([], 1, ""))
    assert media.video_info(source) == {"available": False}
    assert list(cache.iterdir()) == []


@pytest.mark.parametrize("container", ["mp4", "webm"])
def test_existing_proxy_survives_regenerating_missing_metadata(cache, video_tools, monkeypatch, container):
    source, calls = video_tools
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", "0")
    proxy = media.playable_video(source, container)
    assert proxy.exists() and not list(cache.glob("*.json"))
    count = sum(name == "ffmpeg" for name, _ in calls)
    assert media.playable_video(source, container) == proxy
    assert sum(name == "ffmpeg" for name, _ in calls) == count


def test_empty_cache_is_regenerated(cache, tmp_path):
    source = image(tmp_path)
    target = media.image_rendition(source, 320)
    expected = target.read_bytes()
    target.unlink()
    assert media.image_rendition(source, 320).read_bytes() == expected


def test_write_does_not_evict_an_entry_currently_being_reused(cache, tmp_path, monkeypatch):
    source = tmp_path / "source.avi"
    source.write_bytes(b"video")
    target = cache / f"{media._key(source, 'vinfo2')}.json"
    target.write_text('{"available": true}', encoding="utf-8")
    entered, finish = threading.Event(), threading.Event()
    read_text = Path.read_text

    def slow_read(self, *args, **kwargs):
        if self == target:
            entered.set()
            assert finish.wait(timeout=5)
        return read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", slow_read)
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", "0")
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(media.video_info, source)
        try:
            assert entered.wait(timeout=5)
            media.image_rendition(image(tmp_path), 320)
            assert target.exists()
        finally:
            finish.set()
        assert future.result(timeout=5) == {"available": True}


@pytest.mark.parametrize("value", ["invalid", "-1"])
def test_invalid_limit_falls_back_to_default(cache, monkeypatch, value, caplog):
    monkeypatch.setenv("KEMOMICHI_CACHE_MAX_BYTES", value)
    assert media._cache_limit() == media.DEFAULT_CACHE_MAX_BYTES
    assert "KEMOMICHI_CACHE_MAX_BYTES" in caplog.text
