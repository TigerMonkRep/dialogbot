import Link from "@/i18n/link";
import { getRaw, getT } from "@/i18n/server";
import { cookies } from "next/headers";
import { backend } from "@/lib/api.server";
import { VIEWAS_COOKIE } from "@/lib/config";
import type { StepState } from "@/lib/setup.server";
import { Avatar, ViewAsBanner } from "./shell.client";
import { AssistantDock } from "./assistant";
import { SetupLater } from "./setup-later";
import { Icon, LogoMark } from "./ui";

/** The header of the three setup steps: logo, workspace name and the stepper in place of the four pages. No bottom tabs. */
export async function SetupShell({ step, steps, workspaceName, children, wide = false, later = false, assistant }: { step: 1 | 2 | 3; steps: [StepState, StepState, StepState]; workspaceName?: string | null; children: React.ReactNode; wide?: boolean; later?: boolean; assistant?: { wsId: string; canChange: boolean } }) {
  const t = await getT("setup.shell");
  const STEP_LABEL = (await getRaw())<string[]>("setup.shell.steps");
  const me = await backend<{ display_name: string; email: string }>("/auth/me").catch(() => null);
  let viewAs: { name: string; email: string } | null = null;
  try { const raw = (await cookies()).get(VIEWAS_COOKIE)?.value; if (raw) viewAs = JSON.parse(raw); } catch { /* ignore a broken cookie */ }
  return (
    <div className="min-h-dvh bg-panel text-ink app-type flex flex-col overflow-x-clip">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-3 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-paper">{t("skipToContent")}</a>
      {viewAs && <ViewAsBanner who={viewAs} />}
      <header className="sticky top-0 z-30 bg-paper border-b-2 border-ink pt-safe">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 min-h-14 sm:min-h-16 flex items-center gap-2 sm:gap-3 md:gap-6">
          <Link href="/app" className="flex items-center gap-2.5 shrink-0" aria-label={t("home")}>
            <LogoMark size={32} />
            <span className="hidden sm:inline font-display font-extrabold text-[20px] tracking-[-0.3px] text-ink">Dialogbot</span>
          </Link>
          {workspaceName && <span className="hidden lg:block truncate max-w-[220px] text-[14px] text-muted">{workspaceName}</span>}
          <nav aria-label={t("nav")} className="ml-auto">
            <ol className="flex items-center gap-1 sm:gap-3">
              {STEP_LABEL.map((label, i) => {
                const n = (i + 1) as 1 | 2 | 3;
                const st = steps[i];
                const here = n === step;
                return (
                  <li key={label}>
                    <Link href={`/opsaetning/${n}`} aria-label={`${t("stepAria", { n, label })}${st === "done" ? t("done") : st === "skipped" ? t("skipped") : ""}`} aria-current={here ? "step" : undefined} className="inline-flex items-center justify-center gap-2 min-w-[44px] min-h-[44px] rounded-xl">
                      <span className={`w-8 h-8 sm:w-9 sm:h-9 rounded-[10px] border-2 border-ink inline-flex items-center justify-center font-display font-extrabold text-[15px] ${here ? "bg-highlight text-ink" : st === "done" ? "bg-ink text-paper" : "bg-paper text-ink"}`}>
                        {/* done shows as done also on the step you are on (trin 1 filled in = ✓ at once) */}
                        {st === "done" ? <Icon name="check" size={18} /> : n}
                      </span>
                      <span className={`${here ? "hidden sm:inline" : "hidden md:inline"} text-[14px] ${here ? "font-semibold text-ink" : "text-muted"}`}>{label}{st === "skipped" && !here ? t("skipped") : ""}</span>
                    </Link>
                  </li>
                );
              })}
            </ol>
          </nav>
          <div className="shrink-0"><Avatar me={me} /></div>
        </div>
      </header>
      <main id="main" className="flex-grow w-full pb-action-bar sm:pb-10">
        <div className={`${wide ? "max-w-[1100px]" : "max-w-[1280px]"} mx-auto px-4 md:px-6 py-5 md:py-8`}>{children}{later && <p className="text-[13px] text-muted mt-6 hidden sm:block"><SetupLater />{t("laterNote")}</p>}</div>
      </main>
      {assistant && <AssistantDock wsId={assistant.wsId} canChange={assistant.canChange} step={step} column={false} />}
    </div>
  );
}
