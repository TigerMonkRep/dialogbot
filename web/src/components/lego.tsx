import { Icon } from "./ui";

/** Building-instruction pieces shared by the setup guide and the printed manual (public/materiale/opsaetningsmanual.html):
 *  a 2-stud brick with an icon, a numbered bag and the fat "press here" arrow. */

export type BrickColor = "lime" | "forest" | "sky" | "mint" | "white" | "ghost";
const FILL: Record<BrickColor, string> = { lime: "#d4ea82", forest: "#164e43", sky: "#80bbe0", mint: "#9bd1c3", white: "#ffffff", ghost: "#e7fef9" };

export function Brick({ icon, color = "lime", size = 44, optional = false }: { icon: string; color?: BrickColor; size?: number; optional?: boolean }) {
  const h = Math.round(size * 44 / 60);
  return (
    <span className="relative inline-block flex-shrink-0" style={{ width: size, height: h }} aria-hidden>
      <svg viewBox="0 0 60 44" width={size} height={h} className="absolute inset-0 overflow-visible" style={{ color: FILL[color] }}>
        <rect x="8" y="1" width="16" height="9" rx="2.5" fill="currentColor" />
        <rect x="36" y="1" width="16" height="9" rx="2.5" fill="currentColor" />
        <rect x="8" y="1" width="16" height="9" rx="2.5" fill="#000" fillOpacity=".1" />
        <rect x="36" y="1" width="16" height="9" rx="2.5" fill="#000" fillOpacity=".1" />
        <rect x="9.5" y="1.5" width="13" height="2.2" rx="1" fill="#fff" fillOpacity=".45" />
        <rect x="37.5" y="1.5" width="13" height="2.2" rx="1" fill="#fff" fillOpacity=".45" />
        <rect x="1" y="8" width="58" height="35" rx="3.5" fill="currentColor" stroke="#00362d" strokeOpacity={optional ? 0.55 : 0.35}
          strokeWidth="1.2" strokeDasharray={optional ? "3 2" : undefined} />
        <rect x="2" y="37" width="56" height="5" rx="2" fill="#000" fillOpacity=".14" />
        <rect x="3" y="9.5" width="54" height="2" rx="1" fill="#fff" fillOpacity=".4" />
      </svg>
      <span className={`absolute inset-x-0 flex justify-center ${color === "forest" ? "text-secondary-fixed" : "text-primary"}`} style={{ bottom: Math.round(h * 0.12) }}>
        <Icon name={icon} size={Math.round(size * 0.36)} />
      </span>
    </span>
  );
}

export type Part = { icon: string; label: string; color?: BrickColor; optional?: boolean; count?: string };

/** The "parts needed" callout at the top of a step. */
export function PartsBox({ parts, compact = false }: { parts: Part[]; compact?: boolean }) {
  if (parts.length === 0) return null;
  return (
    <div className="inline-flex flex-wrap items-end gap-space-md rounded-lg border-2 border-primary-fixed-dim bg-surface-container-lowest px-space-sm pt-space-sm pb-1.5" aria-label="Det skal du bruge">
      {parts.map((p) => (
        <span key={p.label} className="flex flex-col items-center gap-0.5 text-center" style={{ maxWidth: compact ? 64 : 80 }}>
          <Brick icon={p.icon} color={p.color} optional={p.optional} size={compact ? 32 : 40} />
          <span className="font-label-sm text-label-sm font-bold text-on-surface leading-none" style={{ fontFamily: "var(--font-display)" }}>{p.count ?? "1x"}</span>
          <span className="text-[11px] leading-tight text-on-surface-variant">{p.label}</span>
        </span>
      ))}
    </div>
  );
}

/** Numbered bag. tone: done = lime, active = forest, idle = muted. */
export function Bag({ n, tone = "active", size = 36 }: { n: number; tone?: "done" | "active" | "idle"; size?: number }) {
  const cls = tone === "done" ? "bg-secondary-container text-primary" : tone === "active" ? "bg-primary text-secondary-fixed" : "bg-surface-container-highest text-on-surface-variant";
  return (
    <span className="relative inline-flex flex-shrink-0" style={{ width: size * 0.9, height: size }} aria-hidden>
      <span className={`absolute rounded-t-md ${cls}`} style={{ top: 0, left: "22%", right: "22%", height: size * 0.18 }} />
      <span className={`absolute inset-x-0 bottom-0 rounded-md rounded-b-lg grid place-items-center font-extrabold ${cls}`}
        style={{ top: size * 0.12, fontFamily: "var(--font-display)", fontSize: size * 0.42 }}>
        {tone === "done" ? <Icon name="check" size={Math.round(size * 0.5)} /> : n}
      </span>
    </span>
  );
}

/** The big step number of a building instruction. */
export function StepNumber({ value, muted = false }: { value: string; muted?: boolean }) {
  return (
    <span className={`font-extrabold leading-[0.85] tracking-tighter tabular-nums flex-shrink-0 ${muted ? "text-outline" : "text-primary"}`}
      style={{ fontFamily: "var(--font-display)", fontSize: value.length > 3 ? 34 : 48, minWidth: 52 }}>{value}</span>
  );
}

/** The fat building-instruction arrow pointing right (flip with className="-scale-x-100"). */
export function BuildArrow({ size = 44, className = "" }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 64 40" width={size} height={size * 40 / 64} className={`flex-shrink-0 ${className}`} aria-hidden>
      <path d="M3 13h34V3l24 17-24 17V27H3z" fill="#d4ea82" stroke="#00362d" strokeWidth="3" strokeLinejoin="round" />
    </svg>
  );
}
