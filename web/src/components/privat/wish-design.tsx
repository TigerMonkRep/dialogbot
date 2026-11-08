"use client";
/** «Design ønskeseddel»: ten themes, a few safe adjustments and the owner's own cover, with a live preview on a phone
 *  and a desktop frame. The look is saved per wishlist (PUT /privat/tasks/{id}/design) and shown the same to everyone
 *  the list is shared with; it never changes Dialogbot's own design or another list. Only theme keys, #RRGGBB colours
 *  and a font key are sent – never CSS or HTML. Text over a cover always sits on a dark scrim, so it stays readable. */
import { useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";
import type { ApiError } from "@/lib/client";
import type { Task, WishDesign, WishDesignBody } from "@/lib/privat/api";
import THEMES_JSON from "@/lib/privat/wish-themes.json";
import { imgSrc } from "@/lib/privat/wish";
import { BIG, CHIP } from "./bits";
import { Ico } from "./icons";
import { usePrivat } from "./store";

type Palette = { accent: string; background: string; text: string; font: string };
export const THEMES = THEMES_JSON.themes as Record<string, Palette>;
export const THEME_KEYS = Object.keys(THEMES);
export const FONT_STACK: Record<string, string> = {
  outfit: "var(--font-display)",
  inter: "var(--font-body)",
  serif: "Georgia, 'Iowan Old Style', 'Times New Roman', ui-serif, serif",
  rounded: "ui-rounded, 'SF Pro Rounded', 'Arial Rounded MT Bold', 'Nunito', var(--font-display)",
};

// ---------------------------------------------------------------- contrast (WCAG), the same rules as the backend

function lum(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
export function contrast(a: string, b: string): number {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}
const HEX = /^#[0-9a-fA-F]{6}$/;

// ---------------------------------------------------------------- decorations (discreet, decorative only)

/** Small line motifs per theme, drawn in the accent colour at low opacity in the cover's corners. */
function Motif({ theme, color }: { theme: string; color: string }) {
  const s = { stroke: color, fill: "none", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const f = { fill: color };
  const shapes: Record<string, React.ReactNode> = {
    jul: <><path {...s} d="M20 6v28M8 13l24 14M8 27l24-14M16 8l4 4 4-4M16 32l4-4 4 4" /><path {...s} d="M64 18v16M56 22l16 8M56 30l16-8" /><circle {...f} cx="44" cy="10" r="1.6" /><circle {...f} cx="84" cy="34" r="1.4" /></>,
    foedselsdag: <><ellipse {...s} cx="18" cy="16" rx="8" ry="10" /><path {...s} d="M18 26c-2 6 3 8 0 14" /><ellipse {...s} cx="40" cy="12" rx="6" ry="8" /><path {...s} d="M40 20c2 5-3 7 0 12" /><path {...s} d="M60 10l3 3M70 22l-4 2M58 30l2-3M80 12l2 4" /></>,
    bryllup: <><circle {...s} cx="20" cy="22" r="9" /><circle {...s} cx="32" cy="22" r="9" /><path {...s} d="M56 30c6-10 14-14 26-14M62 26c0-5 3-8 7-9M70 22c1-4 4-6 8-6" /></>,
    konfirmation: <><path {...s} d="M20 34V12M12 20h16" /><path {...s} d="M48 14c4 0 6 3 10 3s6-3 10-3M48 24c4 0 6 3 10 3s6-3 10-3" /><circle {...f} cx="82" cy="10" r="1.5" /></>,
    barnedaab: <><path {...s} d="M10 26a7 7 0 0 1 7-7 9 9 0 0 1 17 2 6 6 0 0 1 0 12H14a5 5 0 0 1-4-7z" /><path {...s} d="M58 10c3 5 5 8 5 11a5 5 0 0 1-10 0c0-3 2-6 5-11z" /><circle {...f} cx="80" cy="24" r="1.5" /></>,
    babyshower: <><path {...s} d="M24 8a12 12 0 1 0 10 18 10 10 0 0 1-10-18z" /><circle {...f} cx="50" cy="12" r="2" /><circle {...f} cx="62" cy="24" r="1.5" /><circle {...f} cx="76" cy="14" r="2.2" /><circle {...f} cx="70" cy="34" r="1.4" /></>,
    student: <><path {...s} d="M8 18l18-8 18 8-18 8z" /><path {...s} d="M16 22v8c6 4 14 4 20 0v-8M44 18v10" /><path stroke={color} strokeWidth={2.4} d="M58 30h30M58 36h30" /></>,
    jubilaeum: <><path {...s} d="M14 34c-4-8-2-18 6-24M14 26c4-1 6-4 6-8M12 18c3 0 5-2 6-5M30 34c4-8 2-18-6-24" /><path {...s} d="M60 10l2 6 6 2-6 2-2 6-2-6-6-2 6-2zM80 26l1 3 3 1-3 1-1 3-1-3-3-1 3-1z" /></>,
    indflytning: <><path {...s} d="M8 22L24 10l16 12M12 20v14h24V20M20 34v-8h8v8" /><circle {...s} cx="60" cy="20" r="5" /><path {...s} d="M65 20h20M80 20v5M85 20v4" /></>,
    neutral: <><circle {...f} cx="12" cy="12" r="1.5" /><circle {...f} cx="28" cy="24" r="1.2" /><circle {...f} cx="48" cy="12" r="1.5" /></>,
  };
  return <svg viewBox="0 0 96 40" width="120" height="50" aria-hidden className="opacity-40">{shapes[theme] ?? shapes.neutral}</svg>;
}

// ---------------------------------------------------------------- the cover everybody sees

/** The wishlist's header: cover photo (crop/zoom/position) or the theme's background, title, greeting and date. */
export function WishCover({ title, design, compact = false }: { title: string; design: WishDesign; compact?: boolean }) {
  const t = useT("privat");
  const locale = useLocale();
  const cover = design.cover;
  const date = design.date ? new Intl.DateTimeFormat(HTML_LANG[locale], { day: "numeric", month: "long", year: "numeric" }).format(new Date(`${design.date}T12:00:00`)) : null;
  const onPhoto = !!cover;
  const fg = onPhoto ? "#FFFFFF" : design.text;
  return (
    <header data-testid="wish-cover" data-theme={design.theme}
      className={`relative overflow-hidden rounded-[18px] border-2 border-ink ${compact ? "min-h-[150px]" : "min-h-[180px] sm:min-h-[220px]"} flex flex-col justify-end`}
      style={{ background: design.background, color: fg, fontFamily: FONT_STACK[design.font] ?? FONT_STACK.outfit }}>
      {cover && (
        // eslint-disable-next-line @next/next/no-img-element -- the owner's own cover from our private bucket (signed link)
        <img src={imgSrc(compact ? cover.url_sm : cover.url)} alt="" className="absolute inset-0 w-full h-full object-cover"
          style={{ objectPosition: `${cover.x}% ${cover.y}%`, transform: `scale(${cover.zoom})`, transformOrigin: `${cover.x}% ${cover.y}%` }} />
      )}
      {onPhoto && <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.05) 0%, rgba(0,0,0,0.25) 45%, rgba(0,0,0,0.72) 100%)" }} aria-hidden />}
      {!onPhoto && <div className="absolute inset-x-0 top-0 h-2" style={{ background: design.accent }} aria-hidden />}
      {design.decorations && !onPhoto && (
        <>
          <div className="absolute top-3 right-3"><Motif theme={design.theme} color={design.accent} /></div>
          <div className="absolute bottom-2 left-2 rotate-180 hidden sm:block"><Motif theme={design.theme} color={design.accent} /></div>
        </>
      )}
      <div className="relative p-4 sm:p-5 flex flex-col gap-1">
        <span className="text-[12px] font-semibold uppercase tracking-[0.08em]" style={{ color: onPhoto ? "#FFFFFF" : design.accent }}>{t(`design.themes.${design.theme}`)}</span>
        <h2 className={`m-0 font-extrabold leading-[1.1] tracking-[-0.3px] [overflow-wrap:anywhere] ${compact ? "text-[22px]" : "text-[26px] sm:text-[32px]"}`}>{title}</h2>
        {design.subtitle && <p className="m-0 text-[15px] sm:text-[16px] [overflow-wrap:anywhere] opacity-95">{design.subtitle}</p>}
        {date && <p className="m-0 text-[14px] font-semibold opacity-95">{date}</p>}
      </div>
    </header>
  );
}

// ---------------------------------------------------------------- the editor

type Draft = { title: string; theme: string; accent: string | null; background: string | null; text: string | null; font: string | null; decorations: boolean;
  subtitle: string; date: string; cover: { key: string | null; url: string; url_sm: string; zoom: number; x: number; y: number } | null };

function fromTask(task: Task): Draft {
  const d = task.design;
  const theme = d?.theme && THEMES[d.theme] ? d.theme : "neutral";
  const ov = new Set(d?.overrides ?? []);
  return { title: task.title, theme, accent: ov.has("accent") ? d!.accent : null, background: ov.has("background") ? d!.background : null,
    text: ov.has("text") ? d!.text : null, font: ov.has("font") ? d!.font : null, decorations: d?.decorations ?? true,
    subtitle: d?.subtitle ?? "", date: d?.date ?? "", cover: d?.cover ? { ...d.cover, key: d.cover.key ?? null } : null };
}
function resolve(d: Draft): WishDesign {
  const b = THEMES[d.theme] ?? THEMES.neutral;
  return { theme: d.theme, accent: d.accent ?? b.accent, background: d.background ?? b.background, text: d.text ?? b.text, font: d.font ?? b.font,
    decorations: d.decorations, subtitle: d.subtitle.trim() || null, date: d.date || null,
    cover: d.cover ? { url: d.cover.url, url_sm: d.cover.url_sm, zoom: d.cover.zoom, x: d.cover.x, y: d.cover.y } : null };
}

export function DesignButton({ task }: { task: Task }) {
  const t = useT("privat");
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={CHIP} onClick={() => setOpen(true)} data-testid="design-open"><Ico name="palette" size={16} />{t("design.open")}</button>
      {open && <DesignEditor task={task} onClose={() => setOpen(false)} />}
    </>
  );
}

function DesignEditor({ task, onClose }: { task: Task; onClose: () => void }) {
  const t = useT("privat");
  const { api, refresh } = usePrivat();
  const [d, setD] = useState<Draft>(() => fromTask(task));
  const [view, setView] = useState<"mobile" | "desktop">("mobile");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const r = useMemo(() => resolve(d), [d]);
  const warn = [
    contrast(r.text, r.background) < 4.5 ? t("design.warnText") : null,
    contrast("#FFFFFF", r.accent) < 4.5 ? t("design.warnAccentLight") : null,
    contrast(r.accent, r.background) < 3 ? t("design.warnAccentBg") : null,
  ].filter(Boolean) as string[];
  const up = (p: Partial<Draft>) => { setD((x) => ({ ...x, ...p })); setErr(null); };
  const color = (k: "accent" | "background" | "text", v: string) => up({ [k]: HEX.test(v) ? v.toUpperCase() : null } as Partial<Draft>);
  const upload = async (file?: File) => {
    if (!file) return;
    setUploading(true); setErr(null);
    try {
      const res = await api.uploadCover(task.id, file);
      if (res.image) up({ cover: { key: res.key, url: res.image.url, url_sm: res.image.url_sm, zoom: 1, x: 50, y: 50 } });
    } catch (e) { setErr((e as ApiError).message); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  const save = async () => {
    if (!d.title.trim()) { setErr(t("design.titleRequired")); return; }
    setBusy(true); setErr(null);
    const body: WishDesignBody = { theme: d.theme, accent: d.accent, background: d.background, text: d.text, font: d.font, decorations: d.decorations,
      subtitle: d.subtitle.trim() || null, date: d.date || null,
      cover: d.cover?.key ? { key: d.cover.key, zoom: d.cover.zoom, x: d.cover.x, y: d.cover.y } : null };
    try { await api.saveDesign(task.id, { title: d.title.trim(), design: body }); await refresh(); onClose(); }
    catch (e) { const a = e as ApiError; setErr(a.field_errors?.[0]?.message || a.message); }
    finally { setBusy(false); }
  };
  const resetToTheme = () => up({ accent: null, background: null, text: null, font: null, decorations: true, cover: null });
  const sampleTask: Task = { ...task, title: d.title || task.title };
  const LBL = "text-[14px] font-semibold";
  return (
    <div className="fixed inset-0 z-50 bg-paper text-ink flex flex-col" role="dialog" aria-modal="true" aria-label={t("design.title")} data-testid="design-editor"
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      <div className="flex items-center gap-2 px-4 py-3 border-b-2 border-ink">
        <h2 className="m-0 flex-1 font-display font-extrabold text-[20px]">{t("design.title")}</h2>
        <button type="button" onClick={onClose} aria-label={t("design.cancel")} className="w-11 h-11 inline-flex items-center justify-center rounded-xl hover:bg-panel"><Ico name="close" /></button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto lg:overflow-hidden lg:grid lg:grid-cols-[420px_minmax(0,1fr)]">
        {/* controls */}
        <div className="p-4 flex flex-col gap-4 lg:overflow-y-auto lg:border-r-2 lg:border-ink">
          <section aria-labelledby="d-themes" className="flex flex-col gap-2">
            <h3 id="d-themes" className="m-0 text-[15px] font-bold">{t("design.themesTitle")}</h3>
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-labelledby="d-themes">
              {THEME_KEYS.map((k) => {
                const p = THEMES[k];
                return (
                  <button key={k} type="button" role="radio" aria-checked={d.theme === k} onClick={() => up({ theme: k, accent: null, background: null, text: null, font: null })}
                    className={`min-h-[64px] rounded-[14px] border-2 p-2 flex items-center gap-2 text-left ${d.theme === k ? "border-ink ring-2 ring-accent" : "border-line"}`}
                    style={{ background: p.background, color: p.text, fontFamily: FONT_STACK[p.font] }} data-testid={`theme-${k}`}>
                    <span className="w-6 h-6 rounded-full shrink-0 border border-black/10" style={{ background: p.accent }} aria-hidden />
                    <span className="text-[14px] font-semibold leading-tight">{t(`design.themes.${k}`)}</span>
                  </button>
                );
              })}
            </div>
          </section>
          <label className="flex flex-col gap-1"><span className={LBL}>{t("design.listTitle")}</span>
            <input className="min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px]" value={d.title} maxLength={300} onChange={(e) => up({ title: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1"><span className={LBL}>{t("design.subtitle")}</span>
            <input className="min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px]" value={d.subtitle} maxLength={160} onChange={(e) => up({ subtitle: e.target.value })} placeholder={t("design.subtitlePlaceholder")} />
          </label>
          <label className="flex flex-col gap-1"><span className={LBL}>{t("design.date")}</span>
            <input type="date" className="min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px]" value={d.date} onChange={(e) => up({ date: e.target.value })} />
          </label>
          <fieldset className="m-0 p-0 border-0 flex flex-col gap-2">
            <legend className="text-[15px] font-bold mb-1">{t("design.colors")}</legend>
            {(["accent", "background", "text"] as const).map((k) => (
              <label key={k} className="flex items-center gap-3 min-h-[44px]">
                <input type="color" value={r[k]} onChange={(e) => color(k, e.target.value)} className="w-11 h-11 rounded-lg border-2 border-ink cursor-pointer" aria-label={t(`design.${k}`)} />
                <span className="flex-1 text-[15px]">{t(`design.${k}`)}</span>
                <code className="text-[13px] text-muted">{r[k]}</code>
              </label>
            ))}
            {warn.map((w) => <p key={w} role="alert" className="m-0 text-[13px] text-danger font-semibold">{w}</p>)}
          </fieldset>
          <label className="flex flex-col gap-1"><span className={LBL}>{t("design.font")}</span>
            <select className="min-h-[48px] rounded-[14px] border-2 border-ink px-3 text-[16px]" value={r.font} onChange={(e) => up({ font: e.target.value })}>
              {Object.keys(FONT_STACK).map((k) => <option key={k} value={k} style={{ fontFamily: FONT_STACK[k] }}>{t(`design.fonts.${k}`)}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-3 min-h-[44px] cursor-pointer">
            <input type="checkbox" className="w-5 h-5" checked={d.decorations} onChange={(e) => up({ decorations: e.target.checked })} />
            <span className="text-[15px]">{t("design.decorations")}</span>
          </label>
          <section className="flex flex-col gap-2" aria-labelledby="d-cover">
            <h3 id="d-cover" className="m-0 text-[15px] font-bold">{t("design.cover")}</h3>
            <input ref={fileRef} id="cover-file" type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => upload(e.target.files?.[0])} />
            <div className="flex flex-wrap gap-2">
              <label htmlFor="cover-file" className={`${CHIP} cursor-pointer`}><Ico name="image" size={16} />{d.cover ? t("design.changeCover") : t("design.addCover")}</label>
              {d.cover && <button type="button" className={CHIP} onClick={() => up({ cover: null })}>{t("design.removeCover")}</button>}
            </div>
            {uploading && <p className="m-0 text-[13px] text-ink-soft" role="status">{t("wish.uploading")}</p>}
            <p className="m-0 text-[12px] text-muted">{t("design.coverHelp")}</p>
            {d.cover && (
              <div className="flex flex-col gap-2">
                {([["zoom", 1, 3, 0.05], ["x", 0, 100, 1], ["y", 0, 100, 1]] as const).map(([k, min, max, step]) => (
                  <label key={k} className="flex items-center gap-3 min-h-[44px]">
                    <span className="w-28 text-[14px]">{t(`design.crop.${k}`)}</span>
                    <input type="range" min={min} max={max} step={step} value={d.cover![k]} className="flex-1"
                      onChange={(e) => up({ cover: { ...d.cover!, [k]: Number(e.target.value) } })} />
                  </label>
                ))}
              </div>
            )}
          </section>
        </div>
        {/* live preview */}
        <div className="p-4 bg-panel flex flex-col gap-3 lg:overflow-y-auto" aria-label={t("design.preview")}>
          <div className="flex items-center gap-2" role="tablist" aria-label={t("design.preview")}>
            {(["mobile", "desktop"] as const).map((k) => (
              <button key={k} type="button" role="tab" aria-selected={view === k} onClick={() => setView(k)}
                className={`min-h-[44px] px-4 rounded-full border-2 border-ink text-[14px] font-semibold ${view === k ? "bg-ink text-paper" : "bg-paper"}`}>{t(`design.${k}`)}</button>
            ))}
          </div>
          <div className={`mx-auto w-full ${view === "mobile" ? "max-w-[390px]" : "max-w-[900px]"} rounded-[22px] border-2 border-ink p-3 transition-[max-width]`} style={{ background: r.background }} data-testid={`preview-${view}`}>
            <WishCover title={sampleTask.title} design={r} compact={view === "mobile"} />
            <div className={`mt-3 grid gap-2 ${view === "mobile" ? "grid-cols-1" : "grid-cols-3"}`}>
              {[0, 1, 2].slice(0, view === "mobile" ? 2 : 3).map((i) => (
                <div key={i} className="rounded-[14px] border-2 border-ink bg-paper p-2.5 flex flex-col gap-1.5" style={{ color: "#141414" }}>
                  <div className="aspect-[4/3] rounded-lg bg-panel flex items-center justify-center text-muted"><Ico name="gift" size={28} /></div>
                  <span className="font-semibold text-[14px]">{task.items[i]?.text ?? t("design.sampleWish")}</span>
                  <span className="self-start inline-flex items-center min-h-[36px] px-3 rounded-full text-[13px] font-semibold text-white" style={{ background: r.accent }}>{t("wish.seeProduct")}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="border-t-2 border-ink px-4 py-3 pb-[calc(12px+env(safe-area-inset-bottom))] flex flex-wrap items-center gap-2">
        {err && <p role="alert" className="m-0 w-full text-[14px] text-danger font-semibold">{err}</p>}
        <Button className={BIG} onClick={save} disabled={busy || uploading || warn.length > 0} data-testid="design-save">{busy ? t("wish.saving") : t("design.save")}</Button>
        <Button variant="outline" className="border-2" onClick={onClose}>{t("design.cancel")}</Button>
        <Button variant="outline" className="border-2" onClick={resetToTheme}>{t("design.reset")}</Button>
        <span className="text-[12px] text-muted">{t("design.resetNote")}</span>
      </div>
    </div>
  );
}
