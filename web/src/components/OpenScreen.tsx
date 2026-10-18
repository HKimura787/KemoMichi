import { useState } from "react";
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

export function OpenScreen({ info, onOpened }: { info: Info; onOpened: (p: Project) => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const [selected, setSelected] = useState<{ path: string; kind: string } | null>(null);
  const [folder, setFolder] = useState<string>("");
  const [creating, setCreating] = useState<string | null>(null);
  const [mode, setMode] = useState<"none" | "template" | "demo">("none");

  const open = async (path: string, readOnly = false) => {
    try {
      onOpened(await api.open(path, readOnly));
    } catch (e) {
      toast.error(e);
    }
  };

  const create = async (template: string | null, demo: boolean) => {
    try {
      setCreating(t("open.creating", { done: 0, total: "…" }));
      const job = await api.create(folder, template, demo);
      await waitForJob(job.id, (done, total) => setCreating(t("open.creating", { done, total: total || "…" })));
      onOpened(await api.project());
    } catch (e: any) {
      toast.push("error", e?.error ? t(e.error, e.params) : t("error.unexpected"));
    } finally {
      setCreating(null);
      setMode("none");
    }
  };

  const start = lastFolder(info.startFolders[0]?.path ?? "/");
  return (
    <div className="open">
      <h1>{t("open.title")}</h1>
      <p style={{ margin: 0 }}>{t("open.lead")}</p>
      <FileBrowser start={start} kinds={["ddb", "tdb"]} places={info.startFolders}
                   selected={selected?.path ?? null} onFolder={setFolder}
                   onSelect={(item) => {
                     if (item.kind === "ddb!") open(item.path);
                     else setSelected({ path: item.path, kind: item.kind.replace("!", "") });
                   }} />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn main" disabled={selected?.kind !== "ddb"} onClick={() => selected && open(selected.path)}>
          {t("open.openDdb")}
        </button>
        <button className="btn" disabled={selected?.kind !== "ddb"} onClick={() => selected && open(selected.path, true)}>
          {t("open.openReadOnly")}
        </button>
        <span style={{ flex: 1 }} />
        <button className="btn" disabled={!folder} onClick={() => setMode("template")}>{t("open.createHere")}</button>
        <button className="btn" disabled={!folder} onClick={() => setMode("demo")}>{t("open.demo")}</button>
      </div>
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
    </div>
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
