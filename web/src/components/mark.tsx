/** Accent kit (design: out/mockups2/accent-system.html, docs/brand.md). Three hand-drawn-looking marks that sit
 *  behind or under a word in a headline: a Trin-gul marker stroke, a thin ink line and an ellipse ring. Drawn by
 *  CSS (globals.css → ".mk"): the span is `position: relative; z-index: 0` and its ::before is an absolutely placed
 *  mask (fixed SVG coordinates) in the tone colour at z-index −1, so the mark lies under the glyphs but over the
 *  section background. No child element, so the headline's accessible name stays exactly the sentence.
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
    <span className={`mk mk-${kind} ${long ? "mk-long" : ""} ${className}`} style={{ "--mk-c": c } as React.CSSProperties}>
      {children}
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
