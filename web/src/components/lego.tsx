import { Icon } from "./ui";

/** Building-instruction pieces (Byggevejledning v2) shared by the setup guide and the printed manual:
 *  a flat rounded block with an icon, a numbered square ("bag"), the big step number, the "Du skal bruge"
 *  parts box and the 3 px ink arrow. Flat colours only - no studs, no LEGO trade dress. */

/** Old palette names are kept for callers; they map onto the brand tokens. */
export type BrickColor = "lime" | "forest" | "sky" | "mint" | "white" | "ghost" | "accent" | "highlight" | "ink" | "panel";
const FILL: Record<BrickColor, { bg: string; fg: string }> = {
  lime: { bg: "var(--color-highlight)", fg: "var(--color-ink)" },
  highlight: { bg: "var(--color-highlight)", fg: "var(--color-ink)" },
  forest: { bg: "var(--color-ink)", fg: "var(--color-paper)" },
  ink: { bg: "var(--color-ink)", fg: "var(--color-paper)" },
  sky: { bg: "var(--color-accent-soft)", fg: "var(--color-accent-deep)" },
  mint: { bg: "var(--color-accent-soft)", fg: "var(--color-accent-deep)" },
  accent: { bg: "var(--color-accent)", fg: "var(--color-paper)" },
  white: { bg: "var(--color-paper)", fg: "var(--color-ink)" },
  ghost: { bg: "var(--color-panel)", fg: "var(--color-ink)" },
  panel: { bg: "var(--color-panel)", fg: "var(--color-ink)" },
};

/** Flat rounded block with an icon on it. `optional` = dashed outline ("not set up yet"). */
export function Brick({ icon, color = "lime", size = 44, optional = false }: { icon: string; color?: BrickColor; size?: number; optional?: boolean }) {
  const h = Math.round(size * 44 / 60);
  const f = FILL[color];
  return (
    <span className="relative inline-flex items-center justify-center flex-shrink-0 box-border" aria-hidden
      style={{ width: size, height: h, background: f.bg, color: f.fg, borderRadius: Math.max(8, Math.round(size * 0.2)), border: `${size >= 40 ? 2 : 1.5}px ${optional ? "dashed" : "solid"} var(--color-ink)` }}>
      <Icon name={icon} size={Math.round(size * 0.4)} />
    </span>
  );
}

export type Part = { icon: string; label: string; color?: BrickColor; optional?: boolean; count?: string };

/** The "Du skal bruge" callout at the top of a step: 1.5 px outline, eyebrow, chips with Outfit "1×" counts. */
export function PartsBox({ parts, compact = false }: { parts: Part[]; compact?: boolean }) {
  if (parts.length === 0) return null;
  return (
    <div className={`flex flex-col gap-2 rounded-xl border-[1.5px] border-ink bg-paper ${compact ? "px-3 py-2.5" : "px-3.5 py-3"}`} aria-label="Du skal bruge">
      <span className="eyebrow">Du skal bruge</span>
      <div className="flex flex-wrap gap-2">
        {parts.map((p) => (
          <span key={p.label} className={`inline-flex items-center gap-2 rounded-lg bg-panel font-medium text-ink ${compact ? "px-2 py-1 text-[13px]" : "px-2.5 py-1.5 text-[14px]"} ${p.optional ? "border-[1.5px] border-dashed border-ink" : ""}`}>
            <b className="font-display font-extrabold">{(p.count ?? "1x").replace(/x$/i, "×")}</b>
            <Icon name={p.icon} size={compact ? 15 : 17} className="text-accent" />
            <span>{p.label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Numbered square. active = Trin-gul with Outfit numeral, done = ink with a check, idle = panel with 1.5 px ink outline. */
export function Bag({ n, tone = "active", size = 36 }: { n: number; tone?: "done" | "active" | "idle"; size?: number }) {
  const cls = tone === "done" ? "bg-ink text-paper" : tone === "active" ? "bg-highlight text-ink" : "bg-panel text-ink border-[1.5px] border-ink";
  return (
    <span className={`inline-flex flex-shrink-0 items-center justify-center font-display font-extrabold ${cls}`} aria-hidden
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.25), fontSize: Math.round(size * 0.5) }}>
      {tone === "done" ? <Icon name="check" size={Math.round(size * 0.55)} /> : n}
    </span>
  );
}

/** The big step number: 56 px Trin-gul rounded square, Outfit 800. `muted` (finished step) = ink with white numeral. */
export function StepNumber({ value, muted = false }: { value: string; muted?: boolean }) {
  const long = value.length > 2;
  return (
    <span className={`inline-flex flex-shrink-0 items-center justify-center w-14 h-14 rounded-[14px] font-display font-extrabold tabular-nums tracking-tight ${muted ? "bg-ink text-paper" : "bg-highlight text-ink"}`}
      style={{ fontSize: long ? 18 : 30 }}>{value}</span>
  );
}

/** Building-instruction arrow pointing right, 3 px ink stroke (flip with className="-scale-x-100"). */
export function BuildArrow({ size = 44, className = "" }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 40 26" width={size} height={size * 26 / 40} className={`flex-shrink-0 text-ink ${className}`} aria-hidden fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 13h32M28 5l8 8-8 8" />
    </svg>
  );
}
