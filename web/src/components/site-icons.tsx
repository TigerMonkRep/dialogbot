/** Inline stroke icons for the public site (paths copied from design-reference/byggevejledning). Plain functions, no
 *  client code, so both server and client components can use them. 2.2–2.5 px strokes, never emoji. */
type P = { size?: number; stroke?: string; width?: number; className?: string };

const base = ({ size = 20, stroke = "currentColor", width = 2.4, className }: P) => ({
  "aria-hidden": true as const, width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke, strokeWidth: width,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const, className,
});

export const ChatIcon = (p: P) => <svg {...base(p)}><path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 4z" /></svg>;
export const PhoneIcon = (p: P) => <svg {...base({ width: 2.2, ...p })}><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z" /></svg>;
export const MenuIcon = (p: P) => <svg {...base(p)}><path d="M4 5h16M4 12h16M4 19h10" /></svg>;
export const ArrowIcon = (p: P) => <svg {...base({ width: 2.5, ...p })}><path d="M5 12h14M13 6l6 6-6 6" /></svg>;
export const CheckIcon = (p: P) => <svg {...base({ width: 3, ...p })}><path d="M5 12l5 5L19 7" /></svg>;
export const CalendarIcon = (p: P) => <svg {...base({ width: 2.2, ...p })}><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>;
export const SmsIcon = (p: P) => <svg {...base({ width: 2.2, ...p })}><path d="M4 4h16v12H8l-4 4z" /><path d="M8 9h8M8 12h5" /></svg>;
export const SendIcon = (p: P) => <svg {...base({ width: 2.2, ...p })}><path d="M3 11l18-7-7 18-2-8z" /></svg>;
export const ChartIcon = (p: P) => <svg {...base({ width: 2.2, ...p })}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></svg>;
export const ClockIcon = (p: P) => <svg {...base({ width: 2.2, ...p })}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>;
export const PlusIcon = (p: P) => <svg {...base(p)}><path d="M12 5v14M5 12h14" /></svg>;
export const CloseIcon = (p: P) => <svg {...base({ width: 2.5, ...p })}><path d="M6 6l12 12M18 6 6 18" /></svg>;
export const ChevronIcon = (p: P) => <svg {...base({ width: 2.5, ...p })}><path d="M6 9l6 6 6-6" /></svg>;
/** Filled play triangle (the one filled icon in the set). */
export const PlayIcon = ({ size = 16, className }: { size?: number; className?: string }) => (
  <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}><path d="M7 5v14l12-7z" /></svg>
);
/** Short build arrow (→) used between parts in illustrations; 3 px ink. */
export const BuildArrowIcon = ({ className, flip = false }: { className?: string; flip?: boolean }) => (
  <svg aria-hidden width="30" height="20" viewBox="0 0 30 20" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className={className}>
    {flip ? <path d="M27 10H5M11 3l-7 7 7 7" /> : <path d="M3 10h22M19 3l7 7-7 7" />}
  </svg>
);
