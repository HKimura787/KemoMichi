"""CREATE statements and column rules shared by project creation and template updates."""

from __future__ import annotations

from pathlib import Path

from . import constants as C
from .template import Control

DEFAULT_SORT_TERMS = (
    '[ { "DataLabel":"RelativePath", "DisplayLabel":"RelativePath", "ControlType":"RelativePath", '
    '"IsAscending":"true" }, { "DataLabel":"DateTime", "DisplayLabel":"DateTime", '
    '"ControlType":"DateTime", "IsAscending":"true" } ]'
)


def q(name: str) -> str:
    """Quote an identifier for SQLite."""
    return '"' + name.replace('"', '""') + '"'


def lit(value: str) -> str:
    """A string literal, the way Timelapse writes defaults."""
    return "'" + (value or "").replace("'", "''") + "'"


TEMPLATE_TABLE_SQL = (
    f"CREATE TABLE {C.TEMPLATE_TABLE} (Id INTEGER PRIMARY KEY AUTOINCREMENT, ControlOrder INTEGER, "
    "SpreadsheetOrder INTEGER, Type TEXT, DefaultValue TEXT, Label TEXT, DataLabel TEXT, Tooltip TEXT, "
    "Visible TEXT, List TEXT, ExportToCSV TEXT DEFAULT 'True', TXTBOXWIDTH TEXT, Copyable TEXT)"
)
FOLDER_DATA_TEMPLATE_SQL = (
    f"CREATE TABLE {C.FOLDER_DATA_TEMPLATE} (Id INTEGER PRIMARY KEY AUTOINCREMENT, ControlOrder INTEGER, "
    "SpreadsheetOrder INTEGER, Level INTEGER, Type TEXT, DefaultValue TEXT, Label TEXT, DataLabel TEXT, "
    "Tooltip TEXT, Visible TEXT, List TEXT, ExportToCSV TEXT DEFAULT 'True')"
)
FOLDER_DATA_INFO_SQL = (
    f"CREATE TABLE {C.FOLDER_DATA_INFO} (Id INTEGER PRIMARY KEY AUTOINCREMENT, Level INTEGER, "
    "Guid TEXT, Alias TEXT)"
)
TEMPLATE_INFO_SQL = (
    f"CREATE TABLE {C.TEMPLATE_INFO} (VersionCompatabily TEXT DEFAULT '', "
    "BackwardsCompatibility TEXT DEFAULT '', Standard TEXT DEFAULT '')"
)
IMAGE_SET_SQL = (
    f"CREATE TABLE {C.IMAGE_SET_TABLE} (Id INTEGER PRIMARY KEY AUTOINCREMENT, RootFolder TEXT DEFAULT '', "
    "Log TEXT DEFAULT '', Row TEXT, VersionCompatabily TEXT, BackwardsCompatibility TEXT, "
    f"SortTerms TEXT DEFAULT {lit(DEFAULT_SORT_TERMS)}, SearchTerms TEXT DEFAULT '{{}}', "
    "QuickPasteTerms TEXT, BBDisplayThreshold REAL DEFAULT '-1', Standard TEXT DEFAULT '')"
)

DATA_TABLE_INDEXES = (
    ("IndexRelativePath", "RelativePath"),
    ("IndexFile", "File"),
    ("IndexRelativePathFile", "RelativePath,File"),
    ("IndexRelativePathDateTimeFile", "RelativePath, DateTime, File"),
    ("IndexDeleteFlag", "DeleteFlag COLLATE NOCASE"),
)


def data_column_sql(control: Control) -> str:
    """Column definition in DataTable for one control (spec §2.2)."""
    name = q(control.data_label)
    if control.type == C.DATE_TIME:
        default = control.default_value
        return f"{name} DATETIME DEFAULT {lit(default)}"
    if control.type in C.NUMBER_TYPES:
        return f"{name} TEXT DEFAULT ''"
    return f"{name} TEXT DEFAULT {lit(control.default_value)}"


def template_row_values(control: Control) -> tuple:
    return (
        control.control_order, control.spreadsheet_order, control.type, control.default_value,
        control.label, control.data_label, control.tooltip,
        C.TRUE if control.visible else C.FALSE, control.list_raw,
        C.TRUE if control.export_to_csv else C.FALSE, control.width,
        C.TRUE if control.copyable else C.FALSE,
    )


INSERT_TEMPLATE_ROW = (
    f"INSERT INTO {C.TEMPLATE_TABLE} (ControlOrder, SpreadsheetOrder, Type, DefaultValue, Label, "
    "DataLabel, Tooltip, Visible, List, ExportToCSV, TXTBOXWIDTH, Copyable) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
)


def sqlite_uri(path, mode: str = "ro") -> str:
    """A SQLite URI that survives Windows drive letters and '#', '?' or '%' in folder names."""
    return f"{Path(path).resolve().as_uri()}?mode={mode}"
