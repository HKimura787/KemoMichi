"""Fields KemoMichi can add to an open project in one step: a species, the stay-event columns."""

from __future__ import annotations

import re

from . import constants as C
from .template import valid_data_label

# Event setting key -> (control type, data label, English label). Same shape as the demo project.
EVENT_FIELDS = {
    "speciesName": (C.NOTE, "SpeciesName", "Species"),
    "individual": (C.NOTE, "Individual", "Individual"),
    "startInside": (C.FLAG, "InsideAtStart", "Inside at start"),
    "entry": (C.DECIMAL_POSITIVE, "EntrySec", "Entry (s)"),
    "duration": (C.DECIMAL_POSITIVE, "StayDuration", "Stay (s)"),
    "exitFile": (C.NOTE, "ExitFile", "Exit file"),
    "exit": (C.DECIMAL_POSITIVE, "ExitSec", "Exit (s)"),
    "endInside": (C.FLAG, "InsideAtEnd", "Inside at end"),
}


def _free(label: str, taken: set[str]) -> bool:
    return label.lower() not in taken


def unique_label(base: str, taken: set[str]) -> str:
    """`base`, or `base2`, `base3`… — the first one no field uses (case does not count)."""
    lowered = {t.lower() for t in taken}
    candidate, n = base, 1
    while not _free(candidate, lowered):
        n += 1
        candidate = f"{base}{n}"
    return candidate


def species_labels(name: str, taken: set[str], counter: bool) -> tuple[str, str | None]:
    """Column names for a new species: (flag, counter or None).

    A name in plain letters keeps its letters ("Red fox" -> RedFox). Any other name (Japanese…)
    cannot be a column name, so it gets Species1, Species2… and stays readable as the label.
    """
    lowered = {t.lower() for t in taken}
    words = re.findall(r"[A-Za-z0-9_]+", name) if name.isascii() else []
    base = "".join(w[:1].upper() + w[1:] for w in words) if len(words) > 1 else "".join(words)
    if valid_data_label(base):
        n, flag = 1, base
        while not _free(flag, lowered) or (counter and not _free(f"{flag}Count", lowered)):
            n += 1
            flag = f"{base}{n}"
    else:
        n = 1
        while not _free(f"Species{n}", lowered) or (counter and not _free(f"Species{n}Count", lowered)):
            n += 1
        flag = f"Species{n}"
    return flag, (f"{flag}Count" if counter else None)


def free_key(palette_items: list[dict]) -> str:
    """The first number key no species uses yet ("" when all ten are taken)."""
    used = {item.get("key") for item in palette_items}
    return next((k for k in "1234567890" if k not in used), "")
