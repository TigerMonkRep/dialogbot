import Link from "next/link";
import { Icon } from "./ui";
import { Bag } from "./lego";

export const INTENT_LABEL: Record<string, string> = { reception: "Reception", campaigns: "Kampagner", both: "Reception + kampagner" };

const STEPS: [string, string][] = [
  ["/onboarding/business", "Virksomhed & viden"],
  ["/onboarding/goals", "Mål & sprog"],
  ["/app/setup", "Personlig plan"],
];

/** Onboarding flow rail (Byggevejledning): yellow step squares, "Trin X af 3", preserved signup intent. */
export function FlowBar({ step, intent }: { step: 1 | 2 | 3; intent?: string | null }) {
  const [, label] = STEPS[step - 1];
  const next = STEPS[step];
  return (
    <>
      {/* Desktop */}
      <div className="hidden md:flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-paper border-2 border-ink p-5 rounded-2xl">
        <div className="flex items-center gap-4">
          <span className="inline-flex w-14 h-14 rounded-[14px] bg-highlight items-center justify-center font-display font-extrabold text-[30px] text-ink" aria-hidden>{step}</span>
          <div className="flex flex-col gap-0.5">
            <span className="eyebrow">Trin {step} af {STEPS.length} · Opsætning</span>
            <p className="font-display font-extrabold text-[24px] leading-[1.1] tracking-[-0.4px] text-ink">{label}</p>
          </div>
        </div>
        <div className="flex items-center gap-5 flex-wrap">
          {intent && (
            <div className="flex items-center gap-2.5 bg-panel border-[1.5px] border-ink px-3 py-1.5 rounded-xl">
              <Icon name="bookmark_added" size={18} className="text-accent" />
              <div className="flex flex-col">
                <span className="text-[12px] text-muted leading-none">Valgt ved tilmelding</span>
                <span className="text-[14px] font-semibold text-ink">{INTENT_LABEL[intent] ?? intent}</span>
              </div>
            </div>
          )}
          <nav aria-label="Onboarding-trin" className="flex items-center gap-2">
            {STEPS.map(([href, name], i) => {
              const n = i + 1;
              const tone = n < step ? "done" : n === step ? "active" : "idle";
              return (
                <span key={href} className="flex items-center gap-2">
                  {i > 0 && <span className={`w-8 h-[3px] rounded-full ${n <= step ? "bg-ink" : "bg-line"}`} />}
                  <Link href={href} aria-label={`Trin ${n}: ${name}`} aria-current={n === step ? "step" : undefined} className="rounded-lg"><Bag n={n} tone={tone} size={32} /></Link>
                </span>
              );
            })}
            <span className="text-[14px] text-muted ml-1">{next ? `Næste: ${next[1]}` : label}</span>
          </nav>
        </div>
      </div>
      {/* Mobil */}
      <div className="md:hidden flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="inline-flex w-9 h-9 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-[18px] text-ink flex-shrink-0" aria-hidden>{step}</span>
          <div className="flex flex-col min-w-0">
            <span className="eyebrow">Trin {step} af {STEPS.length}</span>
            <span className="text-[14px] font-semibold text-ink truncate">{label}</span>
          </div>
        </div>
        {intent && <span className="inline-flex items-center px-2.5 py-1 rounded-full border-[1.5px] border-ink bg-panel text-[12px] font-semibold text-ink flex-shrink-0">{INTENT_LABEL[intent] ?? intent}</span>}
      </div>
    </>
  );
}
