"""Thumbnails, previews and video facts. Originals are never modified; derived files go to a cache."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageOps

from .runtime import run_tool, tool_path
from .timelapse.constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

THUMB_SIZE = 320
PREVIEW_SIZE = 1920
# Containers that hold H.264 which Chrome, Edge, Safari and the desktop app play directly.
_PLAYABLE_CONTAINERS = {".mp4", ".mov", ".webm", ".m4v"}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


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
    return path


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
    target = cache_dir() / f"{_key(path, f'img{size}')}.jpg"
    if target.exists():
        return target
    with _lock_for(str(target)):
        if target.exists():
            return target
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            tmp = target.with_suffix(".tmp")
            img.save(tmp, "JPEG", quality=85 if size <= THUMB_SIZE else 90)
            tmp.replace(target)
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
    target = cache_dir() / f"{_key(path, f'vthumb{size}')}.jpg"
    if target.exists():
        return target
    with _lock_for(str(target)):
        if target.exists():
            return target
        tmp = target.with_suffix(".tmp.jpg")
        result = run_tool("ffmpeg",
            ["-v", "error", "-y", "-i", str(path), "-frames:v", "1",
             "-vf", f"scale='min({size},iw)':-2", str(tmp)],
            capture_output=True)
        if result.returncode != 0 or not tmp.exists():
            return None
        tmp.replace(target)
    return target


def video_info(path: Path) -> dict:
    """Codec, size, frame rate and the exact time of every frame (from ffprobe), cached."""
    target = cache_dir() / f"{_key(path, 'vinfo2')}.json"
    if target.exists():
        return json.loads(target.read_text())
    if not has_ffmpeg():
        return {"available": False}
    with _lock_for(str(target)):
        if target.exists():
            return json.loads(target.read_text())
        probe = run_tool("ffprobe",
            ["-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,time_base:stream_tags=rotate:"
             "stream_side_data=rotation:format=duration,format_name",
             "-of", "json", str(path)], capture_output=True, text=True)
        meta = json.loads(probe.stdout or "{}")
        stream = (meta.get("streams") or [{}])[0]
        time_base = Fraction(stream.get("time_base") or "1/1000")
        frames = run_tool("ffprobe",
            ["-v", "error", "-select_streams", "v:0", "-show_entries",
             "frame=best_effort_timestamp", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
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
        target.write_text(json.dumps(info))
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
    info = video_info(path)
    if container == "mp4" and path.suffix.lower() in _PLAYABLE_CONTAINERS and info.get("codec") == "h264":
        return path
    if container == "webm" and path.suffix.lower() == ".webm":
        return path
    if not has_ffmpeg():
        return None
    target = cache_dir() / f"{_key(path, 'proxy2-' + container)}.{container}"
    if target.exists():
        return target
    with _lock_for(str(target)):
        if target.exists():
            return target
        tmp = target.with_suffix(f".tmp.{container}")
        if container == "webm":
            codec = ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "32", "-b:v", "0",
                     "-row-mt", "1", "-c:a", "libopus"]
        else:
            codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
                     "-movflags", "+faststart"]
        # passthrough keeps every frame and its timestamp: no frames dropped or duplicated.
        result = run_tool("ffmpeg",
            ["-v", "error", "-y", "-i", str(path), "-map", "0:v:0", "-map", "0:a?",
             "-fps_mode", "passthrough", *codec, str(tmp)], capture_output=True)
        if result.returncode != 0:
            tmp.unlink(missing_ok=True)
            return None
        tmp.replace(target)
    return target
