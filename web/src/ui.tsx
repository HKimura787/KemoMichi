import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import { useI18n } from "./i18n";

type ToastKind = "error" | "success" | "warning" | "info";
interface Toast { id: number; kind: ToastKind; text: string }

const ToastContext = createContext<{ push: (kind: ToastKind, text: string) => void; error: (e: unknown) => void }>({
  push: () => {},
  error: () => {},
});

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const remove = (id: number) => setToasts((list) => list.filter((x) => x.id !== id));
  const push = useCallback((kind: ToastKind, text: string) => {
    const id = next.current++;
    setToasts((list) => [...list.slice(-3), { id, kind, text }]);
    if (kind === "success" || kind === "info") setTimeout(() => remove(id), 5000);
  }, []);
  const error = useCallback(
    (e: unknown) => {
      if (e instanceof ApiError) push("error", t(e.key, e.params));
      else push("error", t("error.unexpected") + (e instanceof Error ? ` (${e.message})` : ""));
    },
    [push, t],
  );
  const icons: Record<ToastKind, string> = { error: "✕", success: "✓", warning: "!", info: "i" };
  return (
    <ToastContext.Provider value={{ push, error }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast ${toast.kind}`}>
            <span className="icon" aria-hidden>{icons[toast.kind]}</span>
            <span>{toast.text}</span>
            <button className="btn text small" onClick={() => remove(toast.id)}>{t("settings.close")}</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

export function Dialog({ title, onClose, children, actions, wide }: {
  title: string; onClose: () => void; children: ReactNode; actions?: ReactNode; wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("button, input, select, textarea")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      previous?.focus?.();
    };
  }, [onClose]);
  return (
    <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title} ref={ref}
           style={wide ? { width: "min(960px, calc(100vw - 32px))" } : undefined}>
        <h2>{title}</h2>
        <div className="body">{children}</div>
        {actions && <div className="actions">{actions}</div>}
      </div>
    </div>
  );
}

export interface BrowseResult { path: string; kind: string }

/** Folder browser served by the backend, so it works the same in the desktop app and in a browser. */
export function FileBrowser({ start, kinds, selected, onSelect, onFolder, places }: {
  start: string;
  kinds: string[];
  selected: string | null;
  onSelect: (item: BrowseResult) => void;
  onFolder?: (path: string) => void;
  places: { name: string; path: string }[];
}) {
  const { t } = useI18n();
  const toast = useToast();
  const [path, setPath] = useState(start);
  const [listing, setListing] = useState<Awaited<ReturnType<typeof api.browse>> | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.browse(path).then((l) => {
      if (cancelled) return;
      setListing(l);
      onFolder?.(l.path);
      try { localStorage.setItem("kemomichi.lastFolder", l.path); } catch { /* ignore */ }
    }).catch((e) => !cancelled && toast.error(e));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  const files = listing?.files.filter((f) => kinds.includes(f.kind)) ?? [];
  return (
    <div className="browser">
      <nav className="places" aria-label={t("open.places")}>
        <div className="section-title">{t("open.places")}</div>
        {places.map((p) => <button key={p.path} onClick={() => setPath(p.path)}>{p.name}</button>)}
      </nav>
      <div>
        <div className="path" style={{ marginBottom: 6 }}>{listing?.path}</div>
        <div className="listing" role="listbox" aria-label={listing?.path}>
          {listing?.parent && (
            <button onClick={() => setPath(listing.parent!)}><span className="kind">↑</span>{t("open.up")}</button>
          )}
          {listing?.dirs.map((d) => (
            <button key={d.path} onClick={() => setPath(d.path)}><span className="kind">DIR</span>{d.name}</button>
          ))}
          {files.map((f) => (
            <button key={f.path} role="option" aria-selected={selected === f.path}
                    onClick={() => onSelect(f)} onDoubleClick={() => onSelect({ ...f, kind: f.kind + "!" })}>
              <span className="kind">.{f.kind}</span>{f.name}
            </button>
          ))}
          {listing && files.length === 0 && listing.dirs.length === 0 && (
            <div style={{ padding: 10, color: "var(--km-text-sub)" }}>{t("open.empty")}</div>
          )}
        </div>
      </div>
    </div>
  );
}

export function lastFolder(fallback: string): string {
  try {
    return localStorage.getItem("kemomichi.lastFolder") || fallback;
  } catch {
    return fallback;
  }
}
