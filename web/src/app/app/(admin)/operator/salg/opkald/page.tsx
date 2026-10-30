import Link from "next/link";
import { Tag } from "@/components/ui";
import { ChannelOff, NotOperator, SalgFrame, dt, load } from "../shared";

type Row = {
  campaign_contact_id: string; campaign: { id: string; name: string; test: boolean }; company: string; phone: string;
  status: string; attempts: number; outcome: string | null; summary: string; error: string | null; last_attempt_at: string | null;
  call_id: string | null; duration_seconds: number | null; ended_reason: string | null; transcript_status: string | null;
};
const OUTCOME: Record<string, string> = { interested: "Interesseret", callback: "Ring tilbage", not_interested: "Ikke interesseret", opt_out: "Frabad sig opkald", no_answer: "Intet svar" };
const STATUS: Record<string, string> = { calling: "Ringer / afventer rapport", done: "Gennemført", pending: "Venter på nyt forsøg", no_answer: "Intet svar", failed: "Fejlet", opted_out: "Frabedt", skipped: "Sprunget over", unknown: "Uvist – tjek hos Vapi" };
const TRANSCRIPT: Record<string, string> = { AVAILABLE: "transskript", PENDING: "afventer", NOT_RECORDED: "ingen samtale", FAILED: "fejlet", DELETED: "slettet" };

export default async function CallsPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const qs = new URLSearchParams();
  for (const k of ["q", "outcome", "test"]) if (sp[k]) qs.set(k, sp[k] as string);
  const r = await load<{ items: Row[] }>(`/operator/salg/calls?${qs}`);
  if (!r.ok) {
    if (r.status === 501) return <SalgFrame active="/app/operator/salg/opkald" title="Opkald"><ChannelOff message={r.message} /></SalgFrame>;
    return <NotOperator status={r.status} message={r.message} />;
  }
  return (
    <SalgFrame active="/app/operator/salg/opkald" title="Opkald" intro="Alle Peters opkald fra interne kampagner og testopkald – også ubesvarede og fejlede. Et testopkald starter du fra en virksomheds side (kræver et godkendt manuskript og SALES_OUTBOUND_MODE=test).">
      <form method="get" className="flex flex-wrap gap-2 items-end">
        <label className="text-[13px]">Søg i samtaler<input name="q" defaultValue={sp.q ?? ""} className="block min-h-[42px] px-3 rounded-xl border-2 border-ink bg-paper" /></label>
        <label className="text-[13px]">Udfald<select name="outcome" defaultValue={sp.outcome ?? ""} className="block min-h-[42px] px-2 rounded-xl border-2 border-ink bg-paper"><option value="">Alle</option>{Object.entries(OUTCOME).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="text-[13px]">Type<select name="test" defaultValue={sp.test ?? ""} className="block min-h-[42px] px-2 rounded-xl border-2 border-ink bg-paper"><option value="">Alle</option><option value="true">Kun test</option><option value="false">Uden test</option></select></label>
        <button className="min-h-[42px] px-4 rounded-xl bg-ink text-paper font-semibold">Vis</button>
      </form>
      {r.data.items.length === 0 ? <p className="text-muted">Ingen opkald endnu.</p> : (
        <ul className="flex flex-col gap-2">{r.data.items.map((c) => (
          <li key={c.campaign_contact_id} className="rounded-xl border-2 border-ink bg-paper p-3 text-[14px]">
            <div className="flex flex-wrap gap-2 items-center justify-between">
              <Link className="font-semibold underline" href={`/app/operator/salg/opkald/${c.campaign_contact_id}`}>{c.company} · <span className="tabular-nums">{c.phone}</span></Link>
              <span className="flex gap-2">{c.campaign.test && <Tag tone="secondary">Test</Tag>}<Tag>{c.outcome ? OUTCOME[c.outcome] ?? c.outcome : STATUS[c.status] ?? c.status}</Tag></span>
            </div>
            <p className="text-muted">{dt(c.last_attempt_at)} · {c.campaign.name} · forsøg {c.attempts}{c.duration_seconds != null ? ` · ${c.duration_seconds} s` : ""}{c.transcript_status ? ` · ${TRANSCRIPT[c.transcript_status] ?? c.transcript_status}` : ""}</p>
            {c.summary && <p>{c.summary}</p>}
            {c.error && <p className="text-danger">{c.error}</p>}
          </li>))}</ul>
      )}
    </SalgFrame>
  );
}
