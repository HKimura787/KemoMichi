"""Review a template and write an independent confirmed copy for a new project."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from . import constants as C
from . import schema as S
from .project import ProjectError
from .template import Choices, Control, ValueError_, control_from_row, normalize_value, valid_data_label
from .versions import compare_versions


@dataclass
class TemplateDocument:
    controls: list[Control]
    revision: str


def _revision(conn: sqlite3.Connection) -> str:
    # Include folder metadata and changes held in WAL, not just bytes in the main SQLite file.
    return hashlib.sha256("\n".join(conn.iterdump()).encode("utf-8")).hexdigest()


def read_template(path: Path) -> TemplateDocument:
    if not path.is_file():
        raise ProjectError("error.notFound", path=str(path))
    if path.suffix.lower() != ".tdb":
        raise ValueError_("error.notTdb")
    try:
        with closing(sqlite3.connect(S.sqlite_uri(path), uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError_("error.notTdb")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if C.TEMPLATE_TABLE not in tables or C.DATA_TABLE in tables:
                raise ValueError_("error.notTdb")
            controls = [control_from_row(dict(row)) for row in conn.execute(
                f"SELECT * FROM {C.TEMPLATE_TABLE} ORDER BY ControlOrder, Id")]
            if C.TEMPLATE_INFO in tables:
                metadata = conn.execute(f"SELECT * FROM {C.TEMPLATE_INFO} LIMIT 1").fetchone()
                backwards = dict(metadata).get("BackwardsCompatibility") if metadata else None
                if backwards and compare_versions(backwards, C.NEWEST_UNDERSTOOD_BACKWARDS) > 0:
                    raise ValueError_("error.templateNewer")
            unknown = {control.type for control in controls} - set(C.ALL_TYPES)
            if unknown:
                raise ValueError_("error.unknownType", types=", ".join(sorted(unknown)))
            standards = [control for control in controls if control.is_standard]
            if len(standards) != len(C.STANDARD_TYPES) or {control.type for control in standards} != set(C.STANDARD_TYPES):
                raise ValueError_("error.templateStandard")
            if any(control.data_label != control.type for control in standards):
                raise ValueError_("error.templateStandard")
            return TemplateDocument(controls, _revision(conn))
    except sqlite3.DatabaseError as exc:
        raise ValueError_("error.notTdb") from exc


def validate_controls(items: list[dict], original: TemplateDocument) -> list[Control]:
    standards = {control.id: control for control in original.controls if control.is_standard}
    seen_standards: set[int] = set()
    taken: set[str] = set()
    controls = []
    for index, item in enumerate(items):
        field = item["label"].strip()
        data_label = item["dataLabel"].strip()
        ctype = item["type"]
        standard = standards.get(item["id"])
        if standard:
            if standard.id in seen_standards or (ctype, data_label, item["defaultValue"]) != (
                standard.type, standard.data_label, standard.default_value,
            ):
                raise ValueError_("error.templateStandard", field=field)
            seen_standards.add(standard.id)
        elif ctype not in C.USER_TYPES:
            raise ValueError_("error.unknownType", types=ctype, field=field)
        if not field:
            raise ValueError_("error.templateLabel", field=data_label)
        if not standard and not valid_data_label(data_label):
            raise ValueError_("error.templateDataLabel", field=field)
        if data_label.lower() in taken:
            raise ValueError_("error.duplicateField", field=data_label)
        taken.add(data_label.lower())
        choices = [choice.strip() for choice in item["choices"]] if ctype in (C.FIXED_CHOICE, C.MULTI_CHOICE) else []
        if any(not choice for choice in choices) or len(set(choices)) != len(choices):
            raise ValueError_("error.templateChoices", field=field)
        if ctype == C.MULTI_CHOICE and any("," in choice for choice in choices):
            raise ValueError_("error.templateChoiceComma", field=field)
        width = item["width"].strip()
        if not width.isascii() or not width.isdigit() or int(width) < 1:
            raise ValueError_("error.templateWidth", field=field)
        control = Control(
            id=item["id"], control_order=index, spreadsheet_order=index + 1,
            type=ctype, default_value=item["defaultValue"], label=field, data_label=data_label,
            tooltip=item["tooltip"], visible=item["visible"],
            list_raw=Choices(item["includeEmptyChoice"], choices).serialize()
            if ctype in (C.FIXED_CHOICE, C.MULTI_CHOICE) else "",
            export_to_csv=item["exportToCsv"], width=width, copyable=item["copyable"],
        )
        try:
            control.default_value = normalize_value(control, control.default_value)
            if ctype == C.FIXED_CHOICE and not item["includeEmptyChoice"] and not control.default_value:
                raise ValueError_("error.choice", value="")
        except ValueError_ as exc:
            exc.params["field"] = field
            raise
        controls.append(control)
    if seen_standards != set(standards):
        raise ValueError_("error.templateStandard")
    return controls


def project_name(name: str) -> str:
    name = name.strip()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)}
    if (not name or name.endswith((".", " ")) or name.lower().endswith((".tdb", ".ddb"))
            or len(name.encode("utf-8")) > 240
            or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name)
            or name.split(".")[0].upper() in reserved):
        raise ValueError_("error.templateName")
    return name


def suggest_name(root: Path, stem: str) -> str:
    candidate = stem
    number = 0
    while any((root / f"{candidate}{suffix}").exists() for suffix in (".tdb", ".ddb")):
        number += 1
        candidate = f"{stem}_project" + (str(number) if number > 1 else "")
    return candidate


def write_template_copy(source: Path, target: Path, controls: list[Control], revision: str) -> None:
    """Preserve the source's other tables/metadata; never overwrite an existing template."""
    created = False
    try:
        with closing(sqlite3.connect(S.sqlite_uri(source), uri=True)) as src:
            src.execute("BEGIN")
            if _revision(src) != revision:
                raise ValueError_("error.templateChanged")
            try:
                with target.open("xb"):
                    created = True
            except FileExistsError as exc:
                raise ValueError_("error.templateExists", path=str(target)) from exc
            with closing(sqlite3.connect(target)) as dest:
                src.backup(dest)
                with dest:
                    dest.execute(f"DELETE FROM {C.TEMPLATE_TABLE}")
                    for control in controls:
                        dest.execute(S.INSERT_TEMPLATE_ROW, S.template_row_values(control))
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise
