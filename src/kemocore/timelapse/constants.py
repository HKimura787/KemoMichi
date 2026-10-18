"""Names and values fixed by the Timelapse2 file format (spec §0-§2)."""

from __future__ import annotations

# Tables
TEMPLATE_TABLE = "TemplateTable"
TEMPLATE_INFO = "TemplateInfo"
FOLDER_DATA_TEMPLATE = "FolderDataTemplateTable"
FOLDER_DATA_INFO = "FolderDataInfo"
DATA_TABLE = "DataTable"
IMAGE_SET_TABLE = "ImageSetTable"
MARKERS_TABLE = "MarkersTable"
INFO_TABLE = "Info"
DETECTION_CATEGORIES = "DetectionCategories"
CLASSIFICATION_CATEGORIES = "ClassificationCategories"
DETECTIONS = "Detections"
DETECTIONS_VIDEO = "DetectionsVideo"

# Standard data labels
FILE = "File"
RELATIVE_PATH = "RelativePath"
DATE_TIME = "DateTime"
DELETE_FLAG = "DeleteFlag"
STANDARD_TYPES = (FILE, RELATIVE_PATH, DATE_TIME, DELETE_FLAG)

# User control types
COUNTER = "Counter"
FIXED_CHOICE = "FixedChoice"
MULTI_CHOICE = "MultiChoice"
FLAG = "Flag"
NOTE = "Note"
MULTI_LINE = "MultiLine"
ALPHA_NUMERIC = "AlphaNumeric"
INTEGER_ANY = "IntegerAny"
INTEGER_POSITIVE = "IntegerPositive"
DECIMAL_ANY = "DecimalAny"
DECIMAL_POSITIVE = "DecimalPositive"
DATE_TIME_CUSTOM = "DateTime_"
DATE_CUSTOM = "Date_"
TIME_CUSTOM = "Time_"

USER_TYPES = (
    COUNTER, INTEGER_ANY, INTEGER_POSITIVE, DECIMAL_ANY, DECIMAL_POSITIVE, NOTE, MULTI_LINE,
    ALPHA_NUMERIC, FIXED_CHOICE, MULTI_CHOICE, FLAG, DATE_TIME_CUSTOM, DATE_CUSTOM, TIME_CUSTOM,
)
ALL_TYPES = STANDARD_TYPES + USER_TYPES
NUMBER_TYPES = (INTEGER_ANY, INTEGER_POSITIVE, DECIMAL_ANY, DECIMAL_POSITIVE)

# Legacy data label treated as DeleteFlag.
LEGACY_DELETE_FLAG = "MarkForDeletion"

TRUE = "true"
FALSE = "false"

DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M:%S"

# Versions (spec §5). KemoMichi writes these into files it creates and never
# raises them in files it edits.
CREATED_VERSION = "2.5.2.0"
BACKWARDS_COMPATIBLE = "2.3.3.0"
MINIMUM_VERSION = "2.3.0.0"
# Newest BackwardsCompatibility value KemoMichi knows how to write safely.
NEWEST_UNDERSTOOD_BACKWARDS = "2.5.2.0"

DEFAULT_DDB_NAME = "TimelapseData.ddb"
DEFAULT_TDB_NAME = "TimelapseTemplate.tdb"
BACKUP_FOLDER = "Backups"
DELETED_FILES_FOLDER = "DeletedFiles"
SKIPPED_FOLDERS = {BACKUP_FOLDER, DELETED_FILES_FOLDER, ".vthumb"}

IMAGE_EXTENSIONS = {".jpg", ".jpeg"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".asf"}

# Defaults for a newly added user control: (data label prefix, default value, width, copyable).
NEW_CONTROL_DEFAULTS = {
    COUNTER: ("Counter", "0", "30", False),
    INTEGER_ANY: ("Integer", "0", "60", True),
    INTEGER_POSITIVE: ("IntegerPositive", "0", "60", True),
    DECIMAL_ANY: ("Decimal", "0", "60", True),
    DECIMAL_POSITIVE: ("DecimalPositive", "0", "60", True),
    NOTE: ("Note", "", "100", True),
    MULTI_LINE: ("MultiLine", "", "100", True),
    ALPHA_NUMERIC: ("AlphaNumeric", "", "100", True),
    FIXED_CHOICE: ("Choice", "", "100", True),
    MULTI_CHOICE: ("MultiChoice", "", "100", True),
    FLAG: ("Flag", FALSE, "20", True),
    DATE_TIME_CUSTOM: ("DateTime_", None, "160", True),  # None: <year>-01-01 12:00:00
    DATE_CUSTOM: ("Date_", None, "120", True),           # None: <year>-01-01
    TIME_CUSTOM: ("Time_", "12:00:00", "95", True),
}

STANDARD_TOOLTIPS = {
    FILE: "The file name",
    RELATIVE_PATH: "Path from the root folder containing the template and image data files to the file",
    DATE_TIME: "Date and time taken (Time_ in 24 hour format)",
    DELETE_FLAG: "Mark a file as one to be deleted. You can then confirm deletion through the Edit Menu",
}

# Words a DataLabel may not equal (case-insensitive); the template editor appends "_".
RESERVED_DATA_LABELS = {
    "abort", "action", "add", "after", "all", "alter", "analyze", "and", "as", "asc", "attach",
    "autoincrement", "before", "begin", "between", "by", "cascade", "case", "cast", "check",
    "collate", "column", "commit", "conflict", "constraint", "create", "cross", "current_date",
    "current_time", "current_timestamp", "database", "date", "datetime", "default", "deferrable",
    "deferred", "delete", "desc", "detach", "distinct", "drop", "each", "else", "end", "escape",
    "except", "exclusive", "exists", "explain", "fail", "for", "foreign", "from", "full", "glob",
    "group", "having", "id", "if", "ignore", "immediate", "in", "index", "indexed", "initially",
    "inner", "insert", "instead", "intersect", "into", "is", "isnull", "join", "key", "left",
    "like", "limit", "match", "natural", "no", "not", "notnull", "null", "of", "offset", "on",
    "or", "order", "outer", "plan", "pragma", "primary", "query", "raise", "recursive",
    "references", "regexp", "reindex", "release", "rename", "replace", "restrict", "right",
    "rollback", "row", "savepoint", "select", "set", "table", "temp", "temporary", "then", "time",
    "to", "transaction", "trigger", "union", "unique", "update", "using", "vacuum", "values",
    "view", "virtual", "when", "where", "with", "without",
}
