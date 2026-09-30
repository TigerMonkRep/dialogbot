"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, useSubmit } from "@/components/ui";
import { STATUS, date, kr, monthLabel, pct } from "@/app/ambassador/shared";
import type { OpDetail } from "./page";

export function AmbassadorDetail({ a, others }: { a: OpDetail; others: { id: string; full_name: string }[] }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [terms, setTerms] = useState({ bonus: String(a.terms.bonus_minor / 100), rate: String(a.terms.rate_bp / 100), months: String(a.terms.months) });
  const [secret, setSecret] = useState<{ cpr: string | null; bank: { reg: string; account: string } | null } | null>(null);
  const act = useSubmit(async (path: string) => { await api(`/operator/ambassadors/${a.id}/${path}`, { method: "POST", body: JSON.stringify({ note }) }); setNote(""); router.refresh(); });
  const save = useSubmit(async () => {
    await api(`/operator/ambassadors/${a.id}/terms`, { method: "PUT", body: JSON.stringify({
      bonus_minor: Math.round(Number(terms.bonus.replace(",", ".")) * 100), rate_bp: Math.round(Number(terms.rate.replace(",", ".")) * 100), months: Number(terms.months), expected_version: a.version }) });
    router.refresh();
  });
  const reveal = useSubmit(async () => setSecret(await api(`/operator/ambassadors/${a.id}/reveal`, { method: "POST" })));
  const st = STATUS[a.status];
  const b = a.balances;
  return (
    <div className="grid xl:grid-cols-3 gap-space-lg items-start">
      <div className="xl:col-span-2 flex flex-col gap-space-lg">
        <section className="rounded-xl bg-surface-container-lowest p-space-lg shadow-sm space-y-space-md">
          <div className="flex flex-wrap items-start justify-between gap-space-sm">
            <div>
              <span className={`inline-flex px-2.5 py-0.5 rounded-full font-label-sm text-label-sm font-bold ${st.tone}`}>{st.label}</span>
              <h1 className="font-headline-md text-headline-md text-primary font-bold mt-1">{a.full_name}</h1>
              <p className="font-body-sm text-body-sm text-on-surface-variant">{a.email} · {a.phone || "intet telefonnr."} · tilmeldt {date(a.created_at)}</p>
            </div>
            <div className="font-body-sm text-body-sm min-w-0"><p>Kode <strong className="tracking-widest">{a.code}</strong></p><p className="text-on-surface-variant break-all">{a.link}</p></div>
          </div>
          <dl className="grid sm:grid-cols-2 gap-x-space-lg gap-y-1 font-body-sm text-body-sm">
            <dt className="text-on-surface-variant">Type</dt><dd>{a.kind === "company" ? `Virksomhed: ${a.company_name} (CVR ${a.cvr})${a.vat_registered ? ", momsregistreret" : ""}` : `Privat, født ${date(a.birth_date)}`}</dd>
            {a.minor && <><dt className="text-on-surface-variant">Forælder</dt><dd>{a.parent_name} ({a.parent_email}) – {a.parent_consent_at ? `godkendt ${date(a.parent_consent_at)}` : <span className="text-error">ikke godkendt endnu</span>}</dd></>}
            <dt className="text-on-surface-variant">CPR / bank</dt><dd>{a.kind === "private" ? (a.has_cpr ? "CPR gemt" : "CPR mangler") + " · " : ""}{a.has_bank ? `konto …${a.bank_last4}` : "bank mangler"}</dd>
            <dt className="text-on-surface-variant">Regler accepteret</dt><dd>{date(a.rules_accepted_at)} ({a.rules_version})</dd>
            {a.headline && <><dt className="text-on-surface-variant">Hilsen</dt><dd>&ldquo;{a.headline}&rdquo;</dd></>}
            {a.motivation && <><dt className="text-on-surface-variant">Vil anbefale til</dt><dd>{a.motivation}</dd></>}
          </dl>
          {a.payout_blockers.length > 0 && <Alert kind="warn">Kan ikke udbetales: {a.payout_blockers.join(" · ")}</Alert>}
        </section>

        <section className="rounded-xl bg-surface-container-lowest shadow-sm">
          <h2 className="font-headline-sm text-headline-sm text-primary font-bold p-space-md">Kunder ({a.customers.length})</h2>
          {a.customers.length === 0 ? <p className="px-space-md pb-space-md font-body-sm text-body-sm text-on-surface-variant">Ingen kunder endnu.</p> : (
            <ul className="divide-y divide-outline-variant/40">{a.customers.map((c) => <CustomerRow key={c.workspace_id} c={c} others={others} />)}</ul>
          )}
        </section>

        <section className="rounded-xl bg-surface-container-lowest shadow-sm overflow-hidden">
          <h2 className="font-headline-sm text-headline-sm text-primary font-bold p-space-md">Kontoudtog</h2>
          {a.ledger.length === 0 ? <p className="px-space-md pb-space-md font-body-sm text-body-sm text-on-surface-variant">Ingen posteringer.</p> : (
            <div className="overflow-x-auto"><table className="w-full text-left font-body-sm text-body-sm">
              <thead className="bg-surface-container-low font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider"><tr><th className="p-space-sm">Type</th><th className="p-space-sm">Kunde</th><th className="p-space-sm">Måned</th><th className="p-space-sm">Status</th><th className="p-space-sm text-right">Beløb</th></tr></thead>
              <tbody>{a.ledger.map((e) => <tr key={e.id} className="border-t border-outline-variant/40"><td className="p-space-sm">{e.label}</td><td className="p-space-sm">{e.company}</td><td className="p-space-sm">{monthLabel(e.month)}</td><td className="p-space-sm">{e.status_label}</td><td className="p-space-sm text-right tabular-nums">{kr(e.amount_minor)}</td></tr>)}</tbody>
            </table></div>
          )}
        </section>
      </div>

      <aside className="flex flex-col gap-space-lg">
        <section className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm space-y-space-sm">
          <h2 className="font-label-lg text-label-lg text-primary font-bold">Saldo</h2>
          <dl className="grid grid-cols-2 gap-y-1 font-body-sm text-body-sm tabular-nums">
            <dt>Optjent (hold)</dt><dd className="text-right">{kr(b.held_minor)}</dd><dt>Klar</dt><dd className="text-right font-semibold">{kr(b.payable_minor)}</dd>
            <dt>Under udbetaling</dt><dd className="text-right">{kr(b.in_payout_minor)}</dd><dt>Udbetalt</dt><dd className="text-right">{kr(b.paid_minor)}</dd>
          </dl>
          <p className="font-label-sm text-label-sm text-on-surface-variant">{a.stats.customers} kunder · {a.stats.paying} betalende · {a.stats.clicks_30d} besøg på 30 dage</p>
        </section>

        <section className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm space-y-space-sm">
          <h2 className="font-label-lg text-label-lg text-primary font-bold">Beslutning</h2>
          <ErrorBox error={act.error} />
          <Field label="Note (sendes med ved afslag)"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <div className="flex flex-wrap gap-space-xs">
            {a.status === "pending" && <><Button icon="check" disabled={act.pending} onClick={() => act.run("approve")}>Godkend</Button><Button variant="ghost" disabled={act.pending} onClick={() => act.run("reject")}>Afvis</Button></>}
            {a.status === "active" && <Button variant="danger" icon="pause" disabled={act.pending || !note.trim()} onClick={() => act.run("suspend")}>Sæt på pause</Button>}
            {a.status === "suspended" && <Button icon="play_arrow" disabled={act.pending} onClick={() => act.run("reactivate")}>Genaktivér</Button>}
          </div>
          {a.status === "active" && <p className="font-label-sm text-label-sm text-on-surface-variant">Pause kræver en begrundelse. Linket stopper, men optjent bonus bevares.</p>}
        </section>

        <section className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm space-y-space-sm">
          <h2 className="font-label-lg text-label-lg text-primary font-bold">Aftale</h2>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Nu: {kr(a.terms.bonus_minor)} + {pct(a.terms.rate_bp)} i {a.terms.months} mdr. Ændringer gælder fakturaer betalt fra nu af.</p>
          <ErrorBox error={save.error} />
          <div className="grid grid-cols-3 gap-space-xs">
            <Field label="Bonus kr."><Input inputMode="decimal" value={terms.bonus} onChange={(e) => setTerms({ ...terms, bonus: e.target.value })} /></Field>
            <Field label="Andel %"><Input inputMode="decimal" value={terms.rate} onChange={(e) => setTerms({ ...terms, rate: e.target.value })} /></Field>
            <Field label="Måneder"><Input inputMode="numeric" value={terms.months} onChange={(e) => setTerms({ ...terms, months: e.target.value })} /></Field>
          </div>
          <Button variant="tonal" icon="save" disabled={save.pending} onClick={() => save.run()}>Gem aftale</Button>
        </section>

        <section className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm space-y-space-sm">
          <h2 className="font-label-lg text-label-lg text-primary font-bold flex items-center gap-1"><Icon name="lock" size={18} />Bankoplysninger og CPR</h2>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Vis kun, når du skal overføre eller indberette. Hver visning logges.</p>
          <ErrorBox error={reveal.error} />
          {secret ? (
            <dl className="grid grid-cols-2 gap-y-1 font-body-sm text-body-sm select-all">
              <dt>Reg.nr.</dt><dd>{secret.bank?.reg ?? "–"}</dd><dt>Konto</dt><dd>{secret.bank?.account ?? "–"}</dd>
              {a.kind === "private" && <><dt>CPR</dt><dd>{secret.cpr ?? "–"}</dd></>}
            </dl>
          ) : <Button variant="outline" icon="visibility" disabled={reveal.pending} onClick={() => reveal.run()}>Vis oplysninger</Button>}
        </section>

        {a.payouts.length > 0 && (
          <section className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm space-y-space-sm">
            <h2 className="font-label-lg text-label-lg text-primary font-bold">Udbetalinger</h2>
            <ul className="font-body-sm text-body-sm divide-y divide-outline-variant/40">{a.payouts.map((p) => <li key={p.id} className="py-1.5 flex justify-between"><span>Nr. {p.number} · {p.status === "paid" ? `betalt ${date(p.paid_at)}` : p.status === "pending" ? "afventer" : "annulleret"}</span><span className="tabular-nums">{kr(p.amount_minor)}</span></li>)}</ul>
          </section>
        )}
      </aside>
    </div>
  );
}

function CustomerRow({ c, others }: { c: OpDetail["customers"][number]; others: { id: string; full_name: string }[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");
  const move = useSubmit(async () => {
    await api(`/operator/ambassadors/referrals/${c.workspace_id}`, { method: "PUT", body: JSON.stringify({ ambassador_id: to || null, reason }) });
    router.refresh();
  });
  return (
    <li className="p-space-md space-y-space-sm">
      <div className="flex flex-wrap items-center justify-between gap-space-sm font-body-sm text-body-sm">
        <div><p className="font-semibold">{c.company}</p><p className="text-on-surface-variant">{c.status} · via {c.via} · oprettet {date(c.signed_up)} · andel til {monthLabel(c.share_until)}</p></div>
        <div className="flex items-center gap-space-sm"><span className="tabular-nums font-semibold">{kr(c.earned_minor)}</span><button type="button" onClick={() => setOpen(!open)} className="font-label-md text-label-md text-primary underline">Flyt</button></div>
      </div>
      {open && (
        <div className="rounded-lg bg-surface-container-low p-space-sm grid sm:grid-cols-3 gap-space-sm items-end">
          <ErrorBox error={move.error} />
          <Field label="Til"><Select value={to} onChange={(e) => setTo(e.target.value)}><option value="">Ingen ambassadør (fjern)</option>{others.map((o) => <option key={o.id} value={o.id}>{o.full_name}</option>)}</Select></Field>
          <Field label="Begrundelse"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          <Button variant="tonal" disabled={move.pending || reason.trim().length < 3} onClick={() => move.run()}>Flyt kunde</Button>
        </div>
      )}
    </li>
  );
}
