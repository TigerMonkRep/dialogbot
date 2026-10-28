import Link from "next/link";
import { cookies } from "next/headers";
import { backend } from "@/lib/api.server";
import { VIEWAS_COOKIE } from "@/lib/config";
import type { StepState } from "@/lib/setup.server";
import { Avatar, ViewAsBanner } from "./shell.client";
import { AssistantDock } from "./assistant";
import { SetupLater } from "./setup-later";
import { Icon, LogoMark } from "./ui";

export const STEP_LABEL = ["Virksomhed", "Kalender & systemer", "Test & tænd"] as const;

/** The header of the three setup steps: logo, workspace name and the stepper in place of the four pages. No bottom tabs. */
export async function SetupShell({ step, steps, workspaceName, children, wide = false, later = false, assistant }: { step: 1 | 2 | 3; steps: [StepState, StepState, StepState]; workspaceName?: string | null; children: React.ReactNode; wide?: boolean; later?: boolean; assistant?: { wsId: string; canChange: boolean } }) {
  const me = await backend<{ display_name: string; email: string }>("/auth/me").catch(() => null);
  let viewAs: { name: string; email: string } | null = null;
  try { const raw = (await cookies()).get(VIEWAS_COOKIE)?.value; if (raw) viewAs = JSON.parse(raw); } catch { /* ignore a broken cookie */ }
  return (
    <div className="min-h-dvh bg-panel text-ink flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-3 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-paper">Spring til indhold</a>
      {viewAs && <ViewAsBanner who={viewAs} />}
      <header className="sticky top-0 z-30 bg-paper border-b-2 border-ink pt-safe">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 min-h-16 flex items-center gap-3 md:gap-6">
          <Link href="/app" className="flex items-center gap-2.5 shrink-0" aria-label="Dialogbot – I dag">
            <LogoMark size={32} />
            <span className="hidden sm:inline font-display font-extrabold text-[20px] tracking-[-0.3px] text-ink">Dialogbot</span>
          </Link>
          {workspaceName && <span className="hidden lg:block truncate max-w-[220px] text-[14px] text-muted">{workspaceName}</span>}
          <nav aria-label="Opsætning" className="ml-auto">
            <ol className="flex items-center gap-1.5 sm:gap-3">
              {STEP_LABEL.map((label, i) => {
                const n = (i + 1) as 1 | 2 | 3;
                const st = steps[i];
                const here = n === step;
                return (
                  <li key={label}>
                    <Link href={`/opsaetning/${n}`} aria-label={`Trin ${n}: ${label}${st === "skipped" ? " (sprunget over)" : ""}`} aria-current={here ? "step" : undefined} className="inline-flex items-center gap-2 min-h-[44px] rounded-xl">
                      <span className={`w-9 h-9 rounded-[10px] border-2 border-ink inline-flex items-center justify-center font-display font-extrabold text-[15px] ${here ? "bg-highlight text-ink" : st === "done" ? "bg-ink text-paper" : "bg-paper text-ink"}`}>
                        {st === "done" && !here ? <Icon name="check" size={18} /> : n}
                      </span>
                      <span className={`${here ? "hidden sm:inline" : "hidden md:inline"} text-[14px] ${here ? "font-semibold text-ink" : "text-muted"}`}>{label}{st === "skipped" && !here ? " (sprunget over)" : ""}</span>
                    </Link>
                  </li>
                );
              })}
            </ol>
          </nav>
          <div className="shrink-0"><Avatar me={me} /></div>
        </div>
      </header>
      <main id="main" className="flex-grow w-full pb-28 sm:pb-10">
        <div className={`${wide ? "max-w-[1100px]" : "max-w-[1280px]"} mx-auto px-4 md:px-6 py-6 md:py-8`}>{children}{later && <p className="text-[13px] text-muted mt-6 hidden sm:block"><SetupLater /> – du finder alt igen under profil-ikonet → Alle indstillinger.</p>}</div>
      </main>
      {assistant && <AssistantDock wsId={assistant.wsId} canChange={assistant.canChange} step={step} column={false} />}
    </div>
  );
}
