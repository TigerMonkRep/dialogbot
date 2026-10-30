import Link from "next/link";
import { Advanced } from "../../../admin/shared";
import { Tag } from "@/components/ui";
import { ChannelOff, NotOperator, SalgFrame, dt, load } from "../../shared";

type Detail = {
  campaign_contact_id: string; campaign: { id: string; name: string; test: boolean }; company: string; company_id: string | null;
  phone: string; status: string; attempts: number; outcome: string | null; summary: string; error: string | null;
  dispatch_key: string | null; provider_call_id: string | null;
  call: { id: string; started_at: string | null; ended_at: string | null; duration_seconds: number | null; ended_reason: string | null; summary: string; transcript_status: string; recording_status: string; outcome: string | null } | null;
  messages: { index: number; speaker: string; text: string; time_note: string }[];
  events: { type: string; at: string; payload: Record<string, unknown> }[];
  qualifications: { no: number; result: string; quote: string | null; message_index: number | null }[];
  decision: { result: string; reason_text: string[]; decided_at: string } | null;
};
const ACCEPT = ["", "Problemet forstået", "Gør en forskel", "Rette form for hjælp", "Integration passer", "Prisen giver mening"];
const OUTCOME: Record<string, string> = { interested: "Interesseret", callback: "Ring tilbage", not_interested: "Ikke interesseret", opt_out: "Frabad sig opkald", no_answer: "Intet svar" };
const EVENT: Record<string, string> = { assistant_snapshot: "Manuskript låst til forsøget", created: "Opkald oprettet hos Vapi", "status-update": "Status fra Vapi", "end-of-call-report": "Opkaldsrapport modtaget" };

export default async function CallPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const r = await load<Detail>(`/operator/salg/calls/${id}`);
  if (!r.ok) {
    if (r.status === 501) return <SalgFrame active="/app/operator/salg/opkald" title="Opkald"><ChannelOff message={r.message} /></SalgFrame>;
    if (r.status === 404) return <SalgFrame active="/app/operator/salg/opkald" title="Opkald"><p>Opkaldet findes ikke.</p></SalgFrame>;
    return <NotOperator status={r.status} message={r.message} />;
  }
  const c = r.data;
  return (
    <SalgFrame active="/app/operator/salg/opkald" title={`${c.company} · ${c.phone}`}>
      <Link href="/app/operator/salg/opkald" className="text-primary underline text-[14px]">← Alle opkald</Link>
      <div className="grid lg:grid-cols-[minmax(0,24rem)_1fr] gap-space-lg items-start">
        <section className="rounded-2xl border-2 border-ink bg-paper p-space-md flex flex-col gap-1 text-[14px]">
          <p className="flex gap-2">{c.campaign.test && <Tag tone="secondary">Test</Tag>}<Tag>{c.outcome ? OUTCOME[c.outcome] ?? c.outcome : c.status}</Tag></p>
          <p>Kampagne: <Link className="underline" href={`/app/operator/salg/kampagner/${c.campaign.id}`}>{c.campaign.name}</Link></p>
          {c.company_id && <p><Link className="underline" href={`/app/operator/salg/virksomheder/${c.company_id}`}>Virksomhedens side</Link></p>}
          <p>Forsøg: {c.attempts} · status: {c.status}</p>
          {c.call ? <>
            <p>Start: {dt(c.call.started_at)} · varighed: {c.call.duration_seconds ?? "–"} s</p>
            <p>Afsluttet: {c.call.ended_reason ?? "–"}</p>
            <p>Lyd: {c.call.recording_status === "NOT_RECORDED" ? "ikke optaget" : c.call.recording_status}</p>
          </> : <p className="text-muted">{c.status === "calling" ? "Afventer opkaldsrapport fra Vapi." : c.status === "unknown" ? "Uvist om opkaldet blev oprettet – ringes ikke op igen automatisk." : "Ingen opkaldsrapport."}</p>}
          {c.error && <p className="text-danger">{c.error}</p>}
          {c.decision && <p className="text-muted">Politik ved seneste forsøg: {c.decision.result}{c.decision.reason_text.length ? ` (${c.decision.reason_text.join(", ")})` : ""}</p>}
          <h2 className="font-display font-bold text-[16px] mt-2">Delaccepter</h2>
          {c.qualifications.length === 0 ? <p className="text-muted">Ingen.</p> : <ul>{c.qualifications.map((q) => <li key={q.no}>{q.no}. {ACCEPT[q.no]}: {q.result}{q.quote ? ` – "${q.quote}"` : ""}</li>)}</ul>}
          <h2 className="font-display font-bold text-[16px] mt-2">Hændelser</h2>
          <ul>{c.events.map((e, i) => <li key={i}><span className="tabular-nums text-muted">{dt(e.at)}</span> {EVENT[e.type] ?? e.type}{e.type === "status-update" && e.payload.status ? `: ${String(e.payload.status)}` : ""}</li>)}</ul>
        </section>
        <section className="rounded-2xl border-2 border-ink bg-paper p-space-md min-w-0 flex flex-col gap-2">
          {(c.summary || c.call?.summary) && <div className="rounded-xl bg-panel p-3 text-[14px]"><span className="font-semibold">Opsummering (AI, ikke originalen): </span>{c.summary || c.call?.summary}</div>}
          <h2 className="font-display font-bold text-[18px]">Transskript</h2>
          {c.messages.length === 0 ? <p className="text-muted text-[14px]">Intet transskript ({c.call?.transcript_status ?? "afventer"}).</p> : (
            <ol className="flex flex-col gap-2 text-[14px]">{c.messages.map((m) => (
              <li key={m.index} className={`rounded-xl p-2 max-w-[85%] ${m.speaker === "peter" ? "bg-panel" : "bg-accent-soft self-end"}`}><span className="font-semibold">{m.speaker === "peter" ? "Peter" : "Kunde"}:</span> {m.text}</li>))}</ol>
          )}
          <p className="text-[12px] text-muted">Tidsstempler pr. replik vises ikke endnu; rækkefølgen er samtalens.</p>
          <Advanced data={c} />
        </section>
      </div>
    </SalgFrame>
  );
}
