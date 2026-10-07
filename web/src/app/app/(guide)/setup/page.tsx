import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon, ProgressRing } from "@/components/ui";
import { Bag, BuildArrow, PartsBox, StepNumber, type Part } from "@/components/lego";
import { ExpandAll, GoalArchitecture, HelpSheet, ModeToggle, RunChecks, SkipButton, WhyBlock } from "./client";
import { BAGS, MANUAL_PDF, build } from "./build";
import { whyText } from "./why";

export type Task = { key: string; label: string; phase: string; explanation: string; destination: string; requirement_ids: string[]; required: boolean; status: string; blocked_by: { type: string; message: string }[]; can_skip: boolean; you_can_act: boolean; estimated_minutes: number; stale_checks: string[]; min_role: string };
type Check = { key: string; label: string; description: string; runnable: boolean; status: string; last_run_at: string | null; environment: string | null; stale_reason: string | null };
type Plan = { progress: { required_total: number; required_complete: number; percent: number; estimated_minutes_remaining: number }; next_action: Task | null; next_action_explanation: string | null; resume: { open_drafts: number; in_review: number }; tasks: Task[]; checks: Check[]; guidance_mode: string; product_intent: string };
type Goals = Record<string, unknown> & { product_intent: string; inbound_phone: boolean; webchat: boolean; callback: boolean; booking: boolean };
type Languages = { interface_language: string; default_conversation_language: string; enabled_conversation_languages: string[]; report_language: string };
type Capability = { key: string; label: string; status: string; environment: string; note: string };

const ROUTE: Record<string, string> = { "/onboarding/business#categories": "/onboarding/business", "/app/knowledge/catalogue": "/app/knowledge?tab=k03", "/app/knowledge/review": "/app/knowledge?tab=k05", "/app/setup/readiness": "/app/setup#checks", "/app/setup/launch": "/app/setup#checks", "/app/settings/integrations": "/app/bookings", "/onboarding/test": "/app/not-yet?area=Pr%C3%B8veopkald" };
export const href = (d: string) => ROUTE[d] ?? d;

const LANG: Record<string, string> = { da: "Dansk (DK)", en: "Engelsk (EN)", de: "Tysk (DE)", sv: "Svensk (SV)", no: "Norsk (NO)" };
const LANG_SHORT: Record<string, string> = { da: "Dansk", en: "Engelsk", de: "Tysk", sv: "Svensk", no: "Norsk" };
const code = (t: Task) => t.requirement_ids?.[0];
const done = (t: Task) => t.status === "complete" || t.status === "skipped";

type BagState = { n: number; name: string; text: string; tasks: Task[]; complete: number; total: number; tone: "done" | "active" | "idle" };
/** Groups the plan's tasks into the manual's five bags. Bags without tasks for these goals are left out. */
function bagStates(tasks: Task[], nextKey?: string): BagState[] {
  return BAGS.map((b) => {
    const order = (t: Task) => { const st = stepOf(tasks, t).step; return st.startsWith("K") ? 100 + parseInt(st.slice(1), 10) : parseFloat(st) + (st.charCodeAt(st.length - 1) - 96) / 100; };
    const ts = tasks.filter((t, i) => build(t, i + 1).bag === b.n).sort((x, y) => order(x) - order(y));
    const complete = ts.filter(done).length;
    const tone: BagState["tone"] = ts.length > 0 && complete === ts.length ? "done"
      : ts.some((t) => t.key === nextKey || done(t) || t.status === "in_progress") ? "active" : "idle";
    return { ...b, tasks: ts, complete, total: ts.length, tone };
  }).filter((b) => b.total > 0);
}
const stepOf = (tasks: Task[], t: Task) => build(t, tasks.indexOf(t) + 1);

/** G01 personal setup guide — Stitch "g01_g04_o03_o05_personlig_opsætningsguide" (desktop and mobil). All state is server-computed. */
export default async function SetupPage() {
  const ws = await requireWorkspace();
  const [plan, goals, profile, languages, caps] = await Promise.all([
    backend<Plan>(`/workspaces/${ws.id}/setup/plan`),
    backend<Goals>(`/workspaces/${ws.id}/goals`),
    backend<{ cvr: string | null; description: string }>(`/workspaces/${ws.id}/profile`),
    backend<Languages>(`/workspaces/${ws.id}/languages`),
    backend<{ items: Capability[] }>("/integrations/capabilities"),
  ]);
  const canEdit = ws.role !== "reader";
  const data = { ws, plan, goals, profile, languages, caps: caps.items, canEdit };
  return (
    <>
      <div className="md:hidden"><SetupMobile {...data} /></div>
      <div className="hidden md:block"><SetupDesktop {...data} /></div>
    </>
  );
}

type Data = { ws: { id: string; name: string }; plan: Plan; goals: Goals; profile: { cvr: string | null; description: string }; languages: Languages; caps: Capability[]; canEdit: boolean };

const intentText = (i: string) => (i === "both" ? "reception + kampagner" : i === "campaigns" ? "kampagner" : "reception");

function goalChips(g: Goals): [string, boolean][] {
  const reception = g.product_intent !== "campaigns";
  return [["Reception", reception && g.inbound_phone], ["Webchat", reception && g.webchat], ["Callback", reception && g.callback], ["Booking", reception && g.booking], ["Kampagner", g.product_intent !== "reception"]];
}

/* ───────────────────────────── Desktop ───────────────────────────── */

function SetupDesktop({ ws, plan, goals, profile, languages, caps, canEdit }: Data) {
  const p = plan.progress;
  const next = plan.next_action;
  const remaining = p.required_total - p.required_complete;
  const activeGoals = goalChips(goals).filter(([, on]) => on).length;
  const aiCap = caps.find((c) => c.key === "ai.conversation");
  const env = caps[0]?.environment;
  const passed = plan.checks.filter((c) => c.status === "passed").length;
  return (
    <div className="space-y-space-xl">
      {/* G01 breadcrumb, mode switcher & banner */}
      <div className="flex flex-col gap-space-md">
        <div className="flex flex-wrap items-center justify-between gap-space-md">
          <div className="flex flex-wrap items-center gap-space-xs font-label-md text-label-md text-on-surface-variant">
            <Link href="/app/setup" className="hover:text-primary transition-colors">Opsætning</Link>
            <Icon name="chevron_right" size={14} />
            <span className="text-primary font-semibold">Personlig plan for {ws.name}</span>
            {profile.cvr && <span className="ml-space-sm px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface font-label-sm text-label-sm tracking-wide">CVR: {profile.cvr}</span>}
          </div>
          <ModeToggle wsId={ws.id} mode={plan.guidance_mode} goals={goals} canEdit={canEdit} />
        </div>
        <div className="relative overflow-hidden rounded-xl bg-surface-container-lowest p-space-xl shadow-sm">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-lg relative z-10">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-space-sm">
                <span className="px-2 py-0.5 rounded-md bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-semibold uppercase tracking-wider">Aktiv opsætningshub</span>
                <span className="text-on-surface-variant font-label-sm text-label-sm">Beregnet ud fra dine {activeGoals} valgte driftsmål · {intentText(plan.product_intent)}</span>
              </div>
              <h1 className="font-headline-lg text-headline-lg text-primary font-bold tracking-tight">Din personlige køreplan: {p.required_complete} af {p.required_total} nødvendige trin er klar</h1>
              <p className="font-body-md text-body-md text-on-surface-variant max-w-2xl">
                {profile.description || "Udfyld virksomhedsprofilen, så planen kan tilpasses jeres ydelser."}{remaining > 0 && ` Færdiggør de sidste ${remaining} nødvendige trin.`}
              </p>
            </div>
            <div className="flex items-center gap-space-lg flex-shrink-0">
              <div className="flex items-center gap-space-md bg-surface-container-low px-space-lg py-space-md rounded-xl">
                <ProgressRing percent={p.percent} />
                <div className="flex flex-col">
                  <span className="font-label-lg text-label-lg font-bold text-primary">{p.required_complete} / {p.required_total} opgaver</span>
                  <span className="font-body-sm text-body-sm text-on-surface-variant">Estimeret resttid: {p.estimated_minutes_remaining} min</span>
                </div>
              </div>
            </div>
          </div>
          <div className="w-full bg-surface-container-highest h-2 rounded-full mt-space-lg overflow-hidden" role="progressbar" aria-valuenow={p.percent} aria-valuemin={0} aria-valuemax={100} aria-label="Fremdrift i opsætningen">
            <div className="bg-primary h-full rounded-full transition-all duration-500" style={{ width: `${p.percent}%` }} />
          </div>
          <div className="mt-space-lg"><BagStrip tasks={plan.tasks} nextKey={next?.key} /></div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        <div className="lg:col-span-8 flex flex-col gap-space-xl">
          {/* Next action spotlight */}
          <div className="relative rounded-xl bg-gradient-to-br from-primary-container to-primary text-on-primary p-space-xl shadow-md overflow-hidden">
            <div className="absolute -right-8 -bottom-8 w-48 h-48 bg-secondary-container/10 rounded-full blur-2xl pointer-events-none" />
            <div className="flex flex-col gap-space-md relative z-10">
              {next ? (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-space-xs">
                    <div className="flex items-center gap-space-xs">
                      <span className="px-2.5 py-1 rounded-full bg-secondary-fixed text-on-secondary-fixed font-label-sm text-label-sm font-bold uppercase tracking-wider flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-ping" />Næste handling{code(next) && ` (${code(next)})`}
                      </span>
                      <span className="text-primary-fixed-dim font-label-sm text-label-sm flex items-center gap-1"><Icon name="schedule" size={16} />ca. {next.estimated_minutes} min</span>
                    </div>
                    <span className="text-primary-fixed font-label-sm text-label-sm">{next.required ? "Nødvendigt trin" : "Valgfrit trin"}</span>
                  </div>
                  <div className="flex flex-wrap items-start gap-space-lg">
                    <span className="font-extrabold leading-[0.85] tracking-tighter text-secondary-fixed tabular-nums" style={{ fontFamily: "var(--font-display)", fontSize: 64 }}>{stepOf(plan.tasks, next).step}</span>
                    <div className="space-y-1 flex-1 min-w-[14rem]">
                      <span className="font-label-sm text-label-sm font-bold uppercase tracking-wider text-primary-fixed">Pose {stepOf(plan.tasks, next).bag} · {BAGS[stepOf(plan.tasks, next).bag - 1].name}</span>
                      <h2 className="font-headline-md text-headline-md text-on-primary font-bold">{next.label}</h2>
                      <p className="font-body-md text-body-md text-primary-fixed-dim leading-relaxed">{next.explanation}</p>
                    </div>
                    <PartsBox parts={stepOf(plan.tasks, next).parts} />
                  </div>
                  <WhyBlock task={next} />
                  <div className="flex flex-wrap items-center gap-space-md pt-space-xs">
                    <BuildArrow size={44} />
                    <Link href={href(next.destination)} className="px-space-xl py-2.5 rounded-xl bg-secondary-fixed text-on-secondary-fixed font-label-lg text-label-lg font-bold hover:brightness-105 transition-all shadow-sm flex items-center gap-space-xs">
                      <span>Start opgave</span><Icon name="arrow_forward" size={18} />
                    </Link>
                    <a href="#g04" className="px-space-lg py-2.5 rounded-xl bg-surface-container-lowest/15 hover:bg-surface-container-lowest/25 text-on-primary font-label-md text-label-md font-medium transition-colors flex items-center gap-space-xs">
                      <Icon name="assistant" size={18} /><span>Hjælp til dette trin</span>
                    </a>
                  </div>
                </>
              ) : (
                <div className="space-y-1">
                  <span className="px-2.5 py-1 rounded-full bg-secondary-fixed text-on-secondary-fixed font-label-sm text-label-sm font-bold uppercase tracking-wider">Næste handling</span>
                  <h2 className="font-headline-md text-headline-md text-on-primary font-bold pt-space-sm">Ingen åben handling for din rolle</h2>
                  <p className="font-body-md text-body-md text-primary-fixed-dim">De resterende trin afventer integrationer, der ikke er bygget endnu, eller en anden rolle. Se faserne nedenfor.</p>
                </div>
              )}
            </div>
          </div>

          {/* Building instructions: the plan's tasks in the manual's bags and step numbers */}
          <div id="build" className="rounded-xl bg-surface-container-low p-space-xl shadow-sm space-y-space-lg scroll-mt-24">
            <div className="flex flex-wrap items-start justify-between gap-space-sm">
              <div>
                <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Byggevejledning</span>
                <h3 className="font-headline-sm text-headline-sm text-primary font-bold mt-1">Byg jeres AI-receptionist pose for pose</h3>
                <p className="font-body-sm text-body-sm text-on-surface-variant">Samme poser, trinnumre og dele som i den trykte opsætningsmanual.</p>
              </div>
              <div className="flex items-center gap-space-md">
                <a href={MANUAL_PDF} target="_blank" rel="noopener" className="font-label-md text-label-md text-secondary hover:underline font-semibold flex items-center gap-1"><Icon name="picture_as_pdf" size={16} />Manual (PDF)</a>
                <ExpandAll target="phases" />
              </div>
            </div>
            <div id="phases" className="space-y-space-md">
              {bagStates(plan.tasks, next?.key).map((b) => <BagSection key={b.n} b={b} all={plan.tasks} nextKey={next?.key} wsId={ws.id} canEdit={canEdit} />)}
            </div>
          </div>

          {/* G02 & O03 goals */}
          <div className="rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Mål og kanalarkitektur</span>
                <h3 className="font-headline-sm text-headline-sm text-primary font-bold mt-1">Valgte driftsmål &amp; automatiseringer</h3>
              </div>
              <span className="font-label-sm text-label-sm text-on-surface-variant">{activeGoals} af 5 aktive</span>
            </div>
            <GoalArchitecture wsId={ws.id} goals={goals} canEdit={canEdit} />
            <div className="flex items-start gap-space-sm p-space-md rounded-lg bg-surface-container-high text-on-surface">
              <Icon name="verified_user" size={20} className="text-secondary flex-shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <span className="font-label-md text-label-md font-semibold text-primary">Arkitektur-regel:</span>
                <p className="font-body-sm text-body-sm text-on-surface-variant">Et arbejdsrum med kun kampagner får ingen telefon- eller kalendertrin. Callback hører under reception. Booking aktiveres kun, når du vælger det – og kræver en implementeret kalenderadapter.</p>
              </div>
            </div>
          </div>

          {/* O04 & O05 languages and persona */}
          <div className="rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
            <div>
              <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Sprog &amp; assistent</span>
              <h3 className="font-headline-sm text-headline-sm text-primary font-bold mt-1">Eksplicit adskillelse af 4 sprogniveauer</h3>
              <p className="font-body-sm text-body-sm text-on-surface-variant">Kontrollér sprogparametre separat for drift, AI-forståelse og ledelsesrapportering.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
              <LangTile label="a) Brugerfladesprog" value={LANG[languages.interface_language] ?? languages.interface_language} text="Administration, menupunkter og knapper i denne portal." />
              <LangTile label="b) Standardsamtalesprog" value={LANG[languages.default_conversation_language] ?? languages.default_conversation_language} text="Assistenten svarer som standard på dette sprog." />
              <div className="p-space-md rounded-xl bg-surface-container-low flex flex-col justify-between gap-space-sm">
                <div>
                  <span className="font-label-sm text-label-sm uppercase text-on-surface-variant">c) Tilladte samtalesprog</span>
                  <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                    {languages.enabled_conversation_languages.map((l) => <span key={l} className="px-2 py-0.5 rounded bg-surface-container text-on-surface font-label-sm text-label-sm font-semibold">{LANG[l] ?? l}</span>)}
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant mt-1.5">Sprog assistenten må skifte til, når kunden gør det.</p>
                </div>
                <Link href="/onboarding/languages" className="text-left font-label-sm text-label-sm text-secondary hover:underline flex items-center gap-1"><span>Skift sprog</span><Icon name="tune" size={14} /></Link>
              </div>
              <LangTile label="d) Daglig rapportsprog" value={LANG[languages.report_language] ?? languages.report_language} text="Daglige resuméer og ledelsesrapporter." />
            </div>
            {/* Persona — honest state until the AI/voice adapter exists */}
            <div className="rounded-xl bg-surface-container-low p-space-lg space-y-space-md">
              <div className="flex flex-wrap items-center justify-between gap-space-sm">
                <div className="flex items-center gap-space-sm">
                  <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-secondary-fixed"><Icon name="smart_toy" size={22} /></div>
                  <div>
                    <div className="flex flex-wrap items-center gap-space-xs">
                      <span className="font-label-lg text-label-lg font-bold text-primary">Assistent-persona</span>
                      <span className="px-2 py-0.5 rounded-full bg-surface-container-highest text-on-surface-variant font-label-sm text-label-sm font-bold">{aiCap?.status === "available" ? "Klar til opsætning" : "Ikke tilgængelig endnu"}</span>
                    </div>
                    <span className="font-body-sm text-body-sm text-on-surface-variant">{aiCap?.status === "available" ? aiCap.note : "Stemmemodel, velkomstreplik og prøvehør kræver AI-/stemmeadapteren, som ikke er tilkoblet."}</span>
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-space-sm font-body-sm text-body-sm">
                <div className="p-space-sm rounded-lg bg-surface-container-lowest flex items-start gap-space-xs">
                  <Icon name="rule" size={18} className="text-secondary mt-0.5" />
                  <div><strong className="text-primary font-semibold">Vidensbegrænsning:</strong><p className="text-on-surface-variant">Assistenten må kun bruge godkendt viden. Kladder og afviste svar bruges aldrig.</p></div>
                </div>
                <div className="p-space-sm rounded-lg bg-surface-container-lowest flex items-start gap-space-xs">
                  <Icon name="phone_forwarded" size={18} className="text-on-surface-variant mt-0.5" />
                  <div><strong className="text-primary font-semibold">Menneskelig overtagelse:</strong><p className="text-on-surface-variant">Regler for viderestilling kræver telefoni og vises ikke som aktive, før den er tilkoblet.</p></div>
                </div>
              </div>
            </div>
          </div>

        </div>

        {/* G04 contextual help + G05 checks */}
        <div className="lg:col-span-4 lg:sticky lg:top-20 flex flex-col gap-space-lg">
          <div id="g04" className="rounded-xl bg-surface-container-lowest p-space-lg shadow-sm space-y-space-md relative overflow-hidden scroll-mt-24">
            <div className="flex items-center justify-between pb-space-xs">
              <div className="flex items-center gap-space-xs"><Icon name="assistant" size={22} className="text-secondary" /><h3 className="font-headline-sm text-headline-sm text-primary font-bold">Hjælp mig videre</h3></div>
              <span className="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-semibold">Vejledning</span>
            </div>
            {next && (
              <div className="p-space-md rounded-lg bg-surface-container-low space-y-space-xs">
                <div className="flex items-center gap-1.5 font-label-md text-label-md font-bold text-primary"><Icon name="info" size={18} className="text-secondary" /><span>Om trinnet: {next.label}</span></div>
                <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed">{whyText(next)}</p>
              </div>
            )}
            <div className="space-y-space-xs">
              <span className="font-label-md text-label-md font-bold text-primary">Genoptag, hvor du slap</span>
              <p className="font-body-sm text-body-sm text-on-surface-variant">{plan.resume.open_drafts} åbne kladder · {plan.resume.in_review} til gennemgang. Alt gemmes serverside, så du kan fortsætte fra samme trin på en anden enhed.</p>
            </div>
            <div className="p-space-md rounded-lg bg-surface-container space-y-space-xs">
              <div className="flex items-center gap-space-xs font-label-md text-label-md font-bold text-primary"><Icon name="support_agent" size={18} /><span>Sidder du fast i opsætningen?</span></div>
              <p className="font-body-sm text-body-sm text-on-surface-variant">Hjælpen forklarer hvert trin og viser, hvor det gøres. Valgfrie trin kan springes over og tages senere.</p>
              <div className="pt-space-xs">
                <Link href="/app/help" className="w-full py-2 rounded-lg bg-surface-container-lowest hover:bg-surface-container-high text-primary font-label-md text-label-md font-semibold transition-colors flex items-center justify-center gap-1.5 shadow-sm">
                  <Icon name="help" size={18} className="text-secondary" /><span>Åbn hjælpen</span>
                </Link>
              </div>
            </div>
            <div className="border-t border-surface-container pt-space-sm space-y-1">
              <div className="font-label-sm text-label-sm uppercase text-on-surface-variant">Relevante sider</div>
              <Link className="flex items-center justify-between text-on-surface hover:text-primary font-body-sm text-body-sm py-1" href="/app/knowledge?tab=k05"><span>Gennemgå og godkend viden</span><Icon name="arrow_forward" size={16} /></Link>
              <Link className="flex items-center justify-between text-on-surface hover:text-primary font-body-sm text-body-sm py-1" href="/onboarding/languages"><span>Sprogniveauer</span><Icon name="arrow_forward" size={16} /></Link>
            </div>
          </div>

          <div id="checks" className="rounded-xl bg-surface-container-lowest p-space-lg shadow-sm space-y-space-md scroll-mt-24">
            <div className="flex items-start justify-between gap-space-sm">
              <div>
                <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Klarhedstjek</span>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">{passed} af {plan.checks.length} bestået</p>
              </div>
              {canEdit && <RunChecks wsId={ws.id} />}
            </div>
            <ul className="space-y-space-xs">
              {plan.checks.map((c) => (
                <li key={c.key} className="flex items-start justify-between gap-space-sm py-1">
                  <span className="flex items-start gap-2 font-body-sm text-body-sm text-on-surface">
                    <Icon name={c.status === "passed" ? "check_circle" : c.status === "failed" ? "error" : c.runnable ? "radio_button_unchecked" : "block"} size={16} className={`mt-0.5 ${c.status === "passed" ? "text-secondary" : c.status === "failed" ? "text-error" : "text-on-surface-variant"}`} />
                    <span>{c.label}{c.stale_reason && <span className="block font-label-sm text-label-sm text-error">{c.stale_reason}</span>}</span>
                  </span>
                  <CheckStatus c={c} />
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm flex items-center justify-between">
            <div className="flex items-center gap-space-sm">
              <span className={`w-2.5 h-2.5 rounded-full ${aiCap?.status === "available" ? "bg-secondary" : "bg-outline"}`} />
              <div>
                <p className="font-label-md text-label-md font-bold text-on-surface">Miljøstatus</p>
                <p className="font-body-sm text-body-sm text-on-surface-variant">AI-samtale: {aiCap?.status === "available" ? "tilkoblet" : "ikke tilkoblet"} · e-mail: {caps.find((c) => c.key === "email")?.status === "simulated" ? "simuleret" : "udbyder"}</p>
              </div>
            </div>
            {env && <span className="font-mono text-label-sm text-on-surface-variant">{env}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function LangTile({ label, value, text }: { label: string; value: string; text: string }) {
  return (
    <div className="p-space-md rounded-xl bg-surface-container-low flex flex-col justify-between gap-space-sm">
      <div>
        <span className="font-label-sm text-label-sm uppercase text-on-surface-variant">{label}</span>
        <p className="font-label-lg text-label-lg font-bold text-on-surface mt-1">{value}</p>
        <p className="font-body-sm text-body-sm text-on-surface-variant">{text}</p>
      </div>
      <Link href="/onboarding/languages" className="text-left font-label-sm text-label-sm text-secondary hover:underline flex items-center gap-1"><span>Skift sprog</span><Icon name="tune" size={14} /></Link>
    </div>
  );
}

function CheckStatus({ c }: { c: Check }) {
  const [label, cls] = c.status === "passed" ? ["Bestået", "text-secondary font-semibold"] : c.status === "failed" ? ["Fejlet", "text-error font-semibold"] : c.status === "stale" ? ["Forældet", "text-error"] : c.runnable ? ["Ikke kørt", "text-on-surface-variant"] : ["Kræver integration", "text-on-surface-variant"];
  return <span className={`font-label-sm text-label-sm flex-shrink-0 ${cls}`}>{label}</span>;
}

const STATUS_TEXT: Record<string, string> = { complete: "Klar", skipped: "Sprunget over", not_available: "Ikke tilgængelig endnu", blocked: "Blokeret", in_progress: "I gang", not_started: "Ikke startet" };

function BagSection({ b, all, nextKey, wsId, canEdit }: { b: BagState; all: Task[]; nextKey?: string; wsId: string; canEdit: boolean }) {
  const holdsNext = b.tasks.some((t) => t.key === nextKey);
  return (
    <details open={holdsNext || b.tone === "active"} className="group rounded-xl bg-surface-container-lowest overflow-hidden shadow-sm">
      <summary className="p-space-md flex items-center justify-between gap-space-md cursor-pointer hover:bg-surface-container-low transition-colors list-none [&::-webkit-details-marker]:hidden">
        <div className="flex items-center gap-space-md min-w-0">
          <Bag n={b.n} tone={b.tone} size={40} />
          <div className="min-w-0">
            <span className="font-label-sm text-label-sm font-bold uppercase tracking-wider text-secondary">Pose {b.n}</span>
            <h4 className="font-headline-sm text-headline-sm text-primary font-bold leading-tight">{b.name}</h4>
            <p className="font-body-sm text-body-sm text-on-surface-variant">{b.text}</p>
          </div>
        </div>
        <div className="flex items-center gap-space-md flex-shrink-0">
          <span className="flex gap-1" aria-label={`${b.complete} af ${b.total} trin klar`}>
            {b.tasks.map((t) => <span key={t.key} className={`w-4 h-1.5 rounded-full ${done(t) ? "bg-primary" : t.key === nextKey ? "bg-secondary-fixed-dim" : "bg-surface-container-highest"}`} />)}
          </span>
          <span className={`px-2.5 py-1 rounded-full font-label-sm text-label-sm font-semibold ${b.tone === "done" ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-highest text-on-surface"}`}>{b.complete}/{b.total}{b.tone === "done" ? " Færdig" : ""}</span>
          <Icon name="expand_more" size={20} className="text-on-surface-variant transition-transform group-open:rotate-180" />
        </div>
      </summary>
      <div className="px-space-md pb-space-md space-y-space-sm">
        {b.tasks.map((t) => <StepCard key={t.key} t={t} step={stepOf(all, t).step} parts={stepOf(all, t).parts} isNext={t.key === nextKey} wsId={wsId} canEdit={canEdit} />)}
        {b.tone === "done" && <p className="flex items-center gap-1.5 font-label-md text-label-md font-bold text-secondary pt-1"><Icon name="check_circle" size={18} filled />Pose {b.n} færdig</p>}
      </div>
    </details>
  );
}

function StepCard({ t, step, parts, isNext, wsId, canEdit }: { t: Task; step: string; parts: Part[]; isNext: boolean; wsId: string; canEdit: boolean }) {
  const finished = done(t);
  if (finished) return (
    <div className="rounded-lg px-space-md py-2 flex items-center gap-space-md bg-surface">
      <span className="w-10 text-center font-extrabold tabular-nums tracking-tighter text-outline text-xl" style={{ fontFamily: "var(--font-display)" }}>{step}</span>
      <Icon name={t.status === "skipped" ? "skip_next" : "check_circle"} size={18} filled={t.status === "complete"} className={t.status === "skipped" ? "text-on-surface-variant" : "text-secondary"} />
      <span className="flex-1 min-w-0 font-body-sm text-body-sm text-on-surface-variant truncate">{t.label}</span>
      <span className={`font-label-sm text-label-sm ${t.status === "skipped" ? "text-on-surface-variant" : "text-secondary font-bold"}`}>{STATUS_TEXT[t.status]}</span>
      {t.can_skip && canEdit && t.status === "skipped" && <SkipButton wsId={wsId} taskKey={t.key} unskip />}
    </div>
  );
  const actionable = t.you_can_act && !finished && t.status !== "not_available";
  return (
    <div className={`rounded-xl p-space-md flex gap-space-md border ${isNext ? "border-2 border-primary bg-secondary-container/25" : "border-surface-container-high bg-surface"} ${finished ? "opacity-75" : ""}`}>
      <div className="flex flex-col items-center gap-space-sm pt-1">
        <StepNumber value={step} muted={finished} />
        {finished && <Icon name="check_circle" size={22} filled className="text-secondary" />}
      </div>
      <div className="flex-1 min-w-0 space-y-space-sm">
        <div className="flex flex-wrap items-start justify-between gap-space-sm">
          <div className="space-y-1 min-w-0">
            <h5 className={`font-label-lg text-label-lg font-bold ${finished ? "text-on-surface-variant" : "text-primary"}`}>{t.label}</h5>
            <div className="flex flex-wrap gap-1.5">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-container text-primary font-label-sm text-label-sm"><Icon name="timer" size={13} />{t.estimated_minutes} min</span>
              {!t.required && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-dashed border-primary-fixed-dim bg-surface-container-lowest text-primary font-label-sm text-label-sm"><Icon name="add_circle" size={13} />Valgfrit</span>}
              {t.min_role === "admin" && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary text-secondary-fixed font-label-sm text-label-sm"><Icon name="shield_person" size={13} />Ejer/admin</span>}
              {isNext && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-secondary-fixed text-on-secondary-fixed font-label-sm text-label-sm font-bold">Næste trin</span>}
            </div>
          </div>
          {!finished && <PartsBox parts={parts} compact />}
        </div>
        {!finished && <p className="font-body-sm text-body-sm text-on-surface-variant">{t.explanation}</p>}
        {t.blocked_by.map((b, i) => <p key={i} className="flex items-start gap-1.5 rounded-lg bg-tertiary-fixed/60 px-space-sm py-1.5 font-label-sm text-label-sm text-on-surface"><Icon name="lock" size={14} className="mt-0.5" />{b.message}</p>)}
        {t.stale_checks.length > 0 && <p className="font-label-sm text-label-sm text-error">Forældede tjek: {t.stale_checks.join(", ")} – kør tjek igen.</p>}
        <div className="flex flex-wrap items-center gap-space-sm">
          {actionable
            ? <span className="flex items-center gap-space-xs">{isNext && <BuildArrow size={36} />}<Link href={href(t.destination)} className={`px-space-md py-1.5 rounded-full font-label-md text-label-md font-bold ${isNext ? "bg-primary text-on-primary hover:bg-primary-container" : "bg-surface-container text-primary hover:bg-surface-container-high"}`}>{isNext ? "Byg dette trin" : "Åbn"}</Link></span>
            : <span className={`font-label-sm text-label-sm ${finished ? "text-secondary font-bold" : "text-on-surface-variant"}`}>{STATUS_TEXT[t.status] ?? t.status}</span>}
          {t.can_skip && canEdit && t.status !== "complete" && <SkipButton wsId={wsId} taskKey={t.key} unskip={t.status === "skipped"} />}
        </div>
      </div>
    </div>
  );
}

/** The five bags as a strip under the progress bar. */
function BagStrip({ tasks, nextKey }: { tasks: Task[]; nextKey?: string }) {
  return (
    <ol className="flex flex-wrap gap-x-space-lg gap-y-space-sm" aria-label="Poser">
      {bagStates(tasks, nextKey).map((b) => (
        <li key={b.n}>
          <a href="#build" className="flex items-center gap-space-sm rounded-lg hover:bg-surface-container-low pr-2">
            <Bag n={b.n} tone={b.tone} size={30} />
            <span className="flex flex-col leading-tight">
              <span className={`font-label-md text-label-md font-bold ${b.tone === "idle" ? "text-on-surface-variant" : "text-primary"}`}>{b.name}</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">{b.complete}/{b.total} trin</span>
            </span>
          </a>
        </li>
      ))}
    </ol>
  );
}

/* ───────────────────────────── Mobil ───────────────────────────── */

function SetupMobile({ ws, plan, goals, languages, canEdit }: Data) {
  const p = plan.progress;
  const next = plan.next_action;
  const chips = goalChips(goals);
  const passed = plan.checks.filter((c) => c.status === "passed").length;
  const talk = [languages.default_conversation_language, ...languages.enabled_conversation_languages.filter((l) => l !== languages.default_conversation_language)].map((l) => l.toUpperCase()).join(" / ");
  return (
    <div className="flex flex-col">
      <section className="pb-space-sm flex flex-col gap-space-sm">
        <div className="flex items-center justify-between gap-space-xs">
          <div className="flex items-center gap-space-xs min-w-0">
            <span className="px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm truncate">{ws.name}</span>
          </div>
          <div className="flex items-center gap-1 bg-surface-container-lowest px-2 py-1 rounded-full shadow-sm flex-shrink-0">
            <Icon name="verified" size={15} className="text-primary" />
            <span className="font-label-sm text-label-sm text-primary font-semibold">{p.required_complete} af {p.required_total} klar</span>
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <h1 className="font-headline-lg-mobile text-headline-lg-mobile text-primary tracking-tight">Opsætningsguide</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Tilpas Dialogbot til {ws.name}. Ca. {p.estimated_minutes_remaining} min tilbage af de nødvendige trin.</p>
        </div>
        <div className="w-full bg-surface-container-highest h-2 rounded-full overflow-hidden p-0.5" role="progressbar" aria-valuenow={p.percent} aria-valuemin={0} aria-valuemax={100} aria-label="Fremdrift i opsætningen">
          <div className="bg-primary-container h-full rounded-full transition-all duration-500 ease-out" style={{ width: `${p.percent}%` }} />
        </div>
      </section>

      {!next && (
        <section className="py-space-xs">
          <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-md flex items-start gap-space-xs">
            <div className="w-8 h-8 rounded-lg bg-surface-container-high text-on-surface-variant flex items-center justify-center flex-shrink-0"><Icon name="hourglass_empty" size={18} /></div>
            <div className="flex flex-col">
              <span className="font-label-sm text-label-sm uppercase tracking-wider text-secondary font-bold">Anbefalet næste handling</span>
              <span className="font-headline-sm text-headline-sm text-primary">Ingen åben handling for din rolle</span>
              <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">De resterende trin afventer integrationer, der ikke er bygget endnu, eller en anden rolle.</p>
            </div>
          </div>
        </section>
      )}
      {next && (
        <section className="py-space-xs">
          <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-md flex flex-col gap-space-md relative overflow-hidden">
            <div className="absolute -right-10 -bottom-10 w-32 h-32 rounded-full bg-secondary-container/30 pointer-events-none" />
            <div className="flex items-start justify-between gap-space-xs relative">
              <div className="flex items-center gap-space-xs">
                <Bag n={stepOf(plan.tasks, next).bag} size={32} />
                <div className="flex flex-col">
                  <span className="font-label-sm text-label-sm uppercase tracking-wider text-secondary font-bold">Anbefalet næste handling</span>
                  <span className="font-headline-sm text-headline-sm text-primary">{next.label}</span>
                </div>
              </div>
              <StepNumber value={stepOf(plan.tasks, next).step} />
            </div>
            <div className="bg-surface-container-low rounded-lg p-space-sm flex items-start gap-space-xs relative">
              <Icon name="psychology_alt" size={18} className="text-primary-container mt-0.5" />
              <div className="flex flex-col">
                <span className="font-label-md text-label-md text-primary font-semibold">Hvorfor nu?</span>
                <p className="font-body-sm text-body-sm text-on-surface-variant leading-snug">{whyText(next)}</p>
              </div>
            </div>
            <div className="flex items-center justify-between p-2 rounded-lg bg-surface-container text-on-surface relative">
              <div className="flex items-center gap-2 min-w-0"><Icon name="schedule" size={18} className="text-outline" /><span className="font-label-md text-label-md truncate">{next.phase}</span></div>
              <span className="font-label-sm text-label-sm text-primary font-semibold flex-shrink-0">ca. {next.estimated_minutes} min</span>
            </div>
            <PartsBox parts={stepOf(plan.tasks, next).parts} compact />
            <Link href={href(next.destination)} className="w-full min-h-11 px-space-sm rounded-lg bg-primary-container text-on-primary font-label-lg text-label-lg flex items-center justify-center gap-space-xs shadow-sm active:scale-[0.98] transition-transform relative">
              <span>Fortsæt opsætning: {next.label}</span><Icon name="arrow_forward" size={18} />
            </Link>
          </div>
        </section>
      )}

      <section className="pt-space-md flex flex-col gap-space-xs">
        <div className="flex items-center justify-between">
          <span className="font-label-lg text-label-lg text-primary font-semibold">Aktiverede mål</span>
          <span className="font-label-sm text-label-sm text-on-surface-variant">{chips.filter(([, on]) => on).length} af {chips.length} aktive</span>
        </div>
        <div className="flex gap-space-xs overflow-x-auto pb-1 no-scrollbar -mx-margin px-margin">
          {chips.map(([label, on]) => (
            <Link key={label} href="/onboarding/goals" aria-label={`${label}: ${on ? "aktiv" : "ikke aktiv"}`} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full flex-shrink-0 ${on ? "bg-surface-container-lowest shadow-sm" : "bg-surface-container text-outline"}`}>
              <Icon name={on ? "check_circle" : "radio_button_unchecked"} size={16} className={on ? "text-secondary" : ""} />
              <span className={`font-label-md text-label-md ${on ? "text-primary" : "text-on-surface-variant"}`}>{label}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="pt-space-md">
        <div className="bg-surface-container rounded-xl p-space-md flex flex-col gap-space-sm shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5"><Icon name="translate" size={18} className="text-primary" /><span className="font-label-lg text-label-lg text-primary font-semibold">Sprogindstillinger</span></div>
            <Link href="/onboarding/languages" className="font-label-sm text-label-sm text-primary font-bold hover:underline flex items-center gap-0.5"><span>Rediger</span><Icon name="chevron_right" size={14} /></Link>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {([["Grænseflade", LANG_SHORT[languages.interface_language] ?? languages.interface_language, "Admin & app"], ["Samtale", talk, "Tilladte sprog"], ["Rapporter", LANG_SHORT[languages.report_language] ?? languages.report_language, "Daglige resuméer"]] as const).map(([k, v, s]) => (
              <div key={k} className="bg-surface-container-lowest rounded-lg p-2 flex flex-col gap-0.5">
                <span className="font-label-sm text-label-sm text-on-surface-variant">{k}</span>
                <div className="flex items-center gap-1 mt-0.5"><span className="font-label-md text-label-md text-primary font-bold">{v}</span><span className="w-1.5 h-1.5 rounded-full bg-secondary" /></div>
                <span className="font-label-sm text-[10px] text-outline leading-tight">{s}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="pt-space-md flex flex-col gap-space-md">
        <div className="flex items-center justify-between">
          <h2 className="font-headline-sm text-headline-sm text-primary">Byggevejledning</h2>
          <a href={MANUAL_PDF} target="_blank" rel="noopener" className="font-label-sm text-label-sm text-secondary font-bold flex items-center gap-1"><Icon name="picture_as_pdf" size={14} />Manual (PDF)</a>
        </div>
        {bagStates(plan.tasks, next?.key).map((b) => (
          <div key={b.n} className="flex flex-col gap-2">
            <div className="flex items-center gap-space-sm">
              <Bag n={b.n} tone={b.tone} size={30} />
              <div className="flex flex-col leading-tight min-w-0">
                <span className="font-label-sm text-label-sm font-bold uppercase tracking-wider text-secondary">Pose {b.n} · {b.complete}/{b.total}</span>
                <span className="font-label-lg text-label-lg font-bold text-primary">{b.name}</span>
              </div>
            </div>
            <ul className="flex flex-col gap-2">
              {b.tasks.map((t) => <MobileTask key={t.key} t={t} step={stepOf(plan.tasks, t).step} isNext={t.key === next?.key} />)}
            </ul>
          </div>
        ))}
      </section>

      <section id="checks" className="pt-space-md scroll-mt-20">
        <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm flex items-center justify-between gap-space-sm">
          <div className="flex flex-col">
            <span className="font-label-lg text-label-lg text-primary font-semibold">Klarhedstjek</span>
            <span className="font-body-sm text-body-sm text-on-surface-variant">{passed} af {plan.checks.length} bestået · {plan.checks.filter((c) => !c.runnable).length} kræver integration</span>
          </div>
          {canEdit && <RunChecks wsId={ws.id} compact />}
        </div>
      </section>

      <section className="pt-space-md">
        <div className="rounded-xl bg-gradient-to-r from-primary-container to-primary text-on-primary p-space-md shadow-md flex flex-col gap-space-sm relative overflow-hidden">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg bg-surface-container-lowest/15 flex items-center justify-center"><Icon name="support_agent" size={20} className="text-secondary-container" /></div>
            <div className="flex flex-col">
              <span className="font-label-sm text-label-sm text-secondary-fixed uppercase tracking-wider font-semibold">Support &amp; vejledning</span>
              <span className="font-headline-sm text-headline-sm text-on-primary">Brug for hjælp?</span>
            </div>
          </div>
          <p className="font-body-sm text-body-sm text-on-primary-container leading-relaxed">Få en forklaring på det aktuelle trin og genveje til de sider, der løser det.</p>
          <HelpSheet next={next ? { label: next.label, why: whyText(next), href: href(next.destination) } : null} />
        </div>
      </section>
    </div>
  );
}

function MobileTask({ t, step, isNext }: { t: Task; step: string; isNext: boolean }) {
  const look: Record<string, [string, string, string, string]> = {
    // [circle classes, icon, pill classes, pill text]
    complete: ["bg-secondary-container text-on-secondary-fixed-variant", "check", "bg-surface-container-high text-primary", "Klar"],
    skipped: ["bg-surface-container text-outline", "skip_next", "bg-surface-container text-outline", "Sprunget over"],
    in_progress: ["bg-secondary-fixed text-on-secondary-fixed", "sync", "bg-secondary-container text-on-secondary-container font-bold", "I gang"],
    not_started: [isNext ? "bg-secondary-fixed text-on-secondary-fixed" : "bg-surface-container-low text-primary", isNext ? "bolt" : "radio_button_unchecked", isNext ? "bg-secondary-container text-on-secondary-container font-bold" : "bg-surface-container text-on-surface-variant", isNext ? "Næste" : "Ikke startet"],
    blocked: ["bg-error-container text-error", "lock", "bg-error-container text-error", "Blokeret"],
    not_available: ["bg-surface-container text-outline", "block", "bg-surface-container text-on-surface-variant", "Ikke tilgængelig"],
  };
  const [circle, icon, pill, text] = look[t.status] ?? look.not_started;
  const sub = t.blocked_by[0]?.message ?? t.explanation;
  const body = (
    <div className={`bg-surface-container-lowest rounded-xl p-3 shadow-sm flex items-center justify-between gap-space-xs ${t.status === "not_available" || !t.required ? "opacity-80" : ""}`}>
      <div className="flex items-center gap-space-sm min-w-0">
        <div className="flex-shrink-0 w-12 flex flex-col items-center gap-1">
          <span className={`font-extrabold tabular-nums tracking-tighter leading-none whitespace-nowrap ${done(t) ? "text-outline" : "text-primary"}`} style={{ fontFamily: "var(--font-display)", fontSize: step.length > 3 ? 15 : step.length > 2 ? 19 : 24 }}>{step}</span>
          <span className={`w-5 h-5 rounded-full flex items-center justify-center ${circle}`}><Icon name={icon} size={13} /></span>
        </div>
        <div className="flex flex-col min-w-0">
          <span className={`font-label-lg text-label-lg text-primary truncate ${isNext ? "font-bold" : ""}`}>{t.label}{code(t) && ` (${code(t)})`}</span>
          <span className="font-body-sm text-body-sm text-on-surface-variant truncate">{sub}</span>
        </div>
      </div>
      <span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm font-semibold flex-shrink-0 ${pill}`}>{t.required ? text : text === "Klar" ? text : "Valgfrit"}</span>
    </div>
  );
  const actionable = t.you_can_act && !done(t) && t.status !== "not_available";
  return <li>{actionable ? <Link href={href(t.destination)} className="block rounded-xl">{body}</Link> : body}</li>;
}
