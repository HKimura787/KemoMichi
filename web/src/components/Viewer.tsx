import { useCallback, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState, forwardRef } from "react";
import { mediaUrl } from "../api";
import { useI18n } from "../i18n";
import type { ColorAdjust, Detection, FileDetail, Guide, ShapeKind, VideoInfo } from "../types";

// Colour-blind-safe annotation colours (Okabe & Ito 2008), design system §2.7.
export const ANNOTATION_COLORS = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#FFFFFF"];

export const NEUTRAL_COLOR: ColorAdjust = { brightness: 1, contrast: 1, saturation: 1, gamma: 1, grayscale: false };

export function filterCss(c: ColorAdjust): string {
  return `url(#km-gamma) brightness(${c.brightness}) contrast(${c.contrast}) saturate(${c.saturation}) grayscale(${c.grayscale ? 1 : 0})`;
}

export interface ViewerHandle {
  currentFrame: () => number;
  seekFrame: (frame: number) => void;
  step: (delta: number) => void;
  togglePlay: () => void;
  pause: () => void;
  fit: () => void;
  capture: () => Promise<string | null>;
  isPlaying: () => boolean;
}

interface Props {
  mediaSession: string;
  initialFrame?: number;
  onPositionCommit?: () => void;
  detail: FileDetail | null;
  missingPath: string;
  color: ColorAdjust;
  compare: boolean;
  guides: Guide[];
  showGuides: boolean;
  detections: Detection[];
  showBoxes: boolean;
  boxThreshold: number;
  categoryLabel: (d: Detection) => string;
  drawing: ShapeKind | null;
  onDrawn: (shape: ShapeKind, points: [number, number][]) => void;
  videoInfo: VideoInfo | null;
  playbackRate?: number;
  onFrame: (frame: number) => void;
}

export const Viewer = forwardRef<ViewerHandle, Props>(function Viewer(props, ref) {
  const { t } = useI18n();
  const { detail, color, compare } = props;
  const stageRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const [draft, setDraft] = useState<[number, number][]>([]);
  const [hover, setHover] = useState<[number, number] | null>(null);
  const [frame, setFrame] = useState(0);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const isVideo = detail?.kind === "video";
  const onFrameRef = useRef(props.onFrame);
  onFrameRef.current = props.onFrame;
  const frameTimes = props.videoInfo?.frameTimes ?? [];
  const resumeApplied = useRef<number | null>(null);

  const fit = useCallback(() => {
    const stage = stageRef.current;
    if (!stage || !natural) return;
    const scale = Math.min(stage.clientWidth / natural.w, stage.clientHeight / natural.h);
    setView({ scale, x: (stage.clientWidth - natural.w * scale) / 2, y: (stage.clientHeight - natural.h * scale) / 2 });
  }, [natural]);

  useLayoutEffect(fit, [fit]);
  useEffect(() => {
    const onResize = () => fit();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [fit]);
  useEffect(() => {
    setNatural(null);
    setDraft([]);
    setFrame(0);
  }, [detail?.id]);
  useEffect(() => setDraft([]), [props.drawing]);

  // ---- video frames ---------------------------------------------------------------------
  const frameAt = useCallback((time: number) => {
    if (!frameTimes.length) return 0;
    let lo = 0, hi = frameTimes.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (frameTimes[mid] <= time + 1e-4) lo = mid; else hi = mid - 1;
    }
    return lo;
  }, [frameTimes]);

  const seekFrame = useCallback((target: number) => {
    const video = videoRef.current;
    if (!video || !frameTimes.length) return;
    const f = Math.max(0, Math.min(frameTimes.length - 1, target));
    const next = frameTimes[f + 1] ?? frameTimes[f] + 0.04;
    // Aim a quarter into the frame so rounding never shows the previous one.
    video.currentTime = frameTimes[f] + (next - frameTimes[f]) / 4;
    setFrame(f);
    onFrameRef.current(f);
  }, [frameTimes]);

  useEffect(() => {
    if (!isVideo || !detail || !natural || !frameTimes.length || resumeApplied.current === detail.id) return;
    resumeApplied.current = detail.id;
    seekFrame(props.initialFrame ?? 0);
  }, [isVideo, detail?.id, natural, frameTimes, props.initialFrame, seekFrame]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !isVideo) return;
    let handle = 0;
    const anyVideo = video as any;
    const update = () => {
      const f = frameAt(video.currentTime);
      setFrame(f);
      onFrameRef.current(f);
    };
    const loop = () => {
      update();
      handle = anyVideo.requestVideoFrameCallback ? anyVideo.requestVideoFrameCallback(loop) : 0;
    };
    if (anyVideo.requestVideoFrameCallback) handle = anyVideo.requestVideoFrameCallback(loop);
    video.addEventListener("seeked", update);
    video.addEventListener("timeupdate", update);
    return () => {
      if (handle && anyVideo.cancelVideoFrameCallback) anyVideo.cancelVideoFrameCallback(handle);
      video.removeEventListener("seeked", update);
      video.removeEventListener("timeupdate", update);
    };
  }, [isVideo, frameAt, detail?.id]);

  useEffect(() => {
    if (videoRef.current && props.playbackRate) {
      videoRef.current.playbackRate = props.playbackRate;
    }
  }, [props.playbackRate, detail?.id]);

  useImperativeHandle(ref, () => ({
    currentFrame: () => frame,
    pause: () => videoRef.current?.pause(),
    seekFrame,
    step: (delta) => {
      videoRef.current?.pause();
      seekFrame(frame + delta);
    },
    togglePlay: () => {
      const v = videoRef.current;
      if (!v) return;
      if (v.paused) v.play(); else v.pause();
    },
    fit,
    isPlaying: () => {
      const v = videoRef.current;
      return !!(v && !v.paused && !v.ended && v.readyState > 1);
    },
    capture: async () => {
      if (!natural) return null;
      try {
        const canvas = document.createElement("canvas");
        canvas.width = natural.w;
        canvas.height = natural.h;
        const ctx = canvas.getContext("2d");
        if (!ctx) return null;

        if (!compare) {
          ctx.filter = `brightness(${color.brightness}) contrast(${color.contrast}) saturate(${color.saturation}) grayscale(${color.grayscale ? 1 : 0})`;
        }

        if (isVideo && videoRef.current) {
          ctx.drawImage(videoRef.current, 0, 0, natural.w, natural.h);
        } else if (imgRef.current) {
          ctx.drawImage(imgRef.current, 0, 0, natural.w, natural.h);
        } else {
          return null;
        }

        if (!compare && color.gamma !== 1) {
          const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const d = imgData.data;
          const invGamma = 1 / color.gamma;
          const lut = new Uint8Array(256);
          for (let i = 0; i < 256; i++) {
            lut[i] = Math.min(255, Math.max(0, Math.round(255 * Math.pow(i / 255, invGamma))));
          }
          for (let i = 0; i < d.length; i += 4) {
            d[i] = lut[d[i]];
            d[i + 1] = lut[d[i + 1]];
            d[i + 2] = lut[d[i + 2]];
          }
          ctx.putImageData(imgData, 0, 0);
        }

        return canvas.toDataURL("image/jpeg", 0.95);
      } catch (err) {
        console.error("Frame capture error:", err);
        return null;
      }
    },
  }), [frame, seekFrame, fit, natural, isVideo, compare, color]);

  // ---- pan, zoom and drawing -----------------------------------------------------------
  const toImage = (e: { clientX: number; clientY: number }): [number, number] | null => {
    const stage = stageRef.current;
    if (!stage || !natural) return null;
    const rect = stage.getBoundingClientRect();
    const x = (e.clientX - rect.left - view.x) / (view.scale * natural.w);
    const y = (e.clientY - rect.top - view.y) / (view.scale * natural.h);
    return [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))];
  };

  const needed: Record<ShapeKind, number> = { line: 2, triangle: 3, rect: 2, circle: 2, polygon: Infinity };

  const onWheel = (e: React.WheelEvent) => {
    const stage = stageRef.current;
    if (!stage) return;
    const rect = stage.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    const factor = Math.exp(-e.deltaY * 0.0015);
    setView((v) => {
      const scale = Math.min(40, Math.max(0.05, v.scale * factor));
      const k = scale / v.scale;
      return { scale, x: px - (px - v.x) * k, y: py - (py - v.y) * k };
    });
  };

  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    if (props.drawing) {
      const p = toImage(e);
      if (!p) return;
      const points = [...draft, p];
      if (points.length >= needed[props.drawing]) {
        props.onDrawn(props.drawing, points);
        setDraft([]);
      } else {
        setDraft(points);
      }
      return;
    }
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (props.drawing) setHover(toImage(e));
    const d = drag.current;
    if (!d) return;
    setView((v) => ({ ...v, x: d.vx + e.clientX - d.x, y: d.vy + e.clientY - d.y }));
  };
  const finishPolygon = () => {
    if (props.drawing === "polygon" && draft.length >= 3) {
      props.onDrawn("polygon", draft);
      setDraft([]);
    }
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" && props.drawing === "polygon") finishPolygon();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!detail) {
    return <div className="stage"><div className="notice">{t("viewer.empty")}</div></div>;
  }
  if (!detail.exists) {
    return <div className="stage"><div className="notice">{t("viewer.missing", { path: props.missingPath })}</div></div>;
  }

  const w = natural?.w ?? 1, h = natural?.h ?? 1;
  const filter = compare ? "none" : filterCss(color);
  const lineWidth = Math.max(1, 2 / view.scale);
  const boxes = props.showBoxes
    ? props.detections.filter((d) => d.conf >= props.boxThreshold && d.category !== "0" &&
        (!isVideo || d.frame === null || d.frame === frame))
    : [];

  return (
    <div ref={stageRef} className={`stage${props.drawing ? " drawing" : ""}`}
         onWheel={onWheel} onMouseDown={onMouseDown} onMouseMove={onMouseMove}
         onMouseUp={() => (drag.current = null)} onMouseLeave={() => (drag.current = null)}
         onDoubleClick={finishPolygon}>
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden>
        <filter id="km-gamma">
          <feComponentTransfer>
            {(["R", "G", "B"] as const).map((c) => {
              const Fn = `feFunc${c}` as "feFuncR";
              return <Fn key={c} type="gamma" amplitude={1} exponent={compare ? 1 : 1 / color.gamma} offset={0} />;
            })}
          </feComponentTransfer>
        </filter>
      </svg>
      <div className="content" style={{
        width: w * view.scale, height: h * view.scale, transform: `translate(${view.x}px, ${view.y}px)`,
        visibility: natural ? "visible" : "hidden",
      }}>
        {isVideo ? (
          <video key={detail.id} ref={videoRef} src={mediaUrl(detail.id, "video", props.mediaSession)} preload="auto" muted
                 onPause={() => {
                   const video = videoRef.current;
                   if (video && frameTimes.length) onFrameRef.current(frameAt(video.currentTime));
                   props.onPositionCommit?.();
                 }}
                 crossOrigin="anonymous"
                 style={{ filter }} playsInline
                 onLoadedMetadata={(e) => {
                   const v = e.currentTarget;
                   if (props.playbackRate) v.playbackRate = props.playbackRate;
                   setNatural({ w: v.videoWidth, h: v.videoHeight });
                 }}
                 onPlay={(e) => {
                   if (props.playbackRate) e.currentTarget.playbackRate = props.playbackRate;
                 }} />
        ) : (
          <img key={detail.id} ref={imgRef} src={mediaUrl(detail.id, "preview", props.mediaSession)} alt={detail.values.File} draggable={false}
               crossOrigin="anonymous"
               style={{ filter }}
               onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })} />
        )}
        {natural && (
          <svg className="overlay" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
            {props.showGuides && props.guides.map((g) => <GuideShape key={g.id} guide={g} w={w} h={h} lw={lineWidth} />)}
            {props.drawing && (draft.length > 0 || hover) && (
              <GuideShape guide={{ id: "draft", shape: props.drawing, name: "", color: "#FFFFFF", width: 2,
                                   points: hover ? [...draft, hover] : draft }} w={w} h={h} lw={lineWidth} dashed />
            )}
            {boxes.map((d, i) => {
              const [x, y, bw, bh] = d.bbox;
              const stroke = ANNOTATION_COLORS[Number(d.category) % ANNOTATION_COLORS.length] ?? "#E69F00";
              const label = `${props.categoryLabel(d)} ${Math.round(d.conf * 100)}%`;
              const fs = 14 / view.scale;
              return (
                <g key={d.id ?? i}>
                  <rect x={x * w} y={y * h} width={bw * w} height={bh * h} fill="none" stroke="#000" strokeWidth={lineWidth * 2} />
                  <rect x={x * w} y={y * h} width={bw * w} height={bh * h} fill="none" stroke={stroke} strokeWidth={lineWidth} />
                  <rect x={x * w} y={y * h - fs * 1.4} width={label.length * fs * 0.62 + fs * 0.6} height={fs * 1.4} fill="#000" rx={fs * 0.25} />
                  <text x={x * w + fs * 0.3} y={y * h - fs * 0.35} fill="#fff" fontSize={fs} fontWeight={700}>{label}</text>
                </g>
              );
            })}
          </svg>
        )}
      </div>
      {compare && <div className="compare-tag">{t("viewer.original")}</div>}
      {props.drawing && (
        <div className="hint">
          {props.drawing === "polygon" ? t("guide.polygonHint") : t("guide.drawing", { shape: t(`guide.${props.drawing}`) })}
        </div>
      )}
    </div>
  );
});

export function GuideShape({ guide, w, h, lw, dashed }: { guide: Guide; w: number; h: number; lw: number; dashed?: boolean }) {
  const pts = guide.points.map(([x, y]) => [x * w, y * h] as const);
  const width = (guide.width || 2) * lw;
  const dash = dashed ? `${6 * lw} ${4 * lw}` : undefined;
  const common = { fill: "none", strokeLinejoin: "round" as const, strokeDasharray: dash };
  let shape: JSX.Element | null = null;
  const draw = (el: (stroke: string, sw: number, fill?: string) => JSX.Element) => (
    <>
      {el("#000", width + 2 * lw)}
      {el(guide.color || "#FFFFFF", width, "rgba(255,255,255,0.15)")}
    </>
  );
  if (guide.shape === "line" && pts.length >= 2) {
    shape = draw((s, sw) => <line x1={pts[0][0]} y1={pts[0][1]} x2={pts[1][0]} y2={pts[1][1]} stroke={s} strokeWidth={sw} strokeDasharray={dash} />);
  } else if (guide.shape === "rect" && pts.length >= 2) {
    const x = Math.min(pts[0][0], pts[1][0]), y = Math.min(pts[0][1], pts[1][1]);
    const rw = Math.abs(pts[1][0] - pts[0][0]), rh = Math.abs(pts[1][1] - pts[0][1]);
    shape = draw((s, sw, fill) => <rect x={x} y={y} width={rw} height={rh} {...common} fill={fill ?? "none"} stroke={s} strokeWidth={sw} />);
  } else if (guide.shape === "circle" && pts.length >= 2) {
    const r = Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]);
    shape = draw((s, sw, fill) => <circle cx={pts[0][0]} cy={pts[0][1]} r={r} {...common} fill={fill ?? "none"} stroke={s} strokeWidth={sw} />);
  } else if (pts.length >= 2) {
    const d = pts.map((p) => p.join(",")).join(" ");
    shape = draw((s, sw, fill) => <polygon points={d} {...common} fill={fill ?? "none"} stroke={s} strokeWidth={sw} />);
  }
  if (!shape) return null;
  return (
    <g>
      {shape}
      {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={3 * lw} fill={guide.color || "#fff"} stroke="#000" strokeWidth={lw} />)}
    </g>
  );
}

/** A bar on the timeline: an event's part inside this video. `end` null means it is still open. */
export interface Segment { key: number; start: number; end: number | null; label: string; carriedIn: boolean; carriedOut: boolean }

export function Timeline({
  frame, total, frameTimes, segments, onSeek, exact,
  playbackRate, onPlaybackRateChange, isPlaying, onTogglePlay, onStep,
}: {
  frame: number; total: number; frameTimes: number[]; segments: Segment[];
  onSeek: (frame: number) => void; exact: boolean;
  playbackRate?: number; onPlaybackRateChange?: (rate: number) => void;
  isPlaying?: boolean; onTogglePlay?: () => void; onStep?: (delta: number) => void;
}) {
  const { t } = useI18n();
  const trackRef = useRef<HTMLDivElement>(null);
  const pct = (f: number) => (total > 1 ? (f / (total - 1)) * 100 : 0);
  const seekFrom = (clientX: number) => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return;
    onSeek(Math.round(((clientX - rect.left) / rect.width) * (total - 1)));
  };
  const seconds = frameTimes[frame] ?? 0;
  // Events that overlap in time (several animals) go on separate lanes so their bars do not cover each other.
  const LANE = 26;
  const laneEnds: number[] = [];
  const placed = [...segments].sort((x, y) => x.start - y.start).map((s) => {
    const end = s.end ?? frame;
    const a = Math.min(s.start, end), b = Math.max(s.start, end);
    let lane = laneEnds.findIndex((e) => e < a);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = b;
    return { s, a, b, lane };
  });
  const height = Math.max(1, laneEnds.length) * LANE + 6;
  return (
    <div className="timeline">
      <div className="tc" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {onTogglePlay && (
            <button type="button" className="icon-btn" onClick={onTogglePlay} title="Space: Play/Pause"
                    style={{ minWidth: 28, height: 26, padding: "0 6px", background: "var(--km-surface)", color: "var(--km-primary)", border: "none", borderRadius: 4, fontWeight: 700, cursor: "pointer" }}>
              {isPlaying ? "⏸" : "▶"}
            </button>
          )}
          {onStep && (
            <>
              <button type="button" className="icon-btn" onClick={() => onStep(-1)} title="<: -1 frame"
                      style={{ height: 26, padding: "0 6px", background: "var(--km-surface)", color: "var(--km-primary)", border: "none", borderRadius: 4, cursor: "pointer" }}>◀</button>
              <button type="button" className="icon-btn" onClick={() => onStep(1)} title=">: +1 frame"
                      style={{ height: 26, padding: "0 6px", background: "var(--km-surface)", color: "var(--km-primary)", border: "none", borderRadius: 4, cursor: "pointer" }}>▶</button>
            </>
          )}
          <span>{formatTimecode(seconds)}</span>
          <span>{t("video.frame", { frame, total: Math.max(0, total - 1) })}</span>
          {!exact && <span title={t("video.approx")}>≈</span>}
        </div>
        {onPlaybackRateChange && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 13, opacity: 0.85 }}>{t("video.speed")}:</span>
            <div style={{ display: "flex", gap: 2 }}>
              {[0.5, 1, 1.5, 2].map((r) => (
                <button key={r} type="button" className="chip" aria-pressed={playbackRate === r}
                        onClick={() => onPlaybackRateChange(r)}
                        style={{ padding: "1px 6px", minHeight: 24, fontSize: 12 }}>
                  {r}x
                </button>
              ))}
            </div>
            <select value={playbackRate ?? 1} onChange={(e) => onPlaybackRateChange(Number(e.target.value))}
                    aria-label={t("video.speed")}
                    style={{ width: 68, height: 24, padding: "0 2px", fontSize: 12, background: "var(--km-surface)", color: "var(--km-primary)", fontWeight: 700, borderRadius: 4, border: "none", cursor: "pointer" }}>
              {[0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4].map((r) => (
                <option key={r} value={r}>{r}x</option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div className="track" ref={trackRef} style={{ height }}
           onMouseDown={(e) => {
             seekFrom(e.clientX);
             const move = (ev: MouseEvent) => seekFrom(ev.clientX);
             const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
             window.addEventListener("mousemove", move);
             window.addEventListener("mouseup", up);
           }}>
        {placed.map(({ s, a, b, lane }) => {
          return (
            <div key={s.key} className={`seg${s.end === null ? " pending" : ""}`}
                 style={{ left: `${pct(a)}%`, width: `${Math.max(0.5, pct(b) - pct(a))}%`, top: 4 + lane * LANE }}>
              {s.carriedIn ? "◀ " : ""}{s.label}{s.carriedOut ? " ▶" : ""}
            </div>
          );
        })}
        <div className="head" style={{ left: `calc(${pct(frame)}% - 1px)` }} />
      </div>
    </div>
  );
}

export function formatTimecode(seconds: number): string {
  const ms = Math.round(seconds * 1000);
  const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000), s = Math.floor((ms % 60000) / 1000);
  const pad = (n: number, l = 2) => String(n).padStart(l, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(ms % 1000, 3)}`;
}
