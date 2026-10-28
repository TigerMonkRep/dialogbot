"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, useSubmit } from "@/components/ui";
import { STATUS, date, kr, monthLabel, pct, type Customer, type Entry, type Payout, type Profile } from "./shared";

type Tab = "overblik" | "kunder" | "kontoudtog" | "udbetalinger" | "oplysninger" | "materialer";
const TABS: [Tab, string, string][] = [
  ["overblik", "Overblik", "dashboard"], ["kunder", "Kunder", "storefront"], ["kontoudtog", "Kontoudtog", "receipt_long"],
  ["udbetalinger", "Udbetalinger", "payments"], ["oplysninger", "Oplysninger", "badge"], ["materialer", "Del og tekster", "share"],
];

function Copy({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* select manually */ } }}
      className="inline-flex items-center gap-1.5 min-h-[44px] px-3.5 rounded-xl border-2 border-ink bg-white text-ink text-[14px] font-semibold hover:bg-panel">
      <Icon name={done ? "check" : "content_copy"} size={16} />{done ? "Kopieret" : label}
    </button>
  );
}

function Stat({ label, value, hint, strong = false }: { label: string; value: string; hint?: string; strong?: boolean }) {
  return (
    <div className={`rounded-2xl border-2 border-ink p-4 ${strong ? "bg-ink text-white shadow-block" : "bg-white text-ink"}`}>
      <p className={`m-0 text-[12px] font-semibold uppercase tracking-[0.12em] ${strong ? "text-highlight" : "text-muted"}`}>{label}</p>
      <p className="m-0 font-display font-extrabold text-[26px] leading-[1.1] tracking-[-0.5px] tabular-nums mt-1.5">{value}</p>
      {hint && <p className={`m-0 text-[13px] mt-1 ${strong ? "text-white/75" : "text-muted"}`}>{hint}</p>}
    </div>
  );
}

const ENTRY_TONE: Record<string, string> = {
  held: "bg-highlight text-ink border-highlight", payable: "bg-success-soft text-success border-success-soft",
  paid: "bg-panel text-ink border-ink", reversed: "bg-danger-soft text-on-error-container border-danger-soft",
};

export function Portal({ me, customers, ledger, payouts }: { me: Profile; customers: Customer[]; ledger: Entry[]; payouts: Payout[] }) {
  const [tab, setTab] = useState<Tab>("overblik");
  const b = me.balances;
  const st = STATUS[me.status];
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div className="flex flex-col gap-2">
          <span className={`self-start inline-flex items-center min-h-6 px-2.5 rounded-full border-[1.5px] text-[12px] font-semibold uppercase tracking-[0.06em] ${st.tone}`}>{st.label}</span>
          <h1 className="m-0 font-display font-extrabold text-[clamp(32px,4vw,46px)] leading-[1.05] tracking-[-1px] text-ink">Hej {me.full_name.split(" ")[0]}</h1>
          <p className="m-0 text-[15px] leading-normal text-ink-soft">Din aftale: {kr(me.terms.bonus_minor)} i startbonus pr. kunde + {pct(me.terms.rate_bp)} af det, de betaler, i {me.terms.months} måneder.</p>
        </div>
      </div>

      {me.status === "pending" && <Alert kind="info">Vi kigger på din tilmelding og godkender normalt inden for et par dage. Dit link virker, så snart du er godkendt.</Alert>}
      {me.status === "rejected" && <Alert kind="warn">Vi kunne desværre ikke godkende dig som ambassadør.{me.decision_note ? ` ${me.decision_note}` : ""}</Alert>}
      {me.status === "suspended" && <Alert kind="warn">Din aftale er sat på pause, og dit link virker ikke lige nu.{me.decision_note ? ` Begrundelse: ${me.decision_note}` : ""}</Alert>}
      {me.minor && !me.parent_consent_at && <ParentPending email={me.parent_email} />}

      <nav className="flex gap-1.5 overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 py-1" aria-label="Faner">
        {TABS.map(([k, l, i]) => (
          <button key={k} type="button" onClick={() => setTab(k)} aria-current={tab === k ? "page" : undefined}
            className={`inline-flex items-center gap-1.5 min-h-[44px] px-4 rounded-full border-2 whitespace-nowrap text-[14px] font-semibold ${tab === k ? "bg-ink border-ink text-white" : "bg-white border-ink text-ink hover:bg-panel"}`}>
            <Icon name={i} size={18} />{l}{k === "oplysninger" && me.payout_blockers.length > 0 && me.status === "active" && <span className="w-2.5 h-2.5 rounded-full bg-danger" aria-label="Mangler oplysninger" />}
          </button>
        ))}
      </nav>

      {tab === "overblik" && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat strong label="Klar til udbetaling" value={kr(b.payable_minor)} hint={b.payable_minor >= b.min_payout_minor ? "Udbetales ved næste kørsel" : `Udbetales fra ${kr(b.min_payout_minor)}`} />
            <Stat label="Optjent – frigives" value={kr(b.held_minor)} hint={`Frigives ${me.terms.hold_days ?? 30} dage efter kundens betaling`} />
            <Stat label="Under udbetaling" value={kr(b.in_payout_minor)} />
            <Stat label="Udbetalt i alt" value={kr(b.paid_minor)} />
          </div>
          <section className="rounded-2xl bg-white border-2 border-ink p-5 md:p-6 flex flex-col gap-4">
            <h2 className="m-0 font-display font-extrabold text-[22px] leading-[1.15] text-ink">Dit link og din kode</h2>
            {me.status === "active" ? (
              <div className="grid md:grid-cols-2 gap-4">
                <div className="rounded-xl border-[1.5px] border-ink bg-panel p-4 flex flex-col items-start gap-2 min-w-0">
                  <p className="m-0 eyebrow">Personligt link</p>
                  <p className="m-0 text-[15px] text-ink font-semibold break-all select-all">{me.link}</p>
                  <Copy text={me.link} label="Kopiér link" />
                </div>
                <div className="rounded-xl border-[1.5px] border-ink bg-panel p-4 flex flex-col items-start gap-2">
                  <p className="m-0 eyebrow">Kode</p>
                  <p className="m-0 font-display font-extrabold text-[26px] text-ink tracking-[0.2em] select-all">{me.code}</p>
                  <Copy text={me.code} label="Kopiér kode" />
                </div>
              </div>
            ) : <p className="m-0 text-[15px] text-ink-soft">Dit link og din kode vises her, når du er godkendt.</p>}
            <div className="grid grid-cols-3 gap-3 text-center">
              {[["Besøg (30 dage)", me.stats.clicks_30d], ["Kunder", me.stats.customers], ["Betalende", me.stats.paying]].map(([l, v]) => (
                <div key={l} className="rounded-xl border-[1.5px] border-ink bg-white p-3"><p className="m-0 font-display font-extrabold text-[22px] text-ink tabular-nums">{v}</p><p className="m-0 text-[13px] text-muted">{l}</p></div>
              ))}
            </div>
          </section>
          {me.payout_blockers.length > 0 && me.status === "active" && (
            <Alert kind="warn">Før vi kan udbetale: {me.payout_blockers.join(" · ")}. <button type="button" className="underline underline-offset-4 font-semibold min-h-[44px]" onClick={() => setTab("oplysninger")}>Udfyld oplysninger</button></Alert>
          )}
        </div>
      )}

      {tab === "kunder" && (
        <section className="rounded-2xl bg-white border-2 border-ink overflow-hidden">
          {customers.length === 0 ? <p className="m-0 p-6 text-[15px] leading-normal text-ink-soft">Ingen kunder endnu. Del dit link med en virksomhed, du kender – når de opretter sig, kommer de frem her.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[15px] text-ink">
                <thead className="bg-panel border-b-2 border-ink text-[12px] font-semibold text-muted uppercase tracking-[0.12em]"><tr><th className="px-4 py-3">Virksomhed</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Oprettet</th><th className="px-4 py-3">Andel til</th><th className="px-4 py-3 text-right">Din bonus</th></tr></thead>
                <tbody>{customers.map((c) => (
                  <tr key={c.workspace_id} className="border-t-[1.5px] border-line">
                    <td className="px-4 py-3 font-semibold text-ink">{c.company}<span className="block text-[13px] text-muted font-normal">via {c.via === "code" ? "kode" : c.via === "link" ? "link" : "Dialogbot"}</span></td>
                    <td className="px-4 py-3">{c.status}</td><td className="px-4 py-3">{date(c.signed_up)}</td><td className="px-4 py-3">{monthLabel(c.share_until)}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold">{kr(c.earned_minor)}</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          )}
          <p className="m-0 px-4 py-3 text-[13px] text-muted border-t-[1.5px] border-line">Af hensyn til kunderne ser du kun firmanavn, status og din bonus.</p>
        </section>
      )}

      {tab === "kontoudtog" && (
        <section className="rounded-2xl bg-white border-2 border-ink overflow-hidden">
          {ledger.length === 0 ? <p className="m-0 p-6 text-[15px] leading-normal text-ink-soft">Ingen posteringer endnu. Du tjener første gang, når en af dine kunder har betalt sin første faktura.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[15px] text-ink">
                <thead className="bg-panel border-b-2 border-ink text-[12px] font-semibold text-muted uppercase tracking-[0.12em]"><tr><th className="px-4 py-3">Type</th><th className="px-4 py-3">Kunde</th><th className="px-4 py-3">Måned</th><th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Beløb</th></tr></thead>
                <tbody>{ledger.map((e) => (
                  <tr key={e.id} className="border-t-[1.5px] border-line">
                    <td className="px-4 py-3 font-semibold">{e.label}{e.kind === "share" && <span className="block text-[13px] text-muted font-normal">{pct(me.terms.rate_bp)} af {kr(e.base_minor)}</span>}</td>
                    <td className="px-4 py-3">{e.company}</td><td className="px-4 py-3">{monthLabel(e.month)}</td>
                    <td className="px-4 py-3"><span className={`inline-flex items-center rounded-full border-[1.5px] px-2.5 py-0.5 text-[12px] font-semibold uppercase tracking-[0.06em] whitespace-nowrap ${ENTRY_TONE[e.status]}`}>{e.status_label}</span>{e.status === "held" && <span className="block text-[13px] text-muted mt-1">{date(e.hold_until)}</span>}</td>
                    <td className={`px-4 py-3 text-right tabular-nums font-semibold ${e.amount_minor < 0 ? "text-danger" : ""}`}>{kr(e.amount_minor)}</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {tab === "udbetalinger" && (
        <section className="rounded-2xl bg-white border-2 border-ink overflow-hidden">
          {payouts.length === 0 ? <p className="m-0 p-6 text-[15px] leading-normal text-ink-soft">Ingen udbetalinger endnu. Vi udbetaler, når du har mindst {kr(b.min_payout_minor)} klar.</p> : (
            <ul>{payouts.map((p) => (
              <li key={p.id} className="border-t-[1.5px] first:border-t-0 border-line">
                <Link href={`/ambassador/udbetalinger/${p.id}`} className="flex items-center justify-between gap-4 p-4 min-h-[44px] text-ink no-underline hover:bg-panel">
                  <div><p className="m-0 text-[15px] font-semibold">Afregning nr. {p.number}</p><p className="m-0 text-[13px] text-muted">{p.status === "paid" ? `Udbetalt ${date(p.paid_at)}` : "Under udbetaling"} · {p.income_type === "b_income" ? "B-indkomst" : "Bilag til virksomhed"}</p></div>
                  <span className="font-display font-extrabold text-[20px] tabular-nums text-ink">{kr(p.amount_minor)}</span>
                </Link>
              </li>))}
            </ul>
          )}
        </section>
      )}

      {tab === "oplysninger" && <Details me={me} />}
      {tab === "materialer" && <Materials me={me} />}
    </div>
  );
}

function ParentPending({ email }: { email: string | null }) {
  const [sent, setSent] = useState(false);
  const { run, pending, error } = useSubmit(async () => { await api("/ambassador/me/parent-consent/resend", { method: "POST" }); setSent(true); });
  return (
    <div className="rounded-xl border-[1.5px] border-ink bg-highlight text-ink p-4 flex flex-col sm:flex-row sm:items-center gap-3">
      <Icon name="family_restroom" size={24} />
      <p className="m-0 flex-1 text-[15px] leading-normal">Vi venter på, at din forælder ({email}) godkender aftalen. Du kan godt skaffe kunder imens – vi udbetaler, når aftalen er godkendt.</p>
      <ErrorBox error={error} />
      {sent ? <span className="text-[14px] font-semibold">Mail sendt igen</span> : <Button variant="outline" icon="forward_to_inbox" disabled={pending} onClick={() => run()}>Send mail igen</Button>}
    </div>
  );
}

function Details({ me }: { me: Profile }) {
  const router = useRouter();
  const [f, setF] = useState({ cpr: "", bank_reg: "", bank_account: "", headline: me.headline, phone: me.phone });
  const [saved, setSaved] = useState(false);
  const { run, pending, error } = useSubmit(async () => {
    setSaved(false);
    await api("/ambassador/me", { method: "PUT", body: JSON.stringify({
      cpr: f.cpr || null, bank_reg: f.bank_reg || null, bank_account: f.bank_account || null, headline: f.headline, phone: f.phone, expected_version: me.version,
    }) });
    setF({ ...f, cpr: "", bank_reg: "", bank_account: "" }); setSaved(true); router.refresh();
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="rounded-2xl bg-white border-2 border-ink p-5 md:p-6 flex flex-col gap-4 max-w-2xl">
      <ErrorBox error={error} />
      {saved && <Alert kind="ok">Gemt.</Alert>}
      <dl className="m-0 grid grid-cols-2 gap-y-1.5 text-[15px] text-ink">
        <dt className="text-muted">Navn</dt><dd>{me.full_name}</dd>
        <dt className="text-muted">E-mail</dt><dd className="break-all">{me.email}</dd>
        {me.kind === "private" ? <><dt className="text-muted">Fødselsdato</dt><dd>{date(me.birth_date)}</dd>
          <dt className="text-muted">CPR</dt><dd>{me.has_cpr ? "Gemt (krypteret)" : <span className="text-danger font-semibold">Mangler</span>}</dd></>
          : <><dt className="text-muted">Virksomhed</dt><dd>{me.company_name} · CVR {me.cvr}</dd></>}
        <dt className="text-muted">Bankkonto</dt><dd>{me.has_bank ? `Slutter på ${me.bank_last4}` : <span className="text-danger font-semibold">Mangler</span>}</dd>
        {me.minor && <><dt className="text-muted">Forælders godkendelse</dt><dd>{me.parent_consent_at ? `Godkendt ${date(me.parent_consent_at)}` : "Afventer"}</dd></>}
      </dl>
      {me.kind === "private" && <Field label={me.has_cpr ? "Nyt CPR-nummer" : "CPR-nummer"} hint="Bruges kun til at indberette din B-indkomst til Skattestyrelsen. Gemmes krypteret." error={fieldError(error, "cpr")}><Input value={f.cpr} onChange={set("cpr")} inputMode="numeric" autoComplete="off" placeholder="DDMMÅÅ-XXXX" /></Field>}
      <div className="grid grid-cols-3 gap-4">
        <Field label="Reg.nr." error={fieldError(error, "bank_reg")}><Input value={f.bank_reg} onChange={set("bank_reg")} inputMode="numeric" maxLength={4} /></Field>
        <div className="col-span-2"><Field label={me.has_bank ? "Nyt kontonummer" : "Kontonummer"} error={fieldError(error, "bank_account")}><Input value={f.bank_account} onChange={set("bank_account")} inputMode="numeric" /></Field></div>
      </div>
      <Field label="Mobilnummer"><Input value={f.phone} onChange={set("phone")} inputMode="tel" /></Field>
      <Field label="Din hilsen på din side" hint="Vises for dem, der åbner dit link."><Input maxLength={300} value={f.headline} onChange={set("headline")} /></Field>
      <Button type="submit" icon="save" disabled={pending} className="self-start">{pending ? "Gemmer…" : "Gem"}</Button>
    </form>
  );
}

function Materials({ me }: { me: Profile }) {
  const first = me.full_name.split(" ")[0];
  const d = pct(me.terms.customer_discount_bp ?? 5000);
  const texts: [string, string][] = [
    ["Personlig besked (sms eller Messenger til en du kender)", `Hej! Jeg er ambassadør for Dialogbot – en dansk AI-receptionist, der tager telefonen, når I ikke kan, og booker tider for jer. Via mit link får I ${d} rabat på første måned: ${me.link} (jeg får en lille bonus, hvis I bliver kunde). /${first}`],
    ["Opslag på Instagram, TikTok eller Facebook", `#reklame Kender du en virksomhed, der misser opkald? Dialogbot er en dansk AI-receptionist, der svarer telefonen 24/7 og booker tider. Brug mit link og få ${d} rabat på første måned: ${me.link} – jeg er ambassadør og får bonus, hvis du bliver kunde.`],
    ["LinkedIn", `Reklame: Jeg er ambassadør for Dialogbot. Den svarer telefonen for små virksomheder, når de selv er optaget, og booker tider direkte i kalenderen. Med mit link får I ${d} rabat på første måned: ${me.link}`],
    ["Når du står i butikken eller værkstedet", `"Mister I opkald, mens I har travlt? Jeg er ambassadør for Dialogbot – den tager telefonen og booker tider. Vil du høre den? Du kan selv bede den ringe dig op på hjemmesiden. Brug koden ${me.code}, så får I ${d} rabat."`],
  ];
  return (
    <div className="flex flex-col gap-4">
      <Alert kind="info">Husk reglerne: Skriv altid, at det er reklame, og at du får bonus. Send kun beskeder til folk, du kender eller har talt med. Ingen masse-mails eller -sms'er, og brug aldrig AI til at ringe folk op.</Alert>
      <section className="rounded-2xl bg-white border-2 border-ink p-5 md:p-6 flex flex-col gap-3">
        <h2 className="m-0 font-display font-extrabold text-[20px] leading-[1.15] text-ink">Salgsmateriale til kunder</h2>
        <p className="m-0 text-[15px] leading-normal text-ink-soft">Brochuren fortæller om Dialogbot, funktioner og priser. Din personlige udgave har dit navn, dit link og din kode på forsiden – åbn den, og vælg &quot;Gem som PDF&quot; i browserens udskriftsmenu. Opsætningsmanualen viser kunden alle trin fra konto til første opkald.</p>
        <ul className="m-0 p-0 list-none text-[15px] flex flex-col gap-1">
          <li><a className="inline-flex items-center min-h-[44px] sm:min-h-0 sm:py-1 underline underline-offset-4 text-accent font-semibold" target="_blank" rel="noopener" href={`/materiale/salgsmateriale.html?${new URLSearchParams({ navn: first, link: me.link, kode: me.code, rabat: String((me.terms.customer_discount_bp ?? 5000) / 100) })}`}>Din personlige brochure</a></li>
          <li><a className="inline-flex items-center min-h-[44px] sm:min-h-0 sm:py-1 underline underline-offset-4 text-accent font-semibold" target="_blank" rel="noopener" href="/materiale/dialogbot-salgsmateriale.pdf">Brochure (PDF uden navn)</a></li>
          <li><a className="inline-flex items-center min-h-[44px] sm:min-h-0 sm:py-1 underline underline-offset-4 text-accent font-semibold" target="_blank" rel="noopener" href="/materiale/dialogbot-opsaetningsmanual.pdf">Opsætningsmanual (PDF)</a></li>
          <li><a className="inline-flex items-center min-h-[44px] sm:min-h-0 sm:py-1 underline underline-offset-4 text-accent font-semibold" target="_blank" rel="noopener" href="/materiale/dialogbot-ambassadoerhaandbog.pdf">Ambassadørhåndbogen (PDF) – til dig selv</a></li>
        </ul>
      </section>
      {texts.map(([title, text]) => (
        <section key={title} className="rounded-2xl bg-white border-2 border-ink p-5 md:p-6 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3 flex-wrap"><h2 className="m-0 font-display font-bold text-[18px] leading-[1.2] text-ink">{title}</h2><Copy text={text} label="Kopiér tekst" /></div>
          <p className="m-0 text-[15px] leading-normal text-ink-soft whitespace-pre-line select-all">{text}</p>
        </section>
      ))}
      <p className="m-0 text-[13px] text-muted">QR-kode, ambassadørkort og din egen side med foto kommer i næste version.</p>
    </div>
  );
}
