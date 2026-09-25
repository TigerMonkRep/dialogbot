import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Badge, Card, Steps } from "@/components/ui";
import { RunChecks, SkipButton } from "./client";

type Task = { key: string; label: string; phase: string; explanation: string; destination: string; required: boolean; status: string; blocked_by: { type: string; message: string }[]; can_skip: boolean; you_can_act: boolean; estimated_minutes: number; stale_checks: string[] };
type Check = { key: string; label: string; description: string; runnable: boolean; status: string; last_run_at: string | null; environment: string | null; stale_reason: string | null; evidence: Record<string, unknown> | null };
type Plan = { progress: { required_total: number; required_complete: number; percent: number; estimated_minutes_remaining: number }; next_action: Task | null; next_action_explanation: string | null; resume: { open_drafts: number; in_review: number; last_activity_at: string | null }; tasks: Task[]; checks: Check[]; guidance_mode: string };

const ROUTE: Record<string, string> = { "/onboarding/business#categories": "/onboarding/business", "/app/knowledge/catalogue": "/app/knowledge", "/app/knowledge/review": "/app/knowledge", "/app/setup/readiness": "/app/setup#checks", "/app/setup/launch": "/app/setup", "/app/settings/integrations": "/app/setup", "/onboarding/test": "/app/setup", "/app/campaigns/new": "/app/setup" };
const href = (d: string) => ROUTE[d] ?? d;

/** G01/G02/G05/G07/G08: server-computed personal plan. Nothing here is a client-side "done" flag. */
export default async function SetupPage() {
  const ws = await requireWorkspace();
  const plan = await backend<Plan>(`/workspaces/${ws.id}/setup/plan`);
  const phases = [...new Set(plan.tasks.map((t) => t.phase))];
  const p = plan.progress;
  return (
    <div className="mx-auto max-w-4xl">
      <Steps current="/app/setup" />
      <h1 className="text-2xl font-extrabold text-primary-dark">Personlig plan for {ws.name}</h1>
      <p className="mt-1 text-sm text-muted">{p.required_complete} af {p.required_total} nødvendige trin er klar · ca. {p.estimated_minutes_remaining} min tilbage · {plan.guidance_mode === "guided" ? "guidet" : "selvstyret"}</p>
      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white"><div className="h-2 bg-primary" style={{ width: `${p.percent}%` }} aria-label={`${p.percent} %`} /></div>

      <Card title="Næste handling" className="my-5 border-primary/40">
        {plan.next_action ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><p className="font-bold text-primary-dark">{plan.next_action.label}</p><p className="text-sm text-muted">{plan.next_action.explanation}</p></div>
            <Link href={href(plan.next_action.destination)} className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white">Start opgave →</Link>
          </div>
        ) : <p className="text-sm">{plan.next_action_explanation}</p>}
        {plan.next_action && plan.next_action_explanation && <p className="mt-3 text-xs text-muted">{plan.next_action_explanation}</p>}
        {plan.resume.open_drafts + plan.resume.in_review > 0 && <p className="mt-2 text-xs text-muted">Genoptag: {plan.resume.open_drafts} åbne kladder, {plan.resume.in_review} til gennemgang.</p>}
      </Card>

      {phases.map((phase) => (
        <Card key={phase} title={phase} className="mb-4">
          <ul className="divide-y divide-line">
            {plan.tasks.filter((t) => t.phase === phase).map((t) => (
              <li key={t.key} className="py-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex items-center gap-2"><Badge status={t.status} /><strong>{t.label}</strong>{!t.required && <span className="text-xs text-muted">valgfri</span>}</span>
                  <span className="flex gap-2">
                    {t.can_skip && t.status !== "skipped" && <SkipButton wsId={ws.id} taskKey={t.key} />}
                    {t.status === "skipped" && <SkipButton wsId={ws.id} taskKey={t.key} unskip />}
                    {t.status !== "not_available" && t.status !== "complete" && t.you_can_act && <Link className="font-semibold text-primary underline" href={href(t.destination)}>Åbn</Link>}
                  </span>
                </div>
                <p className="mt-1 text-muted">{t.explanation}</p>
                {t.blocked_by.map((b, i) => <p key={i} className="mt-1 text-xs text-orange-900">⚠ {b.message}</p>)}
                {t.stale_checks.length > 0 && <p className="mt-1 text-xs text-yellow-900">Forældede tjek: {t.stale_checks.join(", ")}</p>}
              </li>
            ))}
          </ul>
        </Card>
      ))}

      <Card title="Tjek (G05)" className="mb-4" actions={ws.role !== "reader" ? <RunChecks wsId={ws.id} /> : undefined}>
        <ul id="checks" className="divide-y divide-line text-sm">
          {plan.checks.map((c) => (
            <li key={c.key} className="py-2">
              <div className="flex flex-wrap items-center justify-between gap-2"><span className="flex items-center gap-2"><Badge status={c.status} /><strong>{c.label}</strong></span>
                <span className="text-xs text-muted">{c.runnable ? (c.last_run_at ? `${new Date(c.last_run_at).toLocaleString("da-DK")} · ${c.environment}` : "ikke kørt") : "kræver integration – ikke implementeret"}</span></div>
              <p className="text-xs text-muted">{c.description}{c.stale_reason && ` · Forældet: ${c.stale_reason}`}</p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
