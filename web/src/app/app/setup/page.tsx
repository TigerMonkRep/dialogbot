import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Badge, Breadcrumb, Icon, ProgressRing, SectionLabel } from "@/components/ui";
import { GoalArchitecture, ModeToggle, RunChecks, SkipButton, WhyBlock } from "./client";

export type Task = { key: string; label: string; phase: string; explanation: string; destination: string; required: boolean; status: string; blocked_by: { type: string; message: string }[]; can_skip: boolean; you_can_act: boolean; estimated_minutes: number; stale_checks: string[]; min_role: string };
type Check = { key: string; label: string; description: string; runnable: boolean; status: string; last_run_at: string | null; environment: string | null; stale_reason: string | null };
type Plan = { progress: { required_total: number; required_complete: number; percent: number; estimated_minutes_remaining: number }; next_action: Task | null; next_action_explanation: string | null; resume: { open_drafts: number; in_review: number }; tasks: Task[]; checks: Check[]; guidance_mode: string; product_intent: string };

const ROUTE: Record<string, string> = { "/onboarding/business#categories": "/onboarding/business", "/app/knowledge/catalogue": "/app/knowledge?tab=k03", "/app/knowledge/review": "/app/knowledge?tab=k05", "/app/setup/readiness": "/app/setup#checks", "/app/setup/launch": "/app/setup#checks", "/app/settings/integrations": "/app/not-yet?area=Integrationer", "/onboarding/test": "/app/not-yet?area=Pr%C3%B8veopkald", "/app/campaigns/new": "/app/not-yet?area=Kampagner" };
export const href = (d: string) => ROUTE[d] ?? d;
const STATUS_ICON: Record<string, string> = { complete: "check_circle", in_progress: "pending", not_started: "radio_button_unchecked", blocked: "lock", not_available: "block", skipped: "skip_next" };

/** G01/G02/G05/G07/G08 — layout after Stitch "g01_g04_o03_o05_personlig_opsætningsguide". Data is server-computed. */
export default async function SetupPage() {
  const ws = await requireWorkspace();
  const [plan, goals, profile, languages] = await Promise.all([
    backend<Plan>(`/workspaces/${ws.id}/setup/plan`),
    backend<Record<string, unknown>>(`/workspaces/${ws.id}/goals`),
    backend<{ cvr: string | null; description: string }>(`/workspaces/${ws.id}/profile`),
    backend<Record<string, unknown>>(`/workspaces/${ws.id}/languages`),
  ]);
  const p = plan.progress;
  const next = plan.next_action;
  const phases = [...new Set(plan.tasks.map((t) => t.phase))];
  const canEdit = ws.role !== "reader";
  const LANG: Record<string, string> = { da: "Dansk (DK)", en: "Engelsk (EN)", de: "Tysk (DE)", sv: "Svensk (SV)", no: "Norsk (NO)" };
  return (
    <div className="flex flex-col gap-space-xl">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-space-md">
        <div className="space-y-1">
          <Breadcrumb items={[["Opsætning"], ["Personlig plan", "/app/setup"]]} />
          <h1 className="font-display text-headline-lg text-primary tracking-tight">Personlig plan for {ws.name}</h1>
          {profile.cvr && <span className="text-label-md text-on-surface-variant">CVR: {profile.cvr}</span>}
        </div>
        <ModeToggle wsId={ws.id} mode={plan.guidance_mode} goals={goals} canEdit={canEdit} />
      </div>

      {/* Honest roadmap banner */}
      <div className="relative overflow-hidden rounded-xl bg-surface-container-lowest p-space-xl shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-lg">
          <div className="space-y-1">
            <div className="flex items-center gap-space-sm">
              <span className="px-2 py-0.5 rounded-md bg-secondary-container text-on-secondary-container text-label-sm font-semibold uppercase tracking-wider">Aktiv opsætningshub (G01)</span>
              <span className="text-on-surface-variant text-label-sm">Beregnet ud fra dine valgte driftsmål · {plan.product_intent === "both" ? "reception + kampagner" : plan.product_intent === "campaigns" ? "kampagner" : "reception"}</span>
            </div>
            <h2 className="font-display text-headline-lg text-primary font-bold tracking-tight">Din personlige køreplan: {p.required_complete} af {p.required_total} nødvendige trin er klar</h2>
            <p className="text-body-md text-on-surface-variant max-w-2xl">{profile.description || "Udfyld virksomhedsprofilen, så planen kan tilpasses jeres ydelser."} {p.required_total - p.required_complete > 0 && `Færdiggør de sidste ${p.required_total - p.required_complete} trin.`}</p>
          </div>
          <div className="flex items-center gap-space-md bg-surface-container-low px-space-lg py-space-md rounded-xl shrink-0">
            <ProgressRing percent={p.percent} />
            <div className="flex flex-col"><span className="text-label-lg font-bold text-primary">{p.required_complete} / {p.required_total} opgaver</span><span className="text-body-sm text-on-surface-variant">Estimeret resttid: {p.estimated_minutes_remaining} min</span></div>
          </div>
        </div>
        <div className="w-full bg-surface-container-highest h-2 rounded-full mt-space-lg overflow-hidden"><div className="bg-primary h-full rounded-full transition-all" style={{ width: `${p.percent}%` }} /></div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        <div className="lg:col-span-8 flex flex-col gap-space-xl">
          {/* Next action spotlight */}
          <div className="relative rounded-xl bg-gradient-to-br from-primary-container to-primary text-on-primary p-space-xl shadow-md overflow-hidden">
            <div className="absolute -right-8 -bottom-8 w-48 h-48 bg-secondary-container/10 rounded-full blur-2xl pointer-events-none" />
            <div className="flex flex-col gap-space-md relative z-10">
              <div className="flex items-center justify-between flex-wrap gap-space-xs">
                <span className="px-2.5 py-1 rounded-full bg-secondary-fixed text-on-secondary-fixed text-label-sm font-bold uppercase tracking-wider flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-primary animate-ping" />Næste handling</span>
                {next && <span className="text-primary-fixed-dim text-label-sm flex items-center gap-1"><Icon name="schedule" size={16} />ca. {next.estimated_minutes} min</span>}
                {next && <span className="text-primary-fixed text-label-sm">{next.required ? "Nødvendigt trin" : "Valgfrit trin"}</span>}
              </div>
              {next ? (
                <>
                  <div className="space-y-1"><h2 className="font-display text-headline-md text-on-primary font-bold">{next.label}</h2><p className="text-body-md text-primary-fixed-dim leading-relaxed">{next.explanation}</p></div>
                  <WhyBlock task={next} />
                  <div className="flex items-center gap-space-md pt-space-xs flex-wrap">
                    <Link href={href(next.destination)} className="px-space-xl py-2.5 rounded-xl bg-secondary-fixed text-on-secondary-fixed text-label-lg font-bold hover:brightness-105 shadow-sm flex items-center gap-space-xs">Start opgave <Icon name="arrow_forward" size={18} /></Link>
                    <span className="text-label-md text-primary-fixed-dim">{next.phase} · {next.key}</span>
                  </div>
                </>
              ) : (
                <div className="space-y-1"><h2 className="font-display text-headline-md font-bold">Ingen åben handling for din rolle</h2><p className="text-body-md text-primary-fixed-dim">{plan.next_action_explanation}</p></div>
              )}
              {next && plan.next_action_explanation && <p className="text-body-sm text-primary-fixed-dim border-t border-on-primary/15 pt-space-sm">{plan.next_action_explanation}</p>}
            </div>
          </div>

          {/* G02 & O03 goal & channel architecture */}
          <div className="rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
            <div className="flex items-start justify-between">
              <div><SectionLabel>Mål og kanalarkitektur (G02 &amp; O03)</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">Valgte driftsmål &amp; automatiseringer</h3></div>
              <Link href="/onboarding/goals" className="text-label-sm text-secondary hover:underline flex items-center gap-1">Redigér <Icon name="tune" size={14} /></Link>
            </div>
            <GoalArchitecture wsId={ws.id} goals={goals} canEdit={canEdit} />
            <div className="flex items-start gap-space-sm p-space-md rounded-lg bg-surface-container-high">
              <Icon name="verified_user" size={20} className="text-secondary shrink-0 mt-0.5" />
              <div className="space-y-0.5"><span className="text-label-md font-semibold text-primary">Arkitektur-regel:</span><p className="text-body-sm text-on-surface-variant">Et arbejdsrum med kun kampagner får ingen telefon- eller kalendertrin. Callback hører under reception. Booking aktiveres kun, når du vælger det – og kræver en implementeret kalenderadapter.</p></div>
            </div>
          </div>

          {/* O04 languages */}
          <div className="rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
            <div><SectionLabel>Sprog &amp; assistent (O04)</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">Eksplicit adskillelse af 4 sprogniveauer</h3><p className="text-body-sm text-on-surface-variant">Kontrollér sprogparametre separat for drift, AI-forståelse og ledelsesrapportering.</p></div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
              {([["a) Brugerfladesprog", LANG[String(languages.interface_language)] ?? String(languages.interface_language), "Administration, menupunkter og knapper i denne portal."],
                ["b) Standardsamtalesprog", LANG[String(languages.default_conversation_language)] ?? String(languages.default_conversation_language), "Assistenten svarer som standard på dette sprog."],
                ["c) Tilladte samtalesprog", (languages.enabled_conversation_languages as string[]).map((c) => LANG[c] ?? c).join(", "), "Sprog assistenten må skifte til, når kunden gør det."],
                ["d) Rapportsprog", LANG[String(languages.report_language)] ?? String(languages.report_language), "Daglige resuméer og ledelsesrapporter."]] as [string, string, string][]).map(([t, v, d]) => (
                <div key={t} className="p-space-md rounded-xl bg-surface-container-low flex flex-col justify-between gap-space-sm">
                  <div><span className="text-label-sm uppercase text-on-surface-variant">{t}</span><p className="text-label-lg font-bold text-on-surface mt-1">{v}</p><p className="text-body-sm text-on-surface-variant">{d}</p></div>
                  <Link href="/onboarding/languages" className="text-left text-label-sm text-secondary hover:underline flex items-center gap-1">Skift sprog <Icon name="tune" size={14} /></Link>
                </div>
              ))}
            </div>
            <p className="text-body-sm text-on-surface-variant flex items-center gap-space-xs"><Icon name="graphic_eq" size={16} />Stemmeprøve og assistentpersona (O05) kræver stemme-/AI-adapteren – tilkobles i milepæl B og vises ikke som færdig før da.</p>
          </div>

          {/* Task list by phase */}
          {phases.map((phase) => (
            <div key={phase} className="rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-md">
              <div className="flex items-center justify-between"><h3 className="font-display text-headline-sm text-primary font-bold">{phase}</h3><span className="text-label-sm text-on-surface-variant">{plan.tasks.filter((t) => t.phase === phase && t.status === "complete").length} af {plan.tasks.filter((t) => t.phase === phase).length} gennemført</span></div>
              <ul className="divide-y divide-outline-variant/40">
                {plan.tasks.filter((t) => t.phase === phase).map((t) => (
                  <li key={t.key} className="py-space-md flex flex-col md:flex-row md:items-start gap-space-md">
                    <Icon name={STATUS_ICON[t.status] ?? "radio_button_unchecked"} size={22} className={`shrink-0 mt-0.5 ${t.status === "complete" ? "text-secondary" : t.status === "not_available" || t.status === "blocked" ? "text-on-surface-variant" : "text-primary"}`} filled={t.status === "complete"} />
                    <div className="flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-space-xs"><span className="text-label-lg font-bold text-on-surface">{t.label}</span><Badge status={t.status} />{!t.required && <span className="text-label-sm text-on-surface-variant">valgfri</span>}<span className="text-label-sm text-on-surface-variant flex items-center gap-0.5"><Icon name="schedule" size={14} />{t.estimated_minutes} min</span></div>
                      <p className="text-body-sm text-on-surface-variant">{t.explanation}</p>
                      {t.blocked_by.map((b, i) => <p key={i} className="text-label-md text-on-error-container flex items-start gap-1"><Icon name={b.type === "capability" ? "block" : b.type === "permission" ? "lock" : "link"} size={16} />{b.message}</p>)}
                      {t.stale_checks.length > 0 && <p className="text-label-md text-on-error-container">Forældede tjek: {t.stale_checks.join(", ")} – kør tjek igen.</p>}
                    </div>
                    <div className="flex gap-space-xs shrink-0">
                      {t.can_skip && t.status !== "skipped" && canEdit && <SkipButton wsId={ws.id} taskKey={t.key} />}
                      {t.status === "skipped" && canEdit && <SkipButton wsId={ws.id} taskKey={t.key} unskip />}
                      {t.status !== "not_available" && t.status !== "complete" && t.you_can_act && <Link href={href(t.destination)} className="px-space-md py-2 rounded-lg bg-surface-container-low text-primary text-label-md font-semibold hover:bg-surface-container flex items-center gap-1">Åbn <Icon name="arrow_forward" size={16} /></Link>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Right column: checks (G05) + resume */}
        <div className="lg:col-span-4 flex flex-col gap-space-lg lg:sticky lg:top-20">
          <div id="checks" className="rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-md">
            <div className="flex items-start justify-between gap-space-sm"><div><SectionLabel>Tjek (G05)</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">Klarhedstjek</h3></div>{canEdit && <RunChecks wsId={ws.id} />}</div>
            <ul className="space-y-space-sm">
              {plan.checks.map((c) => (
                <li key={c.key} className="p-space-md rounded-lg bg-surface-container-low">
                  <div className="flex items-center justify-between gap-space-xs"><span className="text-label-md font-semibold text-on-surface">{c.label}</span><Badge status={c.status} /></div>
                  <p className="text-body-sm text-on-surface-variant mt-0.5">{c.description}</p>
                  <p className="text-label-sm text-on-surface-variant mt-1">{c.runnable ? (c.last_run_at ? `Kørt ${new Date(c.last_run_at).toLocaleString("da-DK")} · ${c.environment}` : "Ikke kørt endnu") : "Kræver integration – ikke implementeret"}{c.stale_reason && ` · ${c.stale_reason}`}</p>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-sm">
            <SectionLabel>Genoptag (G01)</SectionLabel>
            <p className="text-body-sm text-on-surface-variant">{plan.resume.open_drafts} åbne kladder · {plan.resume.in_review} til gennemgang. Alt gemmes serverside; du kan lukke browseren og fortsætte senere fra samme trin.</p>
            <Link href="/app/knowledge?tab=k05" className="text-label-md text-secondary hover:underline flex items-center gap-1">Gå til gennemgang <Icon name="arrow_forward" size={16} /></Link>
          </div>
        </div>
      </div>
    </div>
  );
}
