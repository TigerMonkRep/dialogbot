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
      className="inline-flex items-center gap-1 px-space-sm py-1.5 rounded-lg bg-surface-container-low text-primary font-label-md text-label-md hover:bg-surface-container">
      <Icon name={done ? "check" : "content_copy"} size={16} />{done ? "Kopieret" : label}
    </button>
  );
}

function Stat({ label, value, hint, strong = false }: { label: string; value: string; hint?: string; strong?: boolean }) {
  return (
    <div className={`rounded-xl p-space-md ${strong ? "bg-primary text-on-primary" : "bg-surface-container-lowest shadow-sm"}`}>
      <p className={`font-label-sm text-label-sm uppercase tracking-wider font-bold ${strong ? "text-secondary-fixed" : "text-on-surface-variant"}`}>{label}</p>
      <p className="font-headline-md text-headline-md font-bold tabular-nums mt-1">{value}</p>
      {hint && <p className={`font-label-sm text-label-sm mt-0.5 ${strong ? "opacity-80" : "text-on-surface-variant"}`}>{hint}</p>}
    </div>
  );
}

const ENTRY_TONE: Record<string, string> = {
  held: "bg-tertiary-fixed text-on-tertiary-fixed", payable: "bg-secondary-container text-on-secondary-container",
  paid: "bg-surface-container-high text-on-surface", reversed: "bg-error-container text-on-error-container",
};

export function Portal({ me, customers, ledger, payouts }: { me: Profile; customers: Customer[]; ledger: Entry[]; payouts: Payout[] }) {
  const [tab, setTab] = useState<Tab>("overblik");
  const b = me.balances;
  const st = STATUS[me.status];
  return (
    <div className="space-y-space-lg">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-space-sm">
        <div>
          <span className={`inline-flex px-2.5 py-0.5 rounded-full font-label-sm text-label-sm font-bold ${st.tone}`}>{st.label}</span>
          <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight mt-1">Hej {me.full_name.split(" ")[0]}</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Din aftale: {kr(me.terms.bonus_minor)} i startbonus pr. kunde + {pct(me.terms.rate_bp)} af det, de betaler, i {me.terms.months} måneder.</p>
        </div>
      </div>

      {me.status === "pending" && <Alert kind="info">Vi kigger på din tilmelding og godkender normalt inden for et par dage. Dit link virker, så snart du er godkendt.</Alert>}
      {me.status === "rejected" && <Alert kind="warn">Vi kunne desværre ikke godkende dig som ambassadør.{me.decision_note ? ` ${me.decision_note}` : ""}</Alert>}
      {me.status === "suspended" && <Alert kind="warn">Din aftale er sat på pause, og dit link virker ikke lige nu.{me.decision_note ? ` Begrundelse: ${me.decision_note}` : ""}</Alert>}
      {me.minor && !me.parent_consent_at && <ParentPending email={me.parent_email} />}

      <nav className="flex gap-1 overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0" aria-label="Faner">
        {TABS.map(([k, l, i]) => (
          <button key={k} type="button" onClick={() => setTab(k)} aria-current={tab === k ? "page" : undefined}
            className={`flex items-center gap-1 px-space-md py-2 rounded-lg whitespace-nowrap font-label-md text-label-md ${tab === k ? "bg-primary text-on-primary" : "text-on-surface-variant hover:bg-surface-container"}`}>
            <Icon name={i} size={18} />{l}{k === "oplysninger" && me.payout_blockers.length > 0 && me.status === "active" && <span className="w-2 h-2 rounded-full bg-error" />}
          </button>
        ))}
      </nav>

      {tab === "overblik" && (
        <div className="space-y-space-lg">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-space-md">
            <Stat strong label="Klar til udbetaling" value={kr(b.payable_minor)} hint={b.payable_minor >= b.min_payout_minor ? "Udbetales ved næste kørsel" : `Udbetales fra ${kr(b.min_payout_minor)}`} />
            <Stat label="Optjent – frigives" value={kr(b.held_minor)} hint={`Frigives ${me.terms.hold_days ?? 30} dage efter kundens betaling`} />
            <Stat label="Under udbetaling" value={kr(b.in_payout_minor)} />
            <Stat label="Udbetalt i alt" value={kr(b.paid_minor)} />
          </div>
          <section className="rounded-xl bg-surface-container-lowest p-space-lg shadow-sm space-y-space-md">
            <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Dit link og din kode</h2>
            {me.status === "active" ? (
              <div className="grid md:grid-cols-2 gap-space-md">
                <div className="rounded-lg bg-surface-container-low p-space-md space-y-space-xs min-w-0">
                  <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider font-bold">Personligt link</p>
                  <p className="font-body-md text-body-md text-primary font-semibold break-all select-all">{me.link}</p>
                  <Copy text={me.link} label="Kopiér link" />
                </div>
                <div className="rounded-lg bg-surface-container-low p-space-md space-y-space-xs">
                  <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider font-bold">Kode</p>
                  <p className="font-headline-md text-headline-md text-primary font-bold tracking-widest select-all">{me.code}</p>
                  <Copy text={me.code} label="Kopiér kode" />
                </div>
              </div>
            ) : <p className="font-body-sm text-body-sm text-on-surface-variant">Dit link og din kode vises her, når du er godkendt.</p>}
            <div className="grid grid-cols-3 gap-space-sm text-center">
              {[["Besøg (30 dage)", me.stats.clicks_30d], ["Kunder", me.stats.customers], ["Betalende", me.stats.paying]].map(([l, v]) => (
                <div key={l} className="rounded-lg bg-surface p-space-sm"><p className="font-headline-sm text-headline-sm font-bold text-primary tabular-nums">{v}</p><p className="font-label-sm text-label-sm text-on-surface-variant">{l}</p></div>
              ))}
            </div>
          </section>
          {me.payout_blockers.length > 0 && me.status === "active" && (
            <Alert kind="warn">Før vi kan udbetale: {me.payout_blockers.join(" · ")}. <button type="button" className="underline" onClick={() => setTab("oplysninger")}>Udfyld oplysninger</button></Alert>
          )}
        </div>
      )}

      {tab === "kunder" && (
        <section className="rounded-xl bg-surface-container-lowest shadow-sm overflow-hidden">
          {customers.length === 0 ? <p className="p-space-lg font-body-md text-body-md text-on-surface-variant">Ingen kunder endnu. Del dit link med en virksomhed, du kender – når de opretter sig, kommer de frem her.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left font-body-sm text-body-sm">
                <thead className="bg-surface-container-low font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider"><tr><th className="p-space-sm">Virksomhed</th><th className="p-space-sm">Status</th><th className="p-space-sm">Oprettet</th><th className="p-space-sm">Andel til</th><th className="p-space-sm text-right">Din bonus</th></tr></thead>
                <tbody>{customers.map((c) => (
                  <tr key={c.workspace_id} className="border-t border-outline-variant/40">
                    <td className="p-space-sm font-semibold text-on-surface">{c.company}<span className="block font-label-sm text-label-sm text-on-surface-variant font-normal">via {c.via === "code" ? "kode" : c.via === "link" ? "link" : "Dialogbot"}</span></td>
                    <td className="p-space-sm">{c.status}</td><td className="p-space-sm">{date(c.signed_up)}</td><td className="p-space-sm">{monthLabel(c.share_until)}</td>
                    <td className="p-space-sm text-right tabular-nums font-semibold">{kr(c.earned_minor)}</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          )}
          <p className="px-space-md py-space-sm font-label-sm text-label-sm text-on-surface-variant bg-surface">Af hensyn til kunderne ser du kun firmanavn, status og din bonus.</p>
        </section>
      )}

      {tab === "kontoudtog" && (
        <section className="rounded-xl bg-surface-container-lowest shadow-sm overflow-hidden">
          {ledger.length === 0 ? <p className="p-space-lg font-body-md text-body-md text-on-surface-variant">Ingen posteringer endnu. Du tjener første gang, når en af dine kunder har betalt sin første faktura.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left font-body-sm text-body-sm">
                <thead className="bg-surface-container-low font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider"><tr><th className="p-space-sm">Type</th><th className="p-space-sm">Kunde</th><th className="p-space-sm">Måned</th><th className="p-space-sm">Status</th><th className="p-space-sm text-right">Beløb</th></tr></thead>
                <tbody>{ledger.map((e) => (
                  <tr key={e.id} className="border-t border-outline-variant/40">
                    <td className="p-space-sm font-semibold">{e.label}{e.kind === "share" && <span className="block font-label-sm text-label-sm text-on-surface-variant font-normal">{pct(me.terms.rate_bp)} af {kr(e.base_minor)}</span>}</td>
                    <td className="p-space-sm">{e.company}</td><td className="p-space-sm">{monthLabel(e.month)}</td>
                    <td className="p-space-sm"><span className={`inline-flex px-2 py-0.5 rounded-full font-label-sm text-label-sm ${ENTRY_TONE[e.status]}`}>{e.status_label}</span>{e.status === "held" && <span className="block font-label-sm text-label-sm text-on-surface-variant">{date(e.hold_until)}</span>}</td>
                    <td className={`p-space-sm text-right tabular-nums font-semibold ${e.amount_minor < 0 ? "text-error" : ""}`}>{kr(e.amount_minor)}</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {tab === "udbetalinger" && (
        <section className="rounded-xl bg-surface-container-lowest shadow-sm overflow-hidden">
          {payouts.length === 0 ? <p className="p-space-lg font-body-md text-body-md text-on-surface-variant">Ingen udbetalinger endnu. Vi udbetaler, når du har mindst {kr(b.min_payout_minor)} klar.</p> : (
            <ul>{payouts.map((p) => (
              <li key={p.id} className="border-t first:border-t-0 border-outline-variant/40">
                <Link href={`/ambassador/udbetalinger/${p.id}`} className="flex items-center justify-between gap-space-md p-space-md hover:bg-surface-container-low">
                  <div><p className="font-label-lg text-label-lg font-semibold">Afregning nr. {p.number}</p><p className="font-label-sm text-label-sm text-on-surface-variant">{p.status === "paid" ? `Udbetalt ${date(p.paid_at)}` : "Under udbetaling"} · {p.income_type === "b_income" ? "B-indkomst" : "Bilag til virksomhed"}</p></div>
                  <span className="font-headline-sm text-headline-sm font-bold tabular-nums text-primary">{kr(p.amount_minor)}</span>
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
    <div className="rounded-xl bg-tertiary-fixed text-on-tertiary-fixed p-space-md flex flex-col sm:flex-row sm:items-center gap-space-sm">
      <Icon name="family_restroom" size={24} />
      <p className="flex-1 font-body-sm text-body-sm">Vi venter på, at din forælder ({email}) godkender aftalen. Du kan godt skaffe kunder imens – vi udbetaler, når aftalen er godkendt.</p>
      <ErrorBox error={error} />
      {sent ? <span className="font-label-md text-label-md">Mail sendt igen</span> : <Button variant="outline" icon="forward_to_inbox" disabled={pending} onClick={() => run()}>Send mail igen</Button>}
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
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="rounded-xl bg-surface-container-lowest p-space-lg shadow-sm space-y-space-md max-w-2xl">
      <ErrorBox error={error} />
      {saved && <Alert kind="ok">Gemt.</Alert>}
      <dl className="grid grid-cols-2 gap-y-1 font-body-sm text-body-sm">
        <dt className="text-on-surface-variant">Navn</dt><dd>{me.full_name}</dd>
        <dt className="text-on-surface-variant">E-mail</dt><dd className="break-all">{me.email}</dd>
        {me.kind === "private" ? <><dt className="text-on-surface-variant">Fødselsdato</dt><dd>{date(me.birth_date)}</dd>
          <dt className="text-on-surface-variant">CPR</dt><dd>{me.has_cpr ? "Gemt (krypteret)" : <span className="text-error">Mangler</span>}</dd></>
          : <><dt className="text-on-surface-variant">Virksomhed</dt><dd>{me.company_name} · CVR {me.cvr}</dd></>}
        <dt className="text-on-surface-variant">Bankkonto</dt><dd>{me.has_bank ? `Slutter på ${me.bank_last4}` : <span className="text-error">Mangler</span>}</dd>
        {me.minor && <><dt className="text-on-surface-variant">Forælders godkendelse</dt><dd>{me.parent_consent_at ? `Godkendt ${date(me.parent_consent_at)}` : "Afventer"}</dd></>}
      </dl>
      {me.kind === "private" && <Field label={me.has_cpr ? "Nyt CPR-nummer" : "CPR-nummer"} hint="Bruges kun til at indberette din B-indkomst til Skattestyrelsen. Gemmes krypteret." error={fieldError(error, "cpr")}><Input value={f.cpr} onChange={set("cpr")} inputMode="numeric" autoComplete="off" placeholder="DDMMÅÅ-XXXX" /></Field>}
      <div className="grid grid-cols-3 gap-space-md">
        <Field label="Reg.nr." error={fieldError(error, "bank_reg")}><Input value={f.bank_reg} onChange={set("bank_reg")} inputMode="numeric" maxLength={4} /></Field>
        <div className="col-span-2"><Field label={me.has_bank ? "Nyt kontonummer" : "Kontonummer"} error={fieldError(error, "bank_account")}><Input value={f.bank_account} onChange={set("bank_account")} inputMode="numeric" /></Field></div>
      </div>
      <Field label="Mobilnummer"><Input value={f.phone} onChange={set("phone")} inputMode="tel" /></Field>
      <Field label="Din hilsen på din side" hint="Vises for dem, der åbner dit link."><Input maxLength={300} value={f.headline} onChange={set("headline")} /></Field>
      <Button type="submit" icon="save" disabled={pending}>{pending ? "Gemmer…" : "Gem"}</Button>
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
    <div className="space-y-space-md">
      <Alert kind="info">Husk reglerne: Skriv altid, at det er reklame, og at du får bonus. Send kun beskeder til folk, du kender eller har talt med. Ingen masse-mails eller -sms'er, og brug aldrig AI til at ringe folk op.</Alert>
      <section className="rounded-xl bg-surface-container-lowest p-space-lg shadow-sm space-y-space-sm">
        <h2 className="font-label-lg text-label-lg text-primary font-bold">Salgsmateriale til kunder</h2>
        <p className="font-body-sm text-body-sm text-on-surface">Brochuren fortæller om Dialogbot, funktioner og priser. Din personlige udgave har dit navn, dit link og din kode på forsiden – åbn den, og vælg &quot;Gem som PDF&quot; i browserens udskriftsmenu. Opsætningsmanualen viser kunden alle trin fra konto til første opkald.</p>
        <ul className="font-body-sm text-body-sm space-y-1">
          <li><a className="underline text-primary" target="_blank" rel="noopener" href={`/materiale/salgsmateriale.html?${new URLSearchParams({ navn: first, link: me.link, kode: me.code, rabat: String((me.terms.customer_discount_bp ?? 5000) / 100) })}`}>Din personlige brochure</a></li>
          <li><a className="underline text-primary" target="_blank" rel="noopener" href="/materiale/dialogbot-salgsmateriale.pdf">Brochure (PDF uden navn)</a></li>
          <li><a className="underline text-primary" target="_blank" rel="noopener" href="/materiale/dialogbot-opsaetningsmanual.pdf">Opsætningsmanual (PDF)</a></li>
          <li><a className="underline text-primary" target="_blank" rel="noopener" href="/materiale/dialogbot-ambassadoerhaandbog.pdf">Ambassadørhåndbogen (PDF) – til dig selv</a></li>
        </ul>
      </section>
      {texts.map(([title, text]) => (
        <section key={title} className="rounded-xl bg-surface-container-lowest p-space-lg shadow-sm space-y-space-sm">
          <div className="flex items-center justify-between gap-space-sm flex-wrap"><h2 className="font-label-lg text-label-lg text-primary font-bold">{title}</h2><Copy text={text} label="Kopiér tekst" /></div>
          <p className="font-body-sm text-body-sm text-on-surface whitespace-pre-line select-all">{text}</p>
        </section>
      ))}
      <p className="font-label-sm text-label-sm text-on-surface-variant">QR-kode, ambassadørkort og din egen side med foto kommer i næste version.</p>
    </div>
  );
}
