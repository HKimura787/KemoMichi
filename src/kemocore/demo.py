"""Dummy camera-trap media and a demo project, for tests, fixtures and trying the app.

Nothing here is real survey data: images are flat colours with a label, species are fictional.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from .timelapse import constants as C
from .timelapse.create import create_data_file, create_template
from .timelapse.template import Choices, Control

DEMO_SPECIES = ["SpeciesA", "SpeciesB", "SpeciesC", "SpeciesD"]


def make_image(path: Path, taken: datetime | None, text: str, colour=(90, 110, 80), size=(640, 480)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, colour)
    draw = ImageDraw.Draw(img)
    draw.rectangle([size[0] * 0.4, size[1] * 0.45, size[0] * 0.6, size[1] * 0.75], fill=(60, 50, 40))
    draw.text((16, 16), text, fill=(255, 255, 255))
    exif = Image.Exif()
    if taken is not None:
        exif.get_ifd(0x8769)[0x9003] = taken.strftime("%Y:%m:%d %H:%M:%S")
        exif[0x0132] = taken.strftime("%Y:%m:%d %H:%M:%S")
    img.save(path, "JPEG", quality=85, exif=exif)


def make_video(path: Path, seconds: int = 3, rate: str = "30000/1001", codec: str = "libx264") -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate={rate}",
            "-t", str(seconds), "-c:v", codec]
    if codec == "libx264":
        args += ["-pix_fmt", "yuv420p"]
    result = subprocess.run(args + [str(path)], capture_output=True)
    return result.returncode == 0


def make_demo_media(root: Path) -> int:
    """Two cameras, a burst sequence, night-like images and two short videos."""
    start = datetime(2026, 4, 1, 5, 30, 0)
    count = 0
    for cam, colour in (("CamA", (90, 110, 80)), ("CamB", (70, 90, 110))):
        for i in range(12):
            taken = start + timedelta(minutes=37 * i, seconds=(i % 3))
            night = taken.hour < 6
            make_image(root / cam / "2026-04" / f"IMG_{i + 1:04d}.JPG", taken,
                       f"{cam} #{i + 1} {taken:%Y-%m-%d %H:%M:%S}",
                       (50, 50, 50) if night else colour)
            count += 1
    make_image(root / "CamA" / "2026-04" / "NOEXIF_0001.JPG", None, "no EXIF")
    count += 1
    if make_video(root / "CamA" / "2026-04" / "VID_0001.MP4"):
        count += 1
    if make_video(root / "CamB" / "2026-04" / "VID_0002.AVI", rate="15", codec="mjpeg"):
        count += 1
    return count


def demo_controls() -> list[Control]:
    def control(ctype, label, data_label, default="", choices: list[str] | None = None, copyable=True, width="100"):
        return Control(id=0, control_order=0, spreadsheet_order=0, type=ctype, default_value=default,
                       label=label, data_label=data_label, tooltip="", visible=True,
                       list_raw=Choices(True, choices).serialize() if choices else "", export_to_csv=True,
                       width=width, copyable=copyable)

    controls = []
    for name in DEMO_SPECIES:
        controls.append(control(C.FLAG, name, name, C.FALSE, width="20"))
    for name in DEMO_SPECIES:
        controls.append(control(C.COUNTER, f"{name} count", f"{name}Count", "0", copyable=False, width="30"))
    controls += [
        control(C.FIXED_CHOICE, "Light", "Light", "", ["Day", "Night", "Twilight"]),
        control(C.MULTI_CHOICE, "Behaviour", "Behaviour", "", ["Walking", "Feeding", "Resting", "Looking"]),
        control(C.NOTE, "Note", "Note"),
        # REST event fields: one row per event (see kemocore.events)
        control(C.FLAG, "Inside at start", "InsideAtStart", C.FALSE, width="20"),
        control(C.DECIMAL_POSITIVE, "Entry (s)", "EntrySec", "", width="60"),
        control(C.NOTE, "Exit file", "ExitFile"),
        control(C.DECIMAL_POSITIVE, "Exit (s)", "ExitSec", "", width="60"),
        control(C.FLAG, "Inside at end", "InsideAtEnd", C.FALSE, width="20"),
        control(C.DECIMAL_POSITIVE, "Stay (s)", "StayDuration", "", width="60"),
        control(C.FLAG, "Unclear", "Unclear", C.FALSE, width="20"),
    ]
    return controls


def create_demo_project(root: Path) -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    make_demo_media(root)
    template = root / C.DEFAULT_TDB_NAME
    create_template(template, demo_controls())
    ddb = root / C.DEFAULT_DDB_NAME
    create_data_file(ddb, template)
    # Ready to try: the species palette and where REST event results go.
    from .sidecar import Sidecar
    sidecar = Sidecar(ddb)
    sidecar.set("palette", {"items": [{"flag": name, "counter": f"{name}Count", "key": str(i + 1)}
                                      for i, name in enumerate(DEMO_SPECIES)], "single": False})
    sidecar.set("eventColumns", {"entry": "EntrySec", "exit": "ExitSec", "exitFile": "ExitFile",
                                 "startInside": "InsideAtStart", "endInside": "InsideAtEnd",
                                 "duration": "StayDuration", "writeSpecies": True})
    sidecar.close()
    return ddb
