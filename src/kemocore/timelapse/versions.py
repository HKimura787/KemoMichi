"""Compare Timelapse version strings like '2.5.2.0'."""

from __future__ import annotations


def _parts(version: str) -> tuple[int, ...] | None:
    try:
        parts = tuple(int(p) for p in version.strip().split("."))
    except (AttributeError, ValueError):
        return None
    return parts + (0,) * (4 - len(parts)) if 2 <= len(parts) <= 4 else None


def compare_versions(a: str, b: str) -> int:
    """-1, 0 or 1. An unreadable version compares as older than anything."""
    pa, pb = _parts(a), _parts(b)
    if pa is None and pb is None:
        return 0
    if pa is None:
        return -1
    if pb is None:
        return 1
    return (pa > pb) - (pa < pb)
