"""Thumbnails, previews and video facts. Originals are never modified; derived files go to a cache."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from fractions import Fraction
from pathlib import Path
from typing import Callable, TypeVar

from PIL import Image, ImageOps

from .runtime import run_tool, tool_path
from .timelapse.constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

THUMB_SIZE = 320
PREVIEW_SIZE = 1920
DEFAULT_CACHE_MAX_BYTES = 2 * 1024**3
# Containers that hold H.264 which Chrome, Edge, Safari and the desktop app play directly.
_PLAYABLE_CONTAINERS = {".mp4", ".mov", ".webm", ".m4v"}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_cache_guard = threading.Lock()
_active_cache: Counter[Path] = Counter()
# Only completed files created by this module are eligible; never follow symlinks or remove temporaries.
_CACHE_FILE = re.compile(r"[0-9a-f]{40}\.(?:jpg|json|mp4|webm)\Z")
log = logging.getLogger(__name__)
_T = TypeVar("_T")


class CacheLease:
    """Keep generated/reused entries alive until an HTTP response finishes serving them."""

    def __init__(self):
        self._paths: set[Path] = set()

    def generate(self, create: Callable[[], _T]) -> _T:
        token = _cache_lease.set(self)
        try:
            return create()
        except BaseException:
            self.close()
            raise
        finally:
            _cache_lease.reset(token)

    def close(self):
        with _cache_guard:
            for path in self._paths:
                _active_cache[path] -= 1
                if not _active_cache[path]:
                    del _active_cache[path]
            self._paths.clear()


_cache_lease: ContextVar[CacheLease | None] = ContextVar("media_cache_lease", default=None)


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def cache_dir() -> Path:
    base = os.environ.get("KEMOMICHI_CACHE")
    if base:
        path = Path(base)
    elif os.name == "nt":
        path = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "KemoMichi" / "cache"
    else:
        path = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "kemomichi"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _cache_limit() -> int:
    value = os.environ.get("KEMOMICHI_CACHE_MAX_BYTES")
    if value is None:
        return DEFAULT_CACHE_MAX_BYTES
    try:
        limit = int(value)
        if limit >= 0:
            return limit
    except ValueError:
        pass
    log.warning("Invalid KEMOMICHI_CACHE_MAX_BYTES=%r; using %s bytes", value, DEFAULT_CACHE_MAX_BYTES)
    return DEFAULT_CACHE_MAX_BYTES


@contextmanager
def _cache_entry(path: Path, kind: str, suffix: str):
    target = cache_dir() / f"{_key(path, kind)}{suffix}"
    with _cache_guard:
        _active_cache[target] += 1
        lease = _cache_lease.get()
        if lease is not None and target not in lease._paths:
            lease._paths.add(target)
            _active_cache[target] += 1
    try:
        with _lock_for(str(target)):
            yield target
    finally:
        with _cache_guard:
            _active_cache[target] -= 1
            if not _active_cache[target]:
                del _active_cache[target]


def _cache_hit(target: Path) -> bool:
    """Record last use in the cache file's mtime; filesystem atime may be disabled or noisy."""
    with _cache_guard:
        try:
            target.stat()
        except FileNotFoundError:
            return False
        try:
            os.utime(target, None)
        except FileNotFoundError:
            return False
        except OSError:
            pass  # A read-only cache entry can still be reused.
        return True


@contextmanager
def _temporary_cache_file(target: Path):
    # Unique names avoid collisions with another process converting the same source.
    tmp = target.with_name(f"{target.stem}.{uuid.uuid4().hex}.tmp{target.suffix}")
    try:
        yield tmp
    finally:
        tmp.unlink(missing_ok=True)


def _prune_cache(folder: Path) -> None:
    """Called under _cache_guard after publishing; active entries count but are never evicted."""
    entries = []
    total = 0
    with os.scandir(folder) as scan:
        for entry in scan:
            try:
                if not _CACHE_FILE.fullmatch(entry.name) or not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            target = folder / entry.name
            total += stat.st_size
            entries.append((stat.st_mtime_ns, target, stat.st_size))
    limit = _cache_limit()
    if total <= limit:
        return
    for _, target, size in sorted(entries):
        if _active_cache[target]:
            continue
        try:
            target.unlink(missing_ok=True)
        except OSError:
            # Windows can refuse deletion while another process is serving this file.
            continue
        total -= size
        if total <= limit:
            break


def _publish_cache(tmp: Path, target: Path) -> None:
    with _cache_guard:
        tmp.replace(target)
        # The current target is pinned by _cache_entry, even if it alone exceeds the limit.
        try:
            os.utime(target, None)
            _prune_cache(target.parent)
        except OSError:
            log.warning("Could not clean media cache %s", target.parent, exc_info=True)


def _key(path: Path, kind: str) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{kind}"
    return hashlib.sha1(raw.encode()).hexdigest()


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def image_rendition(path: Path, size: int) -> Path:
    """A JPEG no larger than `size` on its long side, with EXIF rotation applied."""
    with _cache_entry(path, f"img{size}", ".jpg") as target:
        if _cache_hit(target):
            return target
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            with _temporary_cache_file(target) as tmp:
                img.save(tmp, "JPEG", quality=85 if size <= THUMB_SIZE else 90)
                _publish_cache(tmp, target)
        return target


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        return img.size


def has_ffmpeg() -> bool:
    return tool_path("ffmpeg") is not None and tool_path("ffprobe") is not None


def video_thumbnail(path: Path, size: int = THUMB_SIZE) -> Path | None:
    if not has_ffmpeg():
        return None
    with _cache_entry(path, f"vthumb{size}", ".jpg") as target:
        if _cache_hit(target):
            return target
        with _temporary_cache_file(target) as tmp:
            result = run_tool("ffmpeg",
                ["-v", "error", "-y", "-i", str(path), "-frames:v", "1",
                 "-vf", f"scale='min({size},iw)':-2", str(tmp)],
                capture_output=True)
            if result.returncode != 0 or not tmp.exists() or not tmp.stat().st_size:
                return None
            _publish_cache(tmp, target)
        return target


def video_info(path: Path) -> dict:
    """Codec, size, frame rate and the exact time of every frame (from ffprobe), cached."""
    with _cache_entry(path, "vinfo2", ".json") as target:
        if _cache_hit(target):
            return json.loads(target.read_text(encoding="utf-8"))
        if not has_ffmpeg():
            return {"available": False}
        probe = run_tool("ffprobe",
            ["-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,time_base:stream_tags=rotate:"
             "stream_side_data=rotation:format=duration,format_name",
             "-of", "json", str(path)], capture_output=True, text=True)
        if probe.returncode != 0:
            return {"available": False}
        meta = json.loads(probe.stdout or "{}")
        stream = (meta.get("streams") or [{}])[0]
        time_base = Fraction(stream.get("time_base") or "1/1000")
        frames = run_tool("ffprobe",
            ["-v", "error", "-select_streams", "v:0", "-show_entries",
             "frame=best_effort_timestamp", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
        if frames.returncode != 0:
            return {"available": False}
        stamps = []
        for line in frames.stdout.splitlines():
            line = line.strip().rstrip(",")
            if line and line.lstrip("-").isdigit():
                stamps.append(int(line))
        exact = bool(stamps)
        if not stamps:
            # No timestamps (some AVI files): fall back to frame number / frame rate.
            rate = Fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1")
            duration = float((meta.get("format") or {}).get("duration") or 0)
            count = int(duration * rate) if rate else 0
            time_base = 1 / rate if rate else Fraction(1, 1)
            stamps = list(range(count))
        first = stamps[0] if stamps else 0
        rate = Fraction(stream.get("avg_frame_rate") or "0/1") if stream.get("avg_frame_rate") not in (None, "0/0") else Fraction(0)
        rotation = 0
        for side in stream.get("side_data_list") or []:
            if "rotation" in side:
                rotation = int(side["rotation"])
        if (stream.get("tags") or {}).get("rotate"):
            rotation = int(stream["tags"]["rotate"])
        info = {
            "available": True,
            "codec": stream.get("codec_name"),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "rotation": rotation,
            "frameRate": float(rate) if rate else None,
            "timeBase": f"{time_base.numerator}/{time_base.denominator}",
            "exactTimes": exact,
            # Ticks relative to the first frame; seconds = ticks * timeBase.
            "frameTicks": [s - first for s in stamps],
            "container": (meta.get("format") or {}).get("format_name"),
        }
        with _temporary_cache_file(target) as tmp:
            tmp.write_text(json.dumps(info), encoding="utf-8")
            _publish_cache(tmp, target)
        return info


def frame_seconds(info: dict, frame: int) -> Fraction:
    tb = Fraction(info["timeBase"])
    ticks = info["frameTicks"]
    frame = max(0, min(frame, len(ticks) - 1))
    return ticks[frame] * tb


def format_seconds(value: Fraction) -> str:
    """Decimal text of an exact time; keeps every digit down to the microsecond, no trailing zeros."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole = int(value)
    micro = round((value - whole) * 1_000_000)
    if micro == 1_000_000:
        whole, micro = whole + 1, 0
    text = f"{whole}.{micro:06d}".rstrip("0").rstrip(".")
    return sign + text


def playable_video(path: Path, container: str = "mp4") -> Path | None:
    """The file itself if browsers can play it, else a cached proxy with the same frames.

    `container` is "mp4" (H.264, for Chrome, Edge, Safari and the desktop app) or "webm" (VP9,
    for browsers built without H.264).
    """
    with _cache_entry(path, "proxy2-" + container, f".{container}") as target:
        # Metadata may itself need to be generated; pin the requested proxy before that write.
        info = video_info(path)
        if container == "mp4" and path.suffix.lower() in _PLAYABLE_CONTAINERS and info.get("codec") == "h264":
            return path
        if container == "webm" and path.suffix.lower() == ".webm":
            return path
        if not has_ffmpeg():
            return None
        if _cache_hit(target):
            return target
        if container == "webm":
            codec = ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "32", "-b:v", "0",
                     "-row-mt", "1", "-c:a", "libopus"]
        else:
            codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
                     "-movflags", "+faststart"]
        # passthrough keeps every frame and its timestamp: no frames dropped or duplicated.
        with _temporary_cache_file(target) as tmp:
            result = run_tool("ffmpeg",
                ["-v", "error", "-y", "-i", str(path), "-map", "0:v:0", "-map", "0:a?",
                 "-fps_mode", "passthrough", *codec, str(tmp)], capture_output=True)
            if result.returncode != 0 or not tmp.exists() or not tmp.stat().st_size:
                return None
            _publish_cache(tmp, target)
        return target
