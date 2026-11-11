import { useCallback, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import type { TFunc } from "../i18n";
import type { Control, ControlType, Info, TemplateConfirmation, TemplateDraft, TemplatePreview } from "../types";
import { Dialog, FileBrowser } from "../ui";

const USER_TYPES: ControlType[] = ["Note", "MultiLine", "FixedChoice", "MultiChoice", "Flag", "Counter",
  "IntegerAny", "IntegerPositive", "DecimalAny", "DecimalPositive", "AlphaNumeric", "DateTime_", "Date_", "Time_"];
type EditingControl = Control & { choicesText: string };
type Step = "choose" | "edit" | "confirm";

function editable(control: Control): EditingControl {
  return { ...control, choicesText: control.choices.join("\n") };
}

function clean(control: EditingControl): Control {
  const { choicesText, ...rest } = control;
  return { ...rest, choices: control.type === "FixedChoice" || control.type === "MultiChoice"
    ? choicesText.split(/\r?\n/).map((item) => item.trim()).filter(Boolean) : [] };
}

function initialValue(type: ControlType) {
  const year = new Date().getFullYear();
  if (type === "Flag") return "false";
  if (["Counter", "IntegerAny", "IntegerPositive", "DecimalAny", "DecimalPositive"].includes(type)) return "0";
  if (type === "DateTime_") return `${year}-01-01 12:00:00`;
  if (type === "Date_") return `${year}-01-01`;
  if (type === "Time_") return "12:00:00";
  return "";
}

export function TemplateWizard({ info, folder, initialTemplate, progress, onCancel, onCreate }: {
  info: Info; folder: string; initialTemplate: string | null; progress: string | null;
  onCancel: () => void; onCreate: (template: string, draft: TemplateDraft) => Promise<void>;
}) {
  const { t } = useI18n();
  const [step, setStep] = useState<Step>("choose");
  const [template, setTemplate] = useState(initialTemplate);
  const [document, setDocument] = useState<TemplatePreview | null>(null);
  const [controls, setControls] = useState<EditingControl[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [confirmation, setConfirmation] = useState<TemplateConfirmation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const close = useCallback(() => { if (!busy) onCancel(); }, [busy, onCancel]);
  const active = controls.find((control) => control.id === activeId);
  const users = controls.filter((control) => !control.standard);

  const reportError = (e: unknown) => {
    const detail = e as { error?: string; params?: Record<string, unknown> };
    const key = e instanceof ApiError ? e.key : detail?.error ?? "error.unexpected";
    const params = e instanceof ApiError ? e.params : detail?.params;
    const message = t(key, params);
    setError(params?.field ? t("template.fieldError", { field: params.field, message }) : message);
    const invalid = controls.find((control) => control.label === params?.field || control.dataLabel === params?.field);
    if (invalid) setActiveId(invalid.id);
  };

  const load = async () => {
    if (!template || busy) return;
    setError("");
    setBusy(true);
    try {
      const preview = await api.template(template, folder);
      if (document?.path === preview.path && document.revision === preview.revision) {
        setStep("edit");
        return;
      }
      setTemplate(preview.path);
      setDocument(preview);
      setControls(preview.controls.map(editable));
      setActiveId((preview.controls.find((control) => !control.standard) ?? preview.controls[0])?.id ?? null);
      setName(preview.suggestedName);
      setStep("edit");
    } catch (e) { reportError(e); }
    finally { setBusy(false); }
  };

  const validate = async () => {
    if (!document || busy) return;
    setError("");
    setBusy(true);
    try {
      const confirmed = await api.validateTemplate(folder, document.path,
        { name, revision: document.revision, controls: controls.map(clean) });
      setConfirmation(confirmed);
      setName(confirmed.name);
      setControls(confirmed.controls.map(editable));
      setStep("confirm");
    } catch (e) { reportError(e); }
    finally { setBusy(false); }
  };

  const create = async () => {
    if (!document || !confirmation || busy) return;
    setError("");
    setBusy(true);
    try { await onCreate(document.path, confirmation); }
    catch (e) { reportError(e); setStep("edit"); }
    finally { setBusy(false); }
  };

  const patch = (changes: Partial<EditingControl>) => {
    setControls((items) => items.map((control) => control.id === activeId ? { ...control, ...changes } : control));
    setError("");
  };

  const add = () => {
    const taken = new Set(controls.map((control) => control.dataLabel.toLowerCase()));
    let number = 1;
    while (taken.has(`field${number}`)) number += 1;
    const id = Math.min(0, ...controls.map((control) => control.id)) - 1;
    const item: EditingControl = { id, controlOrder: controls.length, spreadsheetOrder: controls.length + 1,
      type: "Note", label: t("template.newField"), dataLabel: `Field${number}`, defaultValue: "", tooltip: "",
      visible: true, choices: [], choicesText: "", includeEmptyChoice: true, exportToCsv: true,
      width: "100", copyable: true, standard: false };
    setControls((items) => [...items, item]);
    setActiveId(id);
    setError("");
  };

  const remove = () => {
    if (!active || active.standard) return;
    const index = controls.indexOf(active);
    const next = controls.filter((control) => control.id !== active.id);
    setControls(next);
    setActiveId(next[Math.min(index, next.length - 1)]?.id ?? null);
    setError("");
  };

  const move = (direction: number) => {
    if (!active || active.standard) return;
    const neighbor = users[users.indexOf(active) + direction];
    if (!neighbor) return;
    setControls((items) => {
      const next = [...items];
      const a = next.indexOf(active), b = next.indexOf(neighbor);
      [next[a], next[b]] = [next[b], next[a]];
      return next;
    });
  };

  return (
    <Dialog title={t("template.title")} onClose={close} wide actions={<>
      <button className="btn" disabled={busy} onClick={close}>{t("open.cancel")}</button>
      <span className="template-action-spacer" />
      {step !== "choose" && <button className="btn" disabled={busy} onClick={() => {
        setStep(step === "confirm" ? "edit" : "choose"); setError("");
      }}>{t(step === "confirm" ? "template.backToEdit" : "template.backToChoose")}</button>}
      {step === "choose" && <button className="btn main" disabled={busy || !template} onClick={load}>{t("template.edit")}</button>}
      {step === "edit" && <button className="btn main" disabled={busy || !name.trim()} onClick={validate}>{t("template.review")}</button>}
      {step === "confirm" && <button className="btn main" disabled={busy} onClick={create}>{t("template.create")}</button>}
    </>}>
      <ol className="template-steps" aria-label={t("template.steps")}>
        {(["choose", "edit", "confirm"] as const).map((item, index) => <li key={item} aria-current={step === item ? "step" : undefined}>
          <span>{index + 1}</span>{t(`template.step.${item}`)}
        </li>)}
      </ol>
      {error && <p className="template-error" role="alert">{error}</p>}
      {busy && <p role="status">{progress || t("template.checking")}</p>}
      <p className="path template-destination">{t("open.destination")}: {folder}</p>
      {step === "choose" ? <>
        <p>{t("template.chooseLead")}</p>
        <fieldset className="open-controls" disabled={busy}>
          <FileBrowser start={folder} kinds={["tdb"]} places={info.startFolders} selected={template}
                       onSelect={(item) => { setTemplate(item.path); setError(""); }} />
        </fieldset>
      </> : step === "edit" ? <>
        <p className="note">{t("template.editLead")}</p>
        <fieldset className="open-controls" disabled={busy}>
          <label className="field"><span>{t("template.name")}</span>
            <input type="text" value={name} onChange={(e) => { setName(e.target.value); setError(""); }} />
            <span className="note">{t("template.nameHint")}</span>
          </label>
          <div className="template-editor">
            <nav className="template-fields" aria-label={t("template.fields")}>
              <div className="section-title">{t("template.fields")}</div>
              {controls.map((control) => <button type="button" key={control.id} aria-current={activeId === control.id ? "true" : undefined}
                onClick={() => setActiveId(control.id)}>
                <strong>{control.label || control.dataLabel}</strong>
                <span>{t(`template.type.${control.type}`)}{control.standard ? ` · ${t("template.automatic")}` : ""}</span>
              </button>)}
              <button type="button" className="btn small" onClick={add}>＋ {t("template.add")}</button>
            </nav>
            {active && <section className="template-detail" aria-label={t("template.attributes")}>
              <div className="template-field-toolbar">
                <h3>{active.label || active.dataLabel}</h3>
                <button className="btn small" disabled={active.standard || users.indexOf(active) <= 0}
                        onClick={() => move(-1)} aria-label={t("template.moveUp")}>↑</button>
                <button className="btn small" disabled={active.standard || users.indexOf(active) === users.length - 1}
                        onClick={() => move(1)} aria-label={t("template.moveDown")}>↓</button>
                <button className="btn small" disabled={active.standard} onClick={remove}>{t("template.remove")}</button>
              </div>
              {active.standard && <p className="note">{t("template.standardHint")}</p>}
              <ControlEditor control={active} patch={patch} t={t} />
            </section>}
          </div>
        </fieldset>
      </> : confirmation && <>
        <p>{t("template.confirmLead")}</p>
        <dl className="template-output">
          <dt>{t("template.outputTemplate")}</dt><dd className="path">{confirmation.templatePath}</dd>
          <dt>{t("open.outputName")}</dt><dd className="path">{confirmation.ddbPath}</dd>
        </dl>
        <p className="note">{t("template.sourceUnchanged")}</p>
        <div className="template-summary">
          <table className="plain">
            <caption>{t("template.summary")}</caption>
            <thead><tr>{["label", "dataLabel", "type", "default", "choices", "visible", "export"].map((key) =>
              <th key={key} scope="col">{t(`template.${key}`)}</th>)}</tr></thead>
            <tbody>{confirmation.controls.map((control) => <tr key={control.id}>
              <td>{control.label}</td><td className="path">{control.dataLabel}</td><td>{t(`template.type.${control.type}`)}</td>
              <td>{control.standard && control.type !== "DeleteFlag" ? t("template.automatic") : control.defaultValue || "—"}</td>
              <td>{control.choices.join(" / ") || "—"}</td>
              <td>{t(control.visible ? "template.yes" : "template.no")}</td>
              <td>{t(control.exportToCsv ? "template.yes" : "template.no")}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </>}
    </Dialog>
  );
}

function ControlEditor({ control, patch, t }: {
  control: EditingControl; patch: (changes: Partial<EditingControl>) => void; t: TFunc;
}) {
  const choices = clean(control).choices;
  const choiceType = control.type === "FixedChoice" || control.type === "MultiChoice";
  return <>
    <div className="template-attributes">
      <label className="field"><span>{t("template.label")}</span>
        <input type="text" value={control.label} onChange={(e) => patch({ label: e.target.value })} />
      </label>
      <label className="field"><span>{t("template.dataLabel")}</span>
        <input type="text" spellCheck={false} value={control.dataLabel} readOnly={control.standard}
               onChange={(e) => patch({ dataLabel: e.target.value })} />
        {!control.standard && <span className="note">{t("template.dataLabelHint")}</span>}
      </label>
      <label className="field"><span>{t("template.type")}</span>
        <select value={control.type} disabled={control.standard} onChange={(e) => {
          const type = e.target.value as ControlType;
          patch({ type, defaultValue: initialValue(type) });
        }}>
          {(control.standard ? [control.type] : USER_TYPES).map((type) => <option key={type} value={type}>{t(`template.type.${type}`)}</option>)}
        </select>
      </label>
      <label className="field"><span>{t("template.default")}</span>
        {control.standard ? <input type="text" readOnly value={control.type === "DeleteFlag" ? control.defaultValue : t("template.automatic")} />
          : control.type === "Flag" ? <select value={control.defaultValue} onChange={(e) => patch({ defaultValue: e.target.value })}>
            <option value="false">false</option><option value="true">true</option>
          </select> : control.type === "FixedChoice" ? <select value={control.defaultValue} onChange={(e) => patch({ defaultValue: e.target.value })}>
            <option value="" disabled={!control.includeEmptyChoice}>{t("template.empty")}</option>
            {control.defaultValue && !choices.includes(control.defaultValue) && <option value={control.defaultValue}>{control.defaultValue}</option>}
            {choices.map((choice, index) => <option key={index} value={choice}>{choice}</option>)}
          </select> : control.type === "MultiLine" ? <textarea value={control.defaultValue} onChange={(e) => patch({ defaultValue: e.target.value })} />
          : <input type="text" value={control.defaultValue}
                   placeholder={control.type === "DateTime_" ? "2026-01-01 12:00:00" : control.type === "Date_" ? "2026-01-01"
                     : control.type === "Time_" ? "12:00:00" : undefined}
                   onChange={(e) => patch({ defaultValue: e.target.value })} />}
        {control.type === "MultiChoice" && <span className="note">{t("template.multiDefaultHint")}</span>}
      </label>
    </div>
    {choiceType && <div className="template-choice-editor">
      <label className="field"><span>{t("template.choices")}</span>
        <textarea rows={5} value={control.choicesText} onChange={(e) => patch({ choicesText: e.target.value })} />
        <span className="note">{t("template.choicesHint")}</span>
      </label>
      {control.type === "FixedChoice" && <label className="template-check">
        <input type="checkbox" checked={control.includeEmptyChoice} onChange={(e) => patch({ includeEmptyChoice: e.target.checked })} />
        {t("template.allowEmpty")}
      </label>}
    </div>}
    <div className="template-attributes">
      <label className="field"><span>{t("template.tooltip")}</span>
        <input type="text" value={control.tooltip} onChange={(e) => patch({ tooltip: e.target.value })} />
      </label>
      <label className="field"><span>{t("template.width")}</span>
        <input type="number" min="1" step="1" value={control.width} onChange={(e) => patch({ width: e.target.value })} />
      </label>
    </div>
    <div className="template-checks">
      {(["visible", "exportToCsv", "copyable"] as const).map((key) => <label key={key} className="template-check">
        <input type="checkbox" checked={control[key]} onChange={(e) => patch({ [key]: e.target.checked })} />
        {t(`template.${key === "exportToCsv" ? "export" : key}`)}
      </label>)}
    </div>
  </>;
}
