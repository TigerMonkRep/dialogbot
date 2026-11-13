import { Advanced, AdminFrame, NotOperator, dt, load } from "../shared";
import { RetryCalendar, RetryJob, Suspend } from "./actions";

type Job = { id: string; type: string; status: string; attempts: number; max_attempts: number; error: string; at: string;
  workspace_id: string | null; workspace_name: string | null; workspace_suspended: boolean; retryable: boolean };
type SyncRow = { id: string; workspace_id: string; workspace_name: string | null; workspace_suspended: boolean; title: string;
  starts_at: string; status: string; calendar_connector: string | null; error: string | null; outcome: "exists" | "unknown" | "not_created" | null };
type Ops = {
  schema: { ok: boolean; database: string | null; code: string }; outbox_7d: Record<string, number>;
  failed_jobs: Job[];
  calls: { last_24h: { total: number; inbound: number; outbound: number };
    problems: { id: string; workspace_id: string; workspace_name: string | null; direction: string; at: string | null; ended_reason: string | null;
      transcript_status: string; recording_status: string; from: string | null }[] };
  calendar_sync: { failed: SyncRow[]; pending_confirmation: number; ical_errors: { workspace_id: string; workspace_name: string | null; error: string; synced_at: string | null }[] };
  incidents: { kind: string; source: string; count: number; since: string | null; detail: string; unit: string }[];
  suspended: { workspace_id: string; workspace_name: string; since: string; reason: string | null; by: string | null }[];
  emails: { at: string; to: string; subject: string; status: string; provider_status: string | null; adapter: string }[];
  audit: { at: string; action: string; workspace_id: string | null; actor: string | null; object: string }[];
  links: Record<string, string>;
};
const box = "rounded-2xl bg-paper border-2 border-ink p-space-md";
const h2 = "font-display font-bold text-[18px] mb-2";
const OUTCOME: Record<string, string> = {
  exists: "Aftalen findes i kalenderen – den opdateres.",
  not_created: "Aftalen blev ikke oprettet – den oprettes én gang.",
  unknown: "Ukendt: sidste forsøg fik intet svar. Se efter i kalenderen før genkørsel.",
};
const KIND: Record<string, string> = { integration: "Forbindelse", job: "Opgavetype", email: "E-mail", telephony: "Telefoni" };

/** M03 – «Drift»: is the system healthy, what failed where, and the operator's controlled interventions (one retry,
 *  pause/resume of a tenant). Nothing on this page changes by itself: no timers, no simulated recovery (DB-007). */
export default async function Drift() {
  const o = await load<Ops>("/operator/admin/operations");
  if (!o) return <NotOperator />;
  const suspendedIds = new Set(o.suspended.map((s) => s.workspace_id));
  const tenants = new Map<string, string>();
  for (const j of o.failed_jobs) if (j.workspace_id && j.workspace_name) tenants.set(j.workspace_id, j.workspace_name);
  for (const b of o.calendar_sync.failed) if (b.workspace_name) tenants.set(b.workspace_id, b.workspace_name);
  for (const c of o.calls.problems) if (c.workspace_name) tenants.set(c.workspace_id, c.workspace_name);
  for (const s of o.suspended) tenants.delete(s.workspace_id);
  return (
    <AdminFrame active="/app/operator/admin/drift" eyebrow="Admin · drift" title="Drift"
      intro="Er systemet sundt? Database, opgavekø, opkald, kalender-synk og afhængigheder på tværs af kunder. Herfra kan I køre én fejlet opgave eller kalenderskrivning igen og sætte en kunde på pause. Alt logføres.">
      <div className="grid md:grid-cols-2 gap-space-md">
        <section className={box}><h2 className="font-display font-bold text-[18px] mb-1">Database og kode</h2>
          <p className={o.schema.ok ? "text-success font-semibold" : "text-danger font-semibold"}>{o.schema.ok ? "Samme version" : "FORSKELLIG version – workeren holder pause"}</p>
          <p className="text-[13px] text-muted">Database {o.schema.database ?? "?"} · kode {o.schema.code}</p></section>
        <section className={box}><h2 className="font-display font-bold text-[18px] mb-1">Opgavekø (7 dage)</h2>
          <p className="text-[14px]">{Object.entries(o.outbox_7d).map(([k, v]) => `${k}: ${v}`).join(" · ") || "tom"}</p>
          <p className="text-[13px] text-muted mt-1">Tjenester: {Object.entries(o.links).map(([k, v]) => <a key={k} className="underline mr-2" href={v} target="_blank" rel="noreferrer">{k}</a>)}</p></section>
      </div>

      <section className={box} aria-labelledby="h-incidents"><h2 id="h-incidents" className={h2}>Afhængigheder og hændelser</h2>
        <ul className="text-[14px] divide-y divide-line">
          {o.incidents.map((x, i) => (
            <li key={i} className="py-2 flex flex-wrap justify-between gap-2">
              <span><span className="font-semibold">{KIND[x.kind] ?? x.kind}: {x.source}</span> · {x.count} {x.unit}{x.detail && <span className="block text-[13px] text-danger break-words">{x.detail}</span>}</span>
              <span className="text-muted text-[13px]">senest {dt(x.since)}</span>
            </li>))}
          {o.incidents.length === 0 && <li className="py-1 text-muted">Ingen aktive hændelser.</li>}
        </ul>
      </section>

      <section className={`${box} shadow-block`} aria-labelledby="h-suspend"><h2 id="h-suspend" className={h2}>Suspendering (kunder sat på pause)</h2>
        <p className="text-[13px] text-muted mb-2">En kunde på pause: køen, kampagneopkald og handlinger i kundens systemer venter. Indgående opkald og chat besvares stadig. Kun Dialogbot-operatører kan sætte på pause og genoptage.</p>
        <ul className="text-[14px] divide-y divide-line">
          {o.suspended.map((s) => (
            <li key={s.workspace_id} className="py-2 flex flex-wrap justify-between items-start gap-3">
              <span><span className="font-semibold">{s.workspace_name}</span> · på pause siden {dt(s.since)}{s.by ? ` · af ${s.by}` : ""}<span className="block text-[13px] text-ink-soft">{s.reason}</span></span>
              <Suspend workspaceId={s.workspace_id} name={s.workspace_name} suspended />
            </li>))}
          {o.suspended.length === 0 && <li className="py-1 text-muted">Ingen kunder er sat på pause.</li>}
        </ul>
        {tenants.size > 0 && (
          <div className="mt-3 pt-3 border-t-[1.5px] border-line flex flex-col gap-2">
            <span className="eyebrow">Berørte kunder</span>
            <ul className="flex flex-col gap-2">{[...tenants].map(([id, name]) => (
              <li key={id} className="flex flex-wrap justify-between items-start gap-3 text-[14px]"><span className="font-semibold">{name}</span><Suspend workspaceId={id} name={name} suspended={false} /></li>))}</ul>
          </div>)}
      </section>

      <section className={box} aria-labelledby="h-calls"><h2 id="h-calls" className={h2}>Opkald</h2>
        <p className="text-[14px]">Seneste døgn: {o.calls.last_24h.total} opkald ({o.calls.last_24h.inbound} indgående, {o.calls.last_24h.outbound} udgående)</p>
        <p className="text-[13px] text-muted mb-2">Opkald med fejl de seneste 7 dage. Et opkald ringes aldrig op igen herfra – det ville give dobbeltopkald.</p>
        <ul className="text-[14px] divide-y divide-line">
          {o.calls.problems.map((c) => (
            <li key={c.id} className="py-2"><span className="font-semibold">{c.workspace_name ?? "–"}</span> · {c.direction === "outbound" ? "udgående" : "indgående"} · {dt(c.at)}{c.from ? ` · ${c.from}` : ""}
              <span className="block text-[13px] text-danger break-words">{c.ended_reason ?? "–"}{c.transcript_status === "FAILED" ? " · udskrift fejlede" : ""}{c.recording_status === "FAILED" ? " · optagelse fejlede" : ""}</span></li>))}
          {o.calls.problems.length === 0 && <li className="py-1 text-muted">Ingen opkald med fejl.</li>}
        </ul>
      </section>

      <section className={box} aria-labelledby="h-sync"><h2 id="h-sync" className={h2}>Kalender-synk (bookinger)</h2>
        <p className="text-[13px] text-muted mb-2">{o.calendar_sync.pending_confirmation} kommende aftaler afventer bekræftelse hos kunden. Aftaler, der ikke kunne skrives i kundens kalender:</p>
        <ul className="text-[14px] divide-y divide-line">
          {o.calendar_sync.failed.map((b) => (
            <li key={b.id} className="py-2 flex flex-wrap justify-between items-start gap-3">
              <span className="min-w-0"><span className="font-semibold">{b.workspace_name ?? "–"}</span> · {b.title} · {dt(b.starts_at)}{b.status === "cancelled" ? " · aflyst" : ""}
                <span className="block text-[13px] text-danger break-words">{b.error ?? "–"}</span>
                {b.outcome && <span className="block text-[13px] text-ink">{OUTCOME[b.outcome]}</span>}
                {b.workspace_suspended && <span className="block text-[13px] text-muted">Kunden er på pause – genoptag først.</span>}</span>
              <RetryCalendar id={b.id} outcome={b.outcome} disabled={b.workspace_suspended} label={`${b.workspace_name ?? ""} ${b.title}`} />
            </li>))}
          {o.calendar_sync.failed.length === 0 && <li className="py-1 text-muted">Ingen fejlede kalenderskrivninger.</li>}
        </ul>
        {o.calendar_sync.ical_errors.length > 0 && (
          <ul className="mt-2 text-[13px] divide-y divide-line">{o.calendar_sync.ical_errors.map((e) => (
            <li key={e.workspace_id} className="py-1">iCal · <span className="font-semibold">{e.workspace_name ?? e.workspace_id}</span> · <span className="text-danger">{e.error}</span> · senest læst {dt(e.synced_at)}</li>))}</ul>)}
      </section>

      <section className={box} aria-labelledby="h-jobs"><h2 id="h-jobs" className={h2}>Fejlede opgaver</h2>
        <p className="text-[13px] text-muted mb-2">«Genkør én gang» giver opgaven præcis ét forsøg mere med samme opgave-id, så den aldrig udføres to gange. En udført opgave køres ikke igen.</p>
        <ul className="text-[14px] divide-y divide-line">{o.failed_jobs.map((j) => (
          <li key={j.id} className="py-2 flex flex-wrap justify-between items-start gap-3">
            <span className="min-w-0"><span className="font-semibold">{j.type}</span> · {j.status} · {j.attempts} forsøg · {dt(j.at)}{j.workspace_name ? ` · ${j.workspace_name}` : ""}
              <span className="block text-[13px] text-danger break-words">{j.error}</span>
              {j.workspace_suspended && <span className="block text-[13px] text-muted">Kunden er på pause – genoptag først.</span>}</span>
            <RetryJob id={j.id} disabled={!j.retryable} label={j.type} />
          </li>))}{o.failed_jobs.length === 0 && <li className="py-1 text-muted">Ingen.</li>}</ul>
      </section>
      <section className={box}><h2 className={h2}>Seneste e-mails</h2>
        <ul className="text-[14px] divide-y divide-line">{o.emails.map((m, i) => <li key={i} className="py-1 flex flex-wrap justify-between gap-2"><span className="break-all">{dt(m.at)} · {m.to} · {m.subject}</span><span className="text-muted">{m.status}{m.provider_status ? ` / ${m.provider_status}` : ""} ({m.adapter})</span></li>)}</ul>
      </section>
      <section className={box}><h2 className={h2}>Logbog (seneste 40)</h2>
        <ul className="text-[13px] divide-y divide-line">{o.audit.map((a, i) => <li key={i} className="py-1 break-words">{dt(a.at)} · {a.action} · <span className="text-muted">{a.object}</span></li>)}</ul>
      </section>
      <Advanced data={o} />
    </AdminFrame>
  );
}
