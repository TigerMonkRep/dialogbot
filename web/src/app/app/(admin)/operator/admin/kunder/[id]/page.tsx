import Link from "next/link";
import { Advanced, AdminFrame, NotOperator, dt, kr, load } from "../../shared";
import { ViewAsButton } from "../../view-as-button";

type Detail = {
  id: string; name: string; status: string; product_intent: string; created_at: string;
  members: { user_id: string; email: string; name: string; role: string; active: boolean; verified: boolean; is_operator: boolean; last_seen_at: string | null }[];
  billing: { card: string | null; billing_email: string | null; stripe_customer: boolean } | null;
  telephony: { state: string; business_number: string | null; documents_status: string } | null;
  ambassador: { id: string; name: string; via: string } | null;
  invoices: { month: string; status: string; gross_minor: number; number: string | null }[];
  calls: { started_at: string | null; from: string | null; seconds: number | null; reason: string | null; summary: string }[];
  campaigns: { id: string; name: string; status: string; created_at: string }[];
  audit: { at: string; action: string; object: string }[];
  entitlements: {
    product_intent: string; reception_may_go_live: boolean; campaigns_may_start: boolean; booking_enabled: boolean;
    subscription: { state: "paid" | "grace" | "stopped" | "never_paid"; paid: boolean; card: boolean; payment_failed: boolean; grace_ends: string | null;
      agreement: { model: string; version: number; confirmed: boolean } | null };
  };
  readiness: {
    goals: { inbound_phone: boolean; webchat: boolean; booking: boolean };
    steps: { key: string; label: string; ok: boolean; detail: string }[];
    setup_done: boolean; live: boolean;
    channels: { phone: string; webchat: string; booking: string };
  };
  advanced: unknown;
};
const SUB: Record<string, string> = { paid: "betalt", grace: "respit", stopped: "stoppet", never_paid: "ikke betalt" };
const yes = (b: boolean) => (b ? "ja" : "nej");
const box = "rounded-2xl bg-paper border-2 border-ink p-space-md";

export default async function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const d = await load<Detail>(`/operator/admin/customers/${id}`);
  if (!d) return <NotOperator />;
  return (
    <AdminFrame active="/app/operator/admin/kunder" title={d.name} intro={`Oprettet ${dt(d.created_at)} · ${d.product_intent} · status ${d.status}`}>
      <p><Link className="underline" href="/app/operator/admin/kunder">← Alle kunder</Link></p>
      <section className={box}>
        <h2 className="font-display font-bold text-[18px] mb-2">Medlemmer – se kontoen som personen</h2>
        <ul className="divide-y divide-line">
          {d.members.map((m) => (
            <li key={m.user_id} className="py-2 flex flex-wrap items-center justify-between gap-2">
              <span><span className="font-semibold">{m.name}</span> <span className="text-muted">{m.email}</span><span className="block text-[13px] text-muted">{m.role}{!m.active && " · deaktiveret"}{!m.verified && " · e-mail ikke bekræftet"} · sidst set {dt(m.last_seen_at)}</span></span>
              {m.active && !m.is_operator ? <ViewAsButton userId={m.user_id} workspaceId={d.id} label={`Se som ${m.name.split(" ")[0]}`} /> : <span className="text-[13px] text-muted">kan ikke ses</span>}
            </li>
          ))}
        </ul>
      </section>
      <div className="grid md:grid-cols-2 gap-space-md">
        <section className={box} aria-labelledby="m02-ent"><h2 id="m02-ent" className="font-display font-bold text-[18px] mb-2">Rettigheder</h2>
          <dl className="text-[14px] grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-muted">Abonnement</dt><dd>{SUB[d.entitlements.subscription.state]}{d.entitlements.subscription.grace_ends ? ` til ${dt(d.entitlements.subscription.grace_ends)}` : ""}{d.entitlements.subscription.payment_failed ? " · betaling fejlede" : ""}</dd>
            <dt className="text-muted">Aftale</dt><dd>{d.entitlements.subscription.agreement ? `model ${d.entitlements.subscription.agreement.model} v${d.entitlements.subscription.agreement.version}${d.entitlements.subscription.agreement.confirmed ? "" : " (ikke bekræftet)"}` : "ingen"} · kort: {yes(d.entitlements.subscription.card)}</dd>
            <dt className="text-muted">Mål</dt><dd>{d.entitlements.product_intent}</dd>
            <dt className="text-muted">Telefon/chat må gå live</dt><dd>{yes(d.entitlements.reception_may_go_live)}</dd>
            <dt className="text-muted">Kampagner må starte</dt><dd>{yes(d.entitlements.campaigns_may_start)}</dd>
            <dt className="text-muted">Online booking</dt><dd>{d.readiness.channels.booking}</dd>
          </dl>
        </section>
        <section className={box} aria-labelledby="m02-ready"><h2 id="m02-ready" className="font-display font-bold text-[18px] mb-2">Opsætning {d.readiness.live ? "· live" : d.readiness.setup_done ? "· klar, ikke live" : "· i gang"}</h2>
          <ul className="text-[14px] divide-y divide-line">{d.readiness.steps.map((s) => <li key={s.key} className="py-1 flex justify-between gap-3"><span><span aria-hidden>{s.ok ? "✓" : "○"}</span> <span className="font-semibold">{s.label}</span><span className="sr-only">{s.ok ? " – færdig" : " – mangler"}</span></span><span className="text-muted text-right">{s.detail}</span></li>)}</ul>
          <p className="text-[13px] text-muted mt-2">Telefon: {d.readiness.channels.phone} · webchat: {d.readiness.channels.webchat}</p>
        </section>
      </div>
      <div className="grid md:grid-cols-2 gap-space-md">
        <section className={box}><h2 className="font-display font-bold text-[18px] mb-2">Fakturering</h2>
          <p className="text-[14px]">Kort: {d.billing?.card ?? "intet gemt"} · faktura-mail: {d.billing?.billing_email ?? "–"}</p>
          <ul className="mt-2 text-[14px] divide-y divide-line">{d.invoices.map((i) => <li key={i.month} className="py-1 flex justify-between"><span>{i.month.slice(0, 7)} {i.number ?? ""}</span><span>{kr(i.gross_minor)} · {i.status}</span></li>)}{d.invoices.length === 0 && <li className="py-1 text-muted">Ingen fakturaer.</li>}</ul>
        </section>
        <section className={box}><h2 className="font-display font-bold text-[18px] mb-2">Telefoni og ambassadør</h2>
          <p className="text-[14px]">Telefonnummer: {d.telephony?.business_number ?? "–"} ({d.telephony?.state ?? "ikke sat op"}, dokumenter: {d.telephony?.documents_status ?? "–"})</p>
          <p className="text-[14px] mt-1">Anbefalet af: {d.ambassador ? `${d.ambassador.name} (${d.ambassador.via})` : "ingen"}</p>
        </section>
      </div>
      <section className={box}><h2 className="font-display font-bold text-[18px] mb-2">Seneste opkald</h2>
        <ul className="text-[14px] divide-y divide-line">{d.calls.map((c, i) => <li key={i} className="py-2"><span className="font-semibold">{dt(c.started_at)}</span> · {c.from ?? "ukendt"} · {c.seconds ?? 0} s{c.reason ? ` · ${c.reason}` : ""}<span className="block text-muted">{c.summary}</span></li>)}{d.calls.length === 0 && <li className="py-1 text-muted">Ingen opkald endnu.</li>}</ul>
      </section>
      <section className={box}><h2 className="font-display font-bold text-[18px] mb-2">Kampagner</h2>
        <ul className="text-[14px]">{d.campaigns.map((c) => <li key={c.id} className="py-1">{c.name} · {c.status} · {dt(c.created_at)}</li>)}{d.campaigns.length === 0 && <li className="text-muted">Ingen.</li>}</ul>
      </section>
      <section className={box}><h2 className="font-display font-bold text-[18px] mb-2">Seneste ændringer (logbog)</h2>
        <ul className="text-[13px] divide-y divide-line">{d.audit.map((a, i) => <li key={i} className="py-1">{dt(a.at)} · {a.action} · <span className="text-muted">{a.object}</span></li>)}{d.audit.length === 0 && <li className="text-muted">Ingen.</li>}</ul>
      </section>
      <Advanced data={d.advanced} />
    </AdminFrame>
  );
}
