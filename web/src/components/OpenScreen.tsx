import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import type { Info, Project, TemplateDraft } from "../types";
import { Dialog, FileBrowser, lastFolder, useToast } from "../ui";
import { TemplateWizard } from "./TemplateWizard";

export async function waitForJob(id: string, onProgress: (done: number, total: number) => void) {
  for (;;) {
    const job = await api.job(id);
    onProgress(job.done, job.total);
    if (job.status === "done") return job.result;
    if (job.status === "failed") throw Object.assign(new Error(job.error?.detail), job.error);
    await new Promise((r) => setTimeout(r, 400));
  }
}

/** A project opened before (design: 続きから). Kept only in this browser. */
export interface RecentProject { path: string; name: string; total: number; at: number }

const RECENT_KEY = "kemomichi.recent";
const RECENT_MAX = 6;

export function readRecent(): RecentProject[] {
  try {
    const raw = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    if (!Array.isArray(raw)) return [];
    return raw.filter((r): r is RecentProject =>
      !!r && typeof r.path === "string" && r.path !== "" && typeof r.name === "string"
      && typeof r.total === "number" && typeof r.at === "number").slice(0, RECENT_MAX);
  } catch {
    return [];
  }
}

/** Puts the project at the top of the list; the same path appears only once. */
export function rememberRecent(list: RecentProject[], p: { path: string; name: string; total: number }, at: number): RecentProject[] {
  return [{ path: p.path, name: p.name, total: p.total, at }, ...list.filter((r) => r.path !== p.path)].slice(0, RECENT_MAX);
}

function saveRecent(list: RecentProject[]) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list)); } catch { /* storage unavailable: the list is a convenience */ }
}

const STEPS = ["open.step.folder", "open.step.fields", "open.step.confirm"] as const;

function Steps({ current, label }: { current: number | null; label: string }) {
  const { t } = useI18n();
  return (
    <ol className="steps" aria-label={label}>
      {STEPS.map((key, i) => (
        <li key={key} aria-current={current === i ? "step" : undefined} className={current !== null && i < current ? "done" : undefined}>
          <i>{i + 1}</i>{t(key)}
        </li>
      ))}
    </ol>
  );
}

export function OpenScreen({ info, onOpened, onCancel }: {
  info: Info; onOpened: (p: Project) => void; onCancel?: () => void;
}) {
  const { t, lang, setLang } = useI18n();
  const toast = useToast();
  const [recent, setRecent] = useState<RecentProject[]>(readRecent);
  const [ddbPath, setDdbPath] = useState("");
  const [readOnly, setReadOnly] = useState(false);
  const [opening, setOpening] = useState(false);
  const operation = useRef(false);
  const [folder, setFolder] = useState<string>("");
  const [template, setTemplate] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);
  const [mode, setMode] = useState<"none" | "browse" | "folder" | "template" | "demo">("none");
  const busy = opening || creating !== null;

  useEffect(() => {
    if (!onCancel || busy || mode !== "none") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, busy, mode]);

  const opened = (p: Project) => {
    const next = rememberRecent(readRecent(), p, Date.now());
    saveRecent(next);
    setRecent(next);
    onOpened(p);
  };

  const open = async (path: string, ro = false) => {
    if (!path || operation.current) return;
    operation.current = true;
    setOpening(true);
    try {
      opened(await api.open(path, ro));
    } catch (e) {
      toast.error(e);
    } finally {
      operation.current = false;
      setOpening(false);
    }
  };

  const create = async (tpl: string | null, demo: boolean, draft?: TemplateDraft) => {
    if (operation.current) return;
    operation.current = true;
    try {
      setCreating(t("open.creating", { done: 0, total: "…" }));
      const job = await api.create(folder, tpl, demo, draft);
      await waitForJob(job.id, (done, total) => setCreating(t("open.creating", { done, total: total || "…" })));
      opened(await api.project());
    } catch (e: any) {
      if (draft) throw e;
      toast.push("error", e?.error ? t(e.error, e.params) : t("error.unexpected"));
    } finally {
      operation.current = false;
      setCreating(null);
      if (!draft) setMode("none");
    }
  };

  const forget = (path: string) => {
    const next = recent.filter((r) => r.path !== path);
    saveRecent(next);
    setRecent(next);
  };

  const start = lastFolder(info.startFolders[0]?.path ?? "/");
  const dateFormat = new Intl.DateTimeFormat(lang === "ja" ? "ja-JP" : "en-GB", { dateStyle: "medium", timeStyle: "short" });
  const folderPicker = (kinds: string[], onPick: (item: { path: string; kind: string }) => void) => (
    <FileBrowser start={folder || start} kinds={kinds} places={info.startFolders} selected={null}
                 onFolder={(next) => { setFolder(next); setTemplate(null); }} onSelect={onPick} />
  );

  return (
    <main className="open" aria-busy={busy}>
      {onCancel && (
        <button className="btn" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={onCancel}>
          <span aria-hidden="true">←</span>{t("open.backToMain")}
        </button>
      )}
      <div className="start">
        <section aria-labelledby="recent-h">
          <h2 id="recent-h">{t("open.recent")}</h2>
          {recent.length === 0 ? (
            <p className="note" data-testid="recent-empty">{t("open.recentEmpty")}</p>
          ) : (
            <ul className="rec" data-testid="recent">
              {recent.map((r) => (
                <li key={r.path}>
                  <button type="button" disabled={busy} onClick={() => open(r.path)} title={r.path}>
                    <span className="nm">{r.name}</span>
                    <span className="pr">{t("filter.count", { count: r.total })}</span>
                    <span className="pth">{r.path}</span>
                    <span className="dt">{dateFormat.format(new Date(r.at))}</span>
                  </button>
                  <button type="button" className="forget" disabled={busy} onClick={() => forget(r.path)}
                          aria-label={t("open.forget", { name: r.name })} title={t("open.forget", { name: r.name })}>×</button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="acts">
          <form className="act" onSubmit={(e) => { e.preventDefault(); void open(ddbPath.trim(), readOnly); }}>
            <h2>{t("open.openTitle")}</h2>
            <div className="pathrow">
              <input type="text" value={ddbPath} onChange={(e) => setDdbPath(e.target.value)} disabled={busy}
                     aria-label={t("open.ddbPath")} placeholder={t("open.ddbPlaceholder")} />
              <button type="button" className="btn small" disabled={busy} onClick={() => setMode("browse")}>{t("open.browseDots")}</button>
            </div>
            <div className="row">
              <button type="submit" className="btn main small" disabled={busy || !ddbPath.trim()}>{t("open.openDdb")}</button>
              <label className="check"><input type="checkbox" checked={readOnly} onChange={(e) => setReadOnly(e.target.checked)} /> {t("open.readOnly")}</label>
            </div>
          </form>
          <div className="act">
            <h2>{t("open.newTitle")}</h2>
            <Steps current={null} label={t("open.steps")} />
            <div>
              <button type="button" className="btn small" disabled={busy}
                      onClick={() => { setTemplate(null); setMode("folder"); }}>{t("open.chooseFolder")}</button>
            </div>
          </div>
        </div>

        <div className="sfoot">
          <span>{t("open.firstTime")}</span>
          <button type="button" className="btn text small" disabled={busy} onClick={() => setMode("demo")}>{t("open.demo")}</button>
          <span className="spacer" />
          <button type="button" className="btn text small" onClick={() => setLang(lang === "ja" ? "en" : "ja")}
                  aria-label={t("settings.language")}>{lang === "ja" ? "日本語 / EN" : "EN / 日本語"}</button>
        </div>
      </div>
      {opening && <p role="status">{t("open.opening")}</p>}
      {creating && <p role="status">{creating}</p>}

      {mode === "browse" && (
        <Dialog title={t("open.openTitle")} wide onClose={() => setMode("none")}
                actions={<>
                  <button className="btn" onClick={() => setMode("none")}>{t("open.cancel")}</button>
                  <button className="btn main" disabled={!ddbPath.trim()} onClick={() => setMode("none")}>{t("dialog.ok")}</button>
                </>}>
          {folderPicker(["ddb"], (item) => {
            setDdbPath(item.path);
            if (item.kind === "ddb!") { setMode("none"); void open(item.path, readOnly); }
          })}
          <p className="path">{ddbPath}</p>
        </Dialog>
      )}
      {mode === "folder" && (
        <Dialog title={t("open.newTitle")} wide onClose={() => setMode("none")}
                actions={<>
                  <button className="btn" onClick={() => setMode("none")}>{t("open.cancel")}</button>
                  <button className="btn main" disabled={!folder} onClick={() => setMode("template")}>{t("open.next")}</button>
                </>}>
          <Steps current={0} label={t("open.steps")} />
          {folderPicker(["tdb"], (item) => setTemplate(item.kind.replace("!", "") === "tdb" ? item.path : null))}
          <dl className="kv">
            <dt>{t("open.destination")}</dt><dd>{folder || "—"}</dd>
            {template && <><dt>{t("open.template")}</dt><dd>{template}</dd></>}
          </dl>
        </Dialog>
      )}
      {mode === "template" && (
        <TemplateWizard info={info} folder={folder} initialTemplate={template}
                        progress={creating} onCancel={() => setMode("none")}
                        onCreate={(tpl, draft) => create(tpl, false, draft)} />
      )}
      {mode === "demo" && (
        <Dialog title={t("open.demo")} wide onClose={() => setMode("none")}
                actions={<>
                  <button className="btn" onClick={() => setMode("none")}>{t("open.cancel")}</button>
                  <button className="btn main" disabled={!folder} onClick={() => create(null, true)}>{t("dialog.ok")}</button>
                </>}>
          <p>{t("open.demoLead")}</p>
          {folderPicker([], () => undefined)}
          <p className="path">{folder}</p>
        </Dialog>
      )}
    </main>
  );
}
