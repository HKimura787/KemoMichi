"""Template controls: parsing, choice lists and value validation (spec §1, §2.5)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from . import constants as C


def parse_bool(value: str | None) -> bool:
    """Timelapse reads booleans case-insensitively; anything but 'true' is false."""
    return (value or "").strip().lower() == C.TRUE


def format_bool(value: bool) -> str:
    return C.TRUE if value else C.FALSE


@dataclass
class Choices:
    include_empty: bool = True
    items: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, raw: str | None) -> "Choices":
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
            items = [str(i).strip() for i in data.get("ChoiceListNonEmpty") or []]
            seen: list[str] = []
            for item in items:
                if item and item not in seen:
                    seen.append(item)
            include_empty = bool(data.get("IncludeEmptyChoice", True)) or not seen
            return cls(include_empty, seen)
        except (ValueError, AttributeError, TypeError):
            return cls()

    def serialize(self) -> str:
        """Same shape and key order Timelapse writes; '' when there are no choices."""
        if not self.items:
            return ""
        return json.dumps(
            {"IncludeEmptyChoice": self.include_empty, "ChoiceListNonEmpty": self.items},
            ensure_ascii=False, separators=(",", ":"),
        )


@dataclass
class Control:
    id: int
    control_order: int
    spreadsheet_order: int
    type: str
    default_value: str
    label: str
    data_label: str
    tooltip: str
    visible: bool
    list_raw: str
    export_to_csv: bool
    width: str
    copyable: bool

    @property
    def choices(self) -> Choices:
        return Choices.parse(self.list_raw)

    @property
    def is_standard(self) -> bool:
        return self.type in C.STANDARD_TYPES

    def to_dict(self) -> dict:
        choices = self.choices
        return {
            "id": self.id,
            "controlOrder": self.control_order,
            "spreadsheetOrder": self.spreadsheet_order,
            "type": self.type,
            "defaultValue": self.default_value,
            "label": self.label,
            "dataLabel": self.data_label,
            "tooltip": self.tooltip,
            "visible": self.visible,
            "choices": choices.items,
            "includeEmptyChoice": choices.include_empty,
            "exportToCsv": self.export_to_csv,
            "width": self.width,
            "copyable": self.copyable,
            "standard": self.is_standard,
        }


def control_from_row(row: dict) -> Control:
    def text(key: str) -> str:
        value = row.get(key)
        return "" if value is None else str(value)

    def number(key: str) -> int:
        try:
            return int(row.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    control_type = text("Type")
    data_label = text("DataLabel")
    if data_label == C.LEGACY_DELETE_FLAG:
        control_type = C.DELETE_FLAG
    return Control(
        id=number("Id"),
        control_order=number("ControlOrder"),
        spreadsheet_order=number("SpreadsheetOrder"),
        type=control_type,
        default_value=text("DefaultValue"),
        label=text("Label"),
        data_label=data_label,
        tooltip=text("Tooltip"),
        visible=parse_bool(text("Visible")) if "Visible" in row else True,
        list_raw=text("List"),
        export_to_csv=parse_bool(text("ExportToCSV")) if row.get("ExportToCSV") is not None else True,
        width=text("TXTBOXWIDTH"),
        copyable=parse_bool(text("Copyable")),
    )


class ValueError_(ValueError):
    """A value that the control type does not accept. Message is a message key + params."""

    def __init__(self, key: str, **params):
        super().__init__(key)
        self.key = key
        self.params = params


_INT_RE = re.compile(r"^[+-]?\d+$")
_DEC_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_ALNUM_RE = re.compile(r"^[A-Za-z0-9_-]*$")


def normalize_value(control: Control, value) -> str:
    """Validate a value for a control and return the exact string Timelapse would store."""
    t = control.type
    if value is None:
        value = ""
    if isinstance(value, bool):
        value = format_bool(value)
    value = str(value)

    if t in (C.FLAG, C.DELETE_FLAG):
        lowered = value.strip().lower()
        if lowered not in (C.TRUE, C.FALSE):
            raise ValueError_("error.flag")
        return lowered
    if t in (C.COUNTER, C.INTEGER_ANY, C.INTEGER_POSITIVE):
        value = value.strip()
        if value == "":
            return ""
        if not _INT_RE.match(value):
            raise ValueError_("error.integer")
        number = int(value)
        if t != C.INTEGER_ANY and number < 0:
            raise ValueError_("error.positive")
        return str(number)
    if t in (C.DECIMAL_ANY, C.DECIMAL_POSITIVE):
        value = value.strip()
        if value == "":
            return ""
        if not _DEC_RE.match(value):
            raise ValueError_("error.decimal")
        if t == C.DECIMAL_POSITIVE and float(value) < 0:
            raise ValueError_("error.positive")
        return value
    if t == C.ALPHA_NUMERIC:
        if not _ALNUM_RE.match(value):
            raise ValueError_("error.alphanumeric")
        return value
    if t == C.FIXED_CHOICE:
        choices = control.choices
        if value == "" or value in choices.items:
            return value
        raise ValueError_("error.choice", value=value)
    if t == C.MULTI_CHOICE:
        items = [i for i in value.split(",") if i != ""]
        allowed = control.choices.items
        bad = [i for i in items if i not in allowed]
        if bad:
            raise ValueError_("error.choice", value=bad[0])
        # Keep the menu order so the stored text is stable.
        return ",".join(i for i in allowed if i in items)
    if t in (C.DATE_TIME, C.DATE_TIME_CUSTOM):
        return _check_datetime(value, C.DATE_TIME_FORMAT, "error.datetime")
    if t == C.DATE_CUSTOM:
        return _check_datetime(value, C.DATE_FORMAT, "error.date")
    if t == C.TIME_CUSTOM:
        return _check_datetime(value, C.TIME_FORMAT, "error.time")
    # File, RelativePath, Note, MultiLine
    return value


def _check_datetime(value: str, fmt: str, key: str) -> str:
    value = value.strip()
    for candidate in (value, value.replace("T", " ")):
        try:
            return datetime.strptime(candidate, fmt).strftime(fmt)
        except ValueError:
            continue
    raise ValueError_(key)


def default_for_new_control(control_type: str, year: int) -> str:
    prefix, default, _width, _copyable = C.NEW_CONTROL_DEFAULTS[control_type]
    if default is not None:
        return default
    if control_type == C.DATE_TIME_CUSTOM:
        return f"{year}-01-01 12:00:00"
    return f"{year}-01-01"


def valid_data_label(label: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_]*$", label)) and label.lower() not in C.RESERVED_DATA_LABELS


def make_data_label(base: str, taken: set[str]) -> str:
    """Turn any text into a DataLabel the template editor would accept, unique among `taken`."""
    label = re.sub(r"[^A-Za-z0-9_]", "X", base) or "X"
    if not label[0].isalpha():
        label = "X" + label[1:]
    if label.lower() in C.RESERVED_DATA_LABELS:
        label += "_"
    candidate, n = label, 0
    while candidate in taken:
        candidate = f"{label}{n}"
        n += 1
    return candidate
