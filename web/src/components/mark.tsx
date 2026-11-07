/** Accent kit (design: out/mockups2/accent-system.html, docs/brand.md). Three hand-drawn-looking marks that sit
 *  behind or under a word in a headline: a Trin-gul marker stroke, a thin ink line and an ellipse ring. Inline SVG
 *  with fixed coordinates, `aria-hidden`, placed with CSS (globals.css → ".mk"): the span is `position: relative;
 *  z-index: 0`, the SVG `absolute; z-index: -1`, so the mark lies under the glyphs but over the section background.
 *  Em-based sizes, so it follows the font size from phone to desktop. No motion by default; reduced-motion safe.
 *
 *  Rules: marker = yellow on both audiences, max one per viewport; line = ink on Erhverv, orange on Privat; ring and
 *  arrow = ink (yellow only on a dark surface). Only on headlines – never body text, buttons, inputs, footer or logo.
 *  Wrap 1–3 words: the span is `white-space: nowrap`. `long` lets a longer phrase wrap on a phone (the mark is then
 *  hidden below sm, so the headline never overflows). Plain functions – usable from server and client components. */
type Kind = "marker" | "underline" | "ring";
type Tone = "yellow" | "ink" | "blue" | "orange";

const COLOR: Record<Tone, string> = { yellow: "#FFCF3F", ink: "#14213D", blue: "#2456F6", orange: "#E0521A" };

export function Mark({ kind, tone, long = false, className = "", children }: {
  kind: Kind; tone?: Tone; long?: boolean; className?: string; children: React.ReactNode;
}) {
  const c = COLOR[tone ?? (kind === "marker" ? "yellow" : "ink")];
  return (
    <span className={`mk mk-${kind} ${long ? "mk-long" : ""} ${className}`}>
      {children}
      {kind === "marker" && (
        <svg viewBox="0 0 100 20" preserveAspectRatio="none" aria-hidden="true" focusable="false"><path d="M2 1 L100 0 L98 20 L0 20 Z" fill={c} /></svg>
      )}
      {kind === "underline" && (
        <svg viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true" focusable="false"><path d="M2 3 L96 3" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" vectorEffect="non-scaling-stroke" /></svg>
      )}
      {kind === "ring" && (
        <svg viewBox="0 0 125 100" preserveAspectRatio="none" aria-hidden="true" focusable="false"><ellipse cx="62.5" cy="50" rx="60" ry="47" pathLength="360" strokeDasharray="340 20" strokeDashoffset="-20" fill="none" stroke={c} strokeWidth="3" strokeLinecap="round" vectorEffect="non-scaling-stroke" /></svg>
      )}
    </span>
  );
}

/** A slightly skewed step number / icon circle ("placed by hand"). Wraps StepNumber or any inline block. */
export function Tilted({ deg = 5, className = "", children }: { deg?: number; className?: string; children: React.ReactNode }) {
  return <span className={`inline-flex shrink-0 ${className}`} style={{ transform: `rotate(${deg}deg)` }}>{children}</span>;
}

/** The short curved ink arrow (64 × 28, 3 px) that points from the copy toward the picture. Desktop only by
 *  convention (`hidden lg:inline-flex`); decorative. */
export function ShortArrow({ className = "", flip = false }: { className?: string; flip?: boolean }) {
  return (
    <svg width="64" height="28" viewBox="0 0 64 28" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" focusable="false" className={`shrink-0 text-ink ${flip ? "-scale-x-100" : ""} ${className}`} style={{ transform: flip ? "scaleX(-1) rotate(8deg)" : "rotate(-8deg)" }}>
      <path d="M3 18 C 20 10, 40 9, 58 13" /><path d="M50 6 l8 7 -9 6" />
    </svg>
  );
}
