export type ControlType =
  | "File" | "RelativePath" | "DateTime" | "DeleteFlag"
  | "Counter" | "FixedChoice" | "MultiChoice" | "Flag" | "Note" | "MultiLine" | "AlphaNumeric"
  | "IntegerAny" | "IntegerPositive" | "DecimalAny" | "DecimalPositive" | "DateTime_" | "Date_" | "Time_";

export interface Control {
  id: number;
  controlOrder: number;
  spreadsheetOrder: number;
  type: ControlType;
  defaultValue: string;
  label: string;
  dataLabel: string;
  tooltip: string;
  visible: boolean;
  choices: string[];
  includeEmptyChoice: boolean;
  exportToCsv: boolean;
  width: string;
  copyable: boolean;
  standard: boolean;
}

export interface Row {
  id: number;
  values: Record<string, string>;
}

export interface PaletteItem {
  flag: string;
  counter: string | null;
  key: string;
}

export interface Palette {
  items: PaletteItem[];
  single: boolean;
}

export interface RestColumns {
  start: string | null;
  end: string | null;
  duration: string | null;
  multi: "first" | "sum" | "list";
}

export interface ReviewPosition {
  fileId: number;
  frame: number;
  filter: Filter;
  view: "viewer" | "grid";
}

export interface Project {
  path: string;
  root: string;
  name: string;
  readOnly: boolean;
  readOnlyReason: string;
  version: string;
  standard: string;
  controls: Control[];
  total: number;
  hasRecognitions: boolean;
  settings: { palette?: Palette; restColumns?: RestColumns; bboxThreshold?: number; reviewPosition?: ReviewPosition; [key: string]: unknown };
  lockedColumns: string[];
  categories: { detection: Record<string, string>; classification: Record<string, string> };
  folders: { path: string; count: number }[];
  templatePath: string | null;
  canUndo: boolean;
  canRedo: boolean;
}

export interface Detection {
  id: number;
  category: string;
  conf: number;
  bbox: [number, number, number, number];
  classification: string | null;
  classificationConf: number | null;
  frame: number | null;
  frameRate: number | null;
}

export interface Interval {
  id: number;
  kind: "video" | "sequence";
  file_id: number;
  start_frame: number | null;
  end_frame: number | null;
  start_file_id: number | null;
  end_file_id: number | null;
  start_seconds: string;
  end_seconds: string;
  duration_seconds: string;
  individual: string;
  species: string;
  note: string;
}

export interface FileDetail extends Row {
  detections: Detection[];
  markers: Record<string, [number, number][]>;
  intervals: Interval[];
  fileRest?: { start_seconds: string; end_seconds: string; duration_seconds: string; interval_count: number } | null;
  kind: "image" | "video";
  exists: boolean;
}

export interface VideoInfo {
  available: boolean;
  codec?: string;
  width?: number;
  height?: number;
  frameRate?: number | null;
  exactTimes?: boolean;
  frameTimes?: number[];
}

export type ShapeKind = "line" | "triangle" | "rect" | "polygon" | "circle";

export interface Guide {
  id: string;
  shape: ShapeKind;
  points: [number, number][];
  name: string;
  color: string;
  width: number;
}

export interface ColorAdjust {
  brightness: number; // 1 = unchanged
  contrast: number;
  saturation: number;
  gamma: number;
  grayscale: boolean;
}

export interface Filter {
  folder?: string;
  deleted?: boolean | null;
  anyTrue?: string[];
  allFalse?: string[];
  text?: string;
  detection?: { category: string; minConf: number } | null;
}

export interface Info {
  version: string;
  serverMode: boolean;
  host: string;
  startFolders: { name: string; path: string }[];
  ffmpeg: boolean;
  projectOpen: boolean;
}
