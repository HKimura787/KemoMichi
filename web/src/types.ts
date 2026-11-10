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

export interface EventColumns {
  entry: string | null;
  exit: string | null;
  exitFile: string | null;
  startInside: string | null;
  endInside: string | null;
  duration: string | null;
  writeSpecies: boolean;
  continuityGap: number;
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
  settings: { palette?: Palette; bboxThreshold?: number; [key: string]: unknown };
  lockedColumns: string[];
  eventColumns: EventColumns;
  duplicates: Record<string, number>;
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

/** One animal's stay in the focal area, entry to exit, possibly across several files. */
export interface RestEvent {
  id: number;
  species: string;
  individual: string;
  note: string;
  start_file_id: number;
  start_frame: number | null;
  start_inside: boolean;
  end_file_id: number | null;
  end_frame: number | null;
  end_inside: boolean;
  open: boolean;
  startFile: string;
  startFolder: string;
  startDateTime: string;
  endFile: string;
  endFolder: string;
  endDateTime: string;
  entrySeconds: string | null;
  exitSeconds: string | null;
  sameFile: boolean;
  durationSeconds: string | null;
  elapsedSeconds: string | null;
}

export interface FileDetail extends Row {
  detections: Detection[];
  markers: Record<string, [number, number][]>;
  events: RestEvent[];
  sameFileRows: number[];
  duplicateOf: number | null;
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
