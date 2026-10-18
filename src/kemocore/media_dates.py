"""When a photo or video was taken, read the way Timelapse2 reads it (spec §2.5)."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PIL import Image

_DATETIME_ORIGINAL = 0x9003
_EXIF_IFD = 0x8769


def exif_datetime(path: Path) -> datetime | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL) or exif.get(0x0132)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip().rstrip("\x00"), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def file_datetime(path: Path) -> datetime:
    """EXIF DateTimeOriginal for images, else the earlier of the file's creation and modification times."""
    path = Path(path)
    if path.suffix.lower() in (".jpg", ".jpeg"):
        taken = exif_datetime(path)
        if taken and 1900 <= taken.year <= 2100:
            return taken
    stat = os.stat(path)
    created = getattr(stat, "st_birthtime", None) or stat.st_ctime
    stamp = min(created, stat.st_mtime)
    return datetime.fromtimestamp(stamp).replace(microsecond=0)
