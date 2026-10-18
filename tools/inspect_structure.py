"""Print the structure of a Timelapse2 .tdb/.ddb without revealing its contents.

The output lists tables, standard columns, column types, row counts, control
type counts and SQLite settings. User-defined labels, data labels, list items,
tooltips and every cell value are replaced by anonymous names (``user_01``)
or omitted, so the output can be shared to help with the format spec without
sharing project data.

The file is opened read-only and never modified.

Usage:
    python tools/inspect_structure.py path/to/file.ddb
"""

from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

# Column names Timelapse2 defines itself. Anything else in a data or template
# table was named by the user and is anonymised.
STANDARD_COLUMNS = {
    "Id", "File", "RelativePath", "DateTime", "DeleteFlag", "FolderDataPath",
    "ControlOrder", "SpreadsheetOrder", "Type", "DefaultValue", "Label",
    "DataLabel", "Tooltip", "Visible", "List", "ExportToCSV", "TXTBOXWIDTH",
    "Copyable", "Level", "Alias", "Guid", "Log", "RootFolder", "Row",
    "VersionCompatabily", "BackwardsCompatibility", "Standard", "SortTerms",
    "QuickPasteTerms", "SearchTerms", "BBDisplayThreshold", "name", "seq",
}

# Tables whose names Timelapse2 defines. Others (e.g. per-level folder data
# tables) are anonymised.
STANDARD_TABLES = {
    "TemplateTable", "TemplateInfo", "FolderDataTemplateTable", "FolderDataInfo",
    "DataTable", "ImageSetTable", "MarkersTable", "Info", "DetectionCategories",
    "ClassificationCategories", "Images", "Detections", "DetectionsVideo",
    "Classifications", "sqlite_sequence",
}


class Anonymiser:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.names: dict[str, str] = {}

    def __call__(self, name: str) -> str:
        if name not in self.names:
            self.names[name] = f"{self.prefix}_{len(self.names) + 1:02d}"
        return self.names[name]


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def main(path: Path) -> None:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    columns_anon = Anonymiser("user_col")
    tables_anon = Anonymiser("user_table")

    def show_column(name: str) -> str:
        return name if name in STANDARD_COLUMNS else columns_anon(name)

    def show_table(name: str) -> str:
        return name if name in STANDARD_TABLES else tables_anon(name)

    print(f"file: {path.suffix} ({path.stat().st_size} bytes)")
    for pragma in ("journal_mode", "page_size", "encoding", "user_version", "auto_vacuum"):
        print(f"pragma {pragma}: {conn.execute(f'PRAGMA {pragma}').fetchone()[0]}")

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()[0]
        print(f"\ntable {show_table(table)}: {count} rows")
        for _, name, col_type, notnull, default, pk in conn.execute(
                f"PRAGMA table_info({quote(table)})"):
            # Defaults on user columns can hold user values; show only whether one exists.
            shown_default = default if name in STANDARD_COLUMNS else ("<set>" if default is not None else None)
            print(f"  {show_column(name)}: type={col_type or '-'} notnull={notnull} "
                  f"pk={pk} default={shown_default}")

    indexes = conn.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL").fetchall()
    if indexes:
        print("\nindexes:")
        for name, table in indexes:
            cols = [show_column(r[2]) for r in conn.execute(f"PRAGMA index_info({quote(name)})")]
            print(f"  on {show_table(table)}({', '.join(cols)})")

    for template in ("TemplateTable", "FolderDataTemplateTable"):
        if template in tables:
            rows = conn.execute(
                f"SELECT Type, Visible, COUNT(*) FROM {template} GROUP BY Type, Visible").fetchall()
            print(f"\n{template} control types (type, visible, count):")
            for row in rows:
                print(f"  {row}")

    for info in ("TemplateInfo", "ImageSetTable"):
        if info in tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({info})")]
            for col in ("VersionCompatabily", "BackwardsCompatibility"):
                if col in cols:
                    value = conn.execute(f"SELECT {col} FROM {info} LIMIT 1").fetchone()
                    print(f"{info}.{col}: {value[0] if value else None}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
