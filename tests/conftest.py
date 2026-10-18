import os
import shutil
from pathlib import Path

import pytest

from kemocore.demo import create_demo_project

_TEMPLATE_CACHE: dict[str, Path] = {}


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("KEMOMICHI_CACHE", str(tmp_path_factory.getbasetemp() / "cache"))


@pytest.fixture
def demo(tmp_path_factory, tmp_path) -> Path:
    """A fresh copy of the demo project; the media is generated once per test session."""
    if "demo" not in _TEMPLATE_CACHE:
        base = tmp_path_factory.mktemp("demo-source") / "project"
        create_demo_project(base)
        _TEMPLATE_CACHE["demo"] = base
    target = tmp_path / "project"
    shutil.copytree(_TEMPLATE_CACHE["demo"], target)
    return target / "TimelapseData.ddb"


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


needs_ffmpeg = pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not installed")
os.environ.setdefault("TZ", "UTC")
