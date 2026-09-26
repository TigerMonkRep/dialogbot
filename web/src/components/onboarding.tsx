import Link from "next/link";
import { Icon } from "./ui";

export const INTENT_LABEL: Record<string, string> = { reception: "Reception", campaigns: "Kampagner", both: "Reception + kampagner" };

const STEPS: [string, string][] = [
  ["/onboarding/business", "Virksomhed & viden"],
  ["/onboarding/goals", "Mål & sprog"],
  ["/app/setup", "Personlig plan"],
];

/** Onboarding flow rail (Stitch a06_o01_o02): phase label, preserved signup intent and a 3-step indicator. */
export function FlowBar({ step, intent }: { step: 1 | 2 | 3; intent?: string | null }) {
  const [, label] = STEPS[step - 1];
  const next = STEPS[step];
  return (
    <>
      {/* Desktop */}
      <div className="hidden md:flex flex-col lg:flex-row lg:items-center justify-between gap-space-md bg-surface-container-lowest p-space-lg rounded-xl shadow-sm">
        <div className="flex items-center gap-space-md">
          <div className="w-10 h-10 rounded-xl bg-primary-container flex items-center justify-center text-secondary-fixed"><Icon name="rocket_launch" size={24} /></div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-label-sm text-label-sm uppercase tracking-wider text-primary font-bold">Onboarding</span>
              <span className="w-1 h-1 rounded-full bg-outline-variant" />
              <span className="font-label-sm text-label-sm text-on-surface-variant">Trin {step} af {STEPS.length}: {label}</span>
            </div>
            <p className="font-headline-sm text-headline-sm text-primary font-bold">Konfiguration af virksomhedens assistent</p>
          </div>
        </div>
        <div className="flex items-center gap-space-lg flex-wrap">
          {intent && (
            <div className="flex items-center gap-space-sm bg-surface-container px-space-md py-1.5 rounded-lg">
              <Icon name="bookmark_added" size={18} className="text-secondary" />
              <div className="flex flex-col">
                <span className="font-label-sm text-label-sm text-on-surface-variant leading-none">Beholdt hensigt (fra tilmelding):</span>
                <span className="font-label-md text-label-md text-primary font-bold">{INTENT_LABEL[intent] ?? intent}</span>
              </div>
            </div>
          )}
          <nav aria-label="Onboarding-trin" className="flex items-center gap-2">
            {STEPS.map(([href, name], i) => {
              const n = i + 1;
              const cls = n <= step ? "bg-primary text-on-primary shadow-sm" : n === step + 1 ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-highest text-on-surface-variant";
              return (
                <span key={href} className="flex items-center gap-2">
                  {i > 0 && <span className={`w-8 h-1 rounded-full ${n <= step + 1 ? "bg-primary" : "bg-surface-container-highest"}`} />}
                  <Link href={href} aria-label={`Trin ${n}: ${name}`} aria-current={n === step ? "step" : undefined} className={`flex items-center justify-center w-7 h-7 rounded-full font-label-sm text-label-sm font-bold ${cls}`}>{n}</Link>
                </span>
              );
            })}
            <span className="font-label-md text-label-md text-on-surface-variant ml-1">{next ? `Næste: ${next[1]}` : label}</span>
          </nav>
        </div>
      </div>
      {/* Mobil */}
      <div className="md:hidden flex items-center justify-between gap-space-xs">
        <div className="flex items-center gap-space-xs min-w-0">
          <span className="px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm font-semibold flex-shrink-0">Trin {step} af {STEPS.length}</span>
          <span className="font-label-sm text-label-sm text-on-surface-variant truncate">{label}</span>
        </div>
        {intent && <span className="flex items-center gap-1 font-label-sm text-label-sm text-primary font-semibold flex-shrink-0"><span className="w-1.5 h-1.5 rounded-full bg-secondary" />{INTENT_LABEL[intent] ?? intent}</span>}
      </div>
    </>
  );
}
