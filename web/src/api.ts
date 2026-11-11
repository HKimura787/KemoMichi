import type { FileDetail, Filter, Info, Project, ReviewPosition, RestEvent, Row, TemplateConfirmation, TemplateDraft, TemplatePreview, VideoInfo } from "./types";

export interface EventResult {
  event: RestEvent | null;
  open: RestEvent[];
  rows: Row[];
  duplicates: Record<string, number>;
  warning: string | null;
}

export class ApiError extends Error {
  constructor(public key: string, public params: Record<string, unknown> = {}, public status = 0) {
    super(key);
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let payload: any = {};
    try {
      payload = await response.json();
    } catch {
      /* not JSON */
    }
    const detail = payload.detail && typeof payload.detail === "object" ? payload.detail : payload;
    throw new ApiError(detail.error || "error.unexpected", detail.params || {}, response.status);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

const q = (filter: Filter) => encodeURIComponent(JSON.stringify(filter));

export const api = {
  info: () => request<Info>("GET", "/api/info"),
  browse: (path: string) =>
    request<{ path: string; parent: string | null; dirs: { name: string; path: string }[];
      files: { name: string; path: string; kind: string }[];
      selected: { name: string; path: string; kind: string } | null }>("GET", `/api/browse?path=${encodeURIComponent(path)}`),
  project: () => request<Project>("GET", "/api/project"),
  saveReviewPosition: async (expectedPath: string, position: ReviewPosition, keepalive = false) => {
    const response = await fetch("/api/review-position", { method: "PUT", keepalive,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expectedPath, ...position }) });
    if (!response.ok) throw new ApiError("error.unexpected", {}, response.status);
  },
  open: (path: string, readOnly = false) => request<Project>("POST", "/api/project/open", { path, readOnly }),
  close: () => request("POST", "/api/project/close"),
  template: (path: string, folder: string) =>
    request<TemplatePreview>("GET", `/api/template?${new URLSearchParams({ path, folder })}`),
  validateTemplate: (folder: string, template: string, draft: TemplateDraft) =>
    request<TemplateConfirmation>("POST", "/api/template/validate", { folder, template, draft }),
  create: (folder: string, template: string | null, demo = false, draft?: TemplateDraft) =>
    request<{ id: string }>("POST", "/api/project/create", { folder, template, demo, draft }),
  job: (id: string) => request<{ status: string; done: number; total: number; error: any; result: any }>(
    "GET", `/api/jobs/${id}`),
  ids: (filter: Filter, records = false) => request<number[]>("GET", `/api/files/ids?filter=${q(filter)}&records=${records}`),
  files: (filter: Filter, offset: number, limit: number) =>
    request<{ total: number; rows: Row[] }>("GET", `/api/files?filter=${q(filter)}&offset=${offset}&limit=${limit}`),
  rowsByIds: (ids: number[]) =>
    request<{ total: number; rows: Row[] }>("GET", `/api/files?filter=${q({ ids } as any)}&limit=${ids.length}`),
  file: (id: number) => request<FileDetail>("GET", `/api/files/${id}`),
  update: (ids: number[], values: Record<string, unknown>) =>
    request<{ changed: number; rows: Row[]; canUndo: boolean; canRedo: boolean }>("PATCH", "/api/files", { ids, values }),
  undo: () => request<{ fileIds: number[]; rows: Row[]; canUndo: boolean; canRedo: boolean }>("POST", "/api/undo"),
  redo: () => request<{ fileIds: number[]; rows: Row[]; canUndo: boolean; canRedo: boolean }>("POST", "/api/redo"),
  setSetting: (key: string, value: unknown) =>
    request<{ settings: Project["settings"]; lockedColumns: string[] }>("PUT", `/api/settings/${key}`, { value }),
  folderSettings: (folder: string) =>
    request<{ guides: any; color: any }>("GET", `/api/folder-settings?folder=${encodeURIComponent(folder)}`),
  setFolderSetting: (folder: string, key: string, value: unknown) =>
    request("PUT", "/api/folder-settings", { folder, key, value }),
  paletteSuggest: () => request<Project["settings"]["palette"]>("GET", "/api/palette/suggest"),
  speciesCounters: (flags: string[], labelSuffix: string) =>
    request<Project & { templateUpdated: boolean }>("POST", "/api/template/species-counters", { flags, labelSuffix }),
  importRecognitions: (path: string) => request<{ report: any }>("POST", "/api/recognitions/import", { path }),
  exportCsv: () => request<{ path: string }>("POST", "/api/export/csv", {}),
  saveCapture: (fileId: number, filename: string, image: string) =>
    request<{ path: string; filename: string; relative: string }>("POST", "/api/capture", { fileId, filename, image }),
  videoInfo: (id: number) => request<VideoInfo>("GET", `/api/media/${id}/video-info`),
  duplicateFile: (fileId: number) =>
    request<{ id: number; row: Row; total: number }>("POST", `/api/files/${fileId}/duplicate`),
  openEvents: () => request<RestEvent[]>("GET", "/api/events?open=true"),
  startEvent: (data: { fileId: number; frame: number | null; inside: boolean; species: string; individual?: string }) =>
    request<EventResult>("POST", "/api/events", data),
  endEvent: (id: number, data: { fileId: number; frame: number | null; inside: boolean }) =>
    request<EventResult>("POST", `/api/events/${id}/end`, data),
  changeEvent: (id: number, changes: Record<string, unknown>) => request<EventResult>("PUT", `/api/events/${id}`, changes),
  deleteEvent: (id: number) => request<EventResult>("DELETE", `/api/events/${id}`),
  exportEvents: () => request<{ path: string }>("POST", "/api/export/events"),
  setMarkers: (id: number, dataLabel: string, points: [number, number][]) =>
    request("PUT", `/api/files/${id}/markers`, { dataLabel, points }),
};

// Browsers built without H.264 (some Linux builds) get a VP9/WebM proxy instead.
const canPlayH264 = typeof document !== "undefined" &&
  document.createElement("video").canPlayType('video/mp4; codecs="avc1.42E01E"') !== "";

export const mediaUrl = (id: number, kind: "thumb" | "preview" | "original" | "video", session: string) => {
  const params = new URLSearchParams({ session });
  if (kind === "video" && !canPlayH264) params.set("format", "webm");
  return `/api/media/${id}/${kind}?${params}`;
};
