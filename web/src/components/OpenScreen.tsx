import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import type { Info, Project } from "../types";
import { Dialog, FileBrowser, lastFolder, useToast } from "../ui";

export async function waitForJob(id: string, onProgress: (done: number, total: number) => void) {
  for (;;) {
    const job = await api.job(id);
    onProgress(job.done, job.total);
    if (job.status === "done") return job.result;
    if (job.status === "failed") throw Object.assign(new Error(job.error?.detail), job.error);
    await new Promise((r) => setTimeout(r, 400));
  }
}

export function OpenScreen({ info, onOpened, onCancel }: {
  info: Info; onOpened: (p: Project) => void; onCancel?: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const [selected, setSelected] = useState<{ path: string; kind: string } | null>(null);
  const [ddbPath, setDdbPath] = useState("");
  const [opening, setOpening] = useState(false);
  const operation = useRef(false);
  const [folder, setFolder] = useState<string>("");
  const [creating, setCreating] = useState<string | null>(null);
  const [mode, setMode] = useState<"none" | "template" | "demo">("none");
  const busy = opening || creating !== null;
  const path = ddbPath.trim().replace(/^(['"])(.*)\1$/, "$2");

  useEffect(() => {
    if (!onCancel || busy || mode !== "none") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, busy, mode]);

  const open = async (path: string, readOnly = false) => {
    if (!path || operation.current) return;
    operation.current = true;
    setOpening(true);
    try {
      onOpened(await api.open(path, readOnly));
    } catch (e) {
      toast.error(e);
    } finally {
      operation.current = false;
      setOpening(false);
    }
  };

  const create = async (template: string | null, demo: boolean) => {
    if (operation.current) return;
    operation.current = true;
    setMode("none");
    try {
      setCreating(t("open.creating", { done: 0, total: "…" }));
      const job = await api.create(folder, template, demo);
      await waitForJob(job.id, (done, total) => setCreating(t("open.creating", { done, total: total || "…" })));
      onOpened(await api.project());
    } catch (e: any) {
      toast.push("error", e?.error ? t(e.error, e.params) : t("error.unexpected"));
    } finally {
      operation.current = false;
      setCreating(null);
      setMode("none");
    }
  };

  const start = lastFolder(info.startFolders[0]?.path ?? "/");
  return (
    <main className="open" aria-busy={busy}>
      {onCancel && (
        <button className="btn" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={onCancel}>
          <span aria-hidden="true">←</span>{t("open.backToMain")}
        </button>
      )}
      <h1>{t("open.title")}</h1>
      <p style={{ margin: 0 }}>{t("open.lead")}</p>
      <fieldset className="open-controls" disabled={busy}>
        <form id="open-project" className="field" onSubmit={(event) => {
          event.preventDefault();
          open(path);
        }}>
          <label htmlFor="ddb-path">{t("open.ddbPath")}</label>
          <input id="ddb-path" type="text" value={ddbPath} required spellCheck={false} autoCapitalize="none"
                 autoCorrect="off" aria-describedby="ddb-path-hint"
                 onChange={(event) => { setDdbPath(event.target.value); setSelected(null); }} />
          <span id="ddb-path-hint" className="note">
            {t(info.serverMode ? "open.ddbPathServerHint" : "open.ddbPathHint")}
          </span>
        </form>
        <FileBrowser start={start} kinds={["ddb", "tdb"]} places={info.startFolders}
                     selected={selected?.path ?? null} onFolder={setFolder}
                     onSelect={(item) => {
                       if (item.kind === "ddb!") open(item.path);
                       else {
                         const kind = item.kind.replace("!", "");
                         setSelected({ path: item.path, kind });
                         setDdbPath(kind === "ddb" ? item.path : "");
                       }
                     }} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn main" type="submit" form="open-project" disabled={!path}>
            {t("open.openDdb")}
          </button>
          <button className="btn" disabled={!path} onClick={() => open(path, true)}>
            {t("open.openReadOnly")}
          </button>
          <span style={{ flex: 1 }} />
          <button className="btn" disabled={!folder} onClick={() => setMode("template")}>{t("open.createHere")}</button>
          <button className="btn" disabled={!folder} onClick={() => setMode("demo")}>{t("open.demo")}</button>
        </div>
      </fieldset>
      {opening && <p role="status">{t("open.opening")}</p>}
      {creating && <p role="status">{creating}</p>}

      {mode === "template" && (
        <TemplatePicker info={info} folder={folder} onCancel={() => setMode("none")}
                        onPick={(template) => create(template, false)} />
      )}
      {mode === "demo" && (
        <Dialog title={t("open.demo")} onClose={() => setMode("none")}
                actions={<>
                  <button className="btn" onClick={() => setMode("none")}>{t("open.cancel")}</button>
                  <button className="btn main" onClick={() => create(null, true)}>{t("dialog.ok")}</button>
                </>}>
          <p>{t("open.demoLead")}</p>
          <p className="path">{folder}</p>
        </Dialog>
      )}
    </main>
  );
}

function TemplatePicker({ info, folder, onCancel, onPick }: {
  info: Info; folder: string; onCancel: () => void; onPick: (path: string) => void;
}) {
  const { t } = useI18n();
  const [template, setTemplate] = useState<string | null>(null);
  return (
    <Dialog title={t("open.chooseTemplate")} onClose={onCancel} wide
            actions={<>
              <button className="btn" onClick={onCancel}>{t("open.cancel")}</button>
              <button className="btn main" disabled={!template} onClick={() => template && onPick(template)}>
                {t("open.createHere")}
              </button>
            </>}>
      <p>{t("open.createLead")}</p>
      <p className="path">{folder}</p>
      <FileBrowser start={folder} kinds={["tdb"]} places={info.startFolders} selected={template}
                   onSelect={(item) => setTemplate(item.path)} />
    </Dialog>
  );
}
