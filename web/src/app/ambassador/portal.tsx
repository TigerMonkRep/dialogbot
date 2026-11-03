"use client";
import Link from "@/i18n/link";
import { useLocale, useT } from "@/i18n/client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, useSubmit } from "@/components/ui";
import { STATUS, formatters, type Customer, type Entry, type Payout, type Profile } from "./shared";

type Tab = "overblik" | "kunder" | "kontoudtog" | "udbetalinger" | "oplysninger" | "materialer";
const TABS: [Tab, string][] = [
  ["overblik", "dashboard"], ["kunder", "storefront"], ["kontoudtog", "receipt_long"],
  ["udbetalinger", "payments"], ["oplysninger", "badge"], ["materialer", "share"],
];

function useFormat() {
  return formatters(useLocale());
}

function Copy({ text, label }: { text: string; label: string }) {
  const t = useT("auth.ambassador");
  const [done, setDone] = useState(false);
  return (
    <button type="button" onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* select manually */ } }}
      className="inline-flex items-center gap-1.5 min-h-[44px] px-3.5 rounded-xl border-2 border-ink bg-white text-ink text-[14px] font-semibold hover:bg-panel">
      <Icon name={done ? "check" : "content_copy"} size={16} />{done ? t("copied") : label}
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
  paid: "bg-panel text-ink border-ink", reversed: "bg-danger-soft text-danger border-danger-soft",
};

export function Portal({ me, customers, ledger, payouts }: { me: Profile; customers: Customer[]; ledger: Entry[]; payouts: Payout[] }) {
  const t = useT("auth.ambassador");
  const { date, kr, monthLabel, pct } = useFormat();
  const [tab, setTab] = useState<Tab>("overblik");
  const b = me.balances;
  const st = STATUS[me.status];
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div className="flex flex-col gap-2">
          <span className={`self-start inline-flex items-center min-h-6 px-2.5 rounded-full border-[1.5px] text-[12px] font-semibold uppercase tracking-[0.06em] ${st.tone}`}>{t(`status.${me.status}`)}</span>
          <h1 className="m-0 font-display font-extrabold text-[clamp(32px,4vw,46px)] leading-[1.05] tracking-[-1px] text-ink">{t("hello", { name: me.full_name.split(" ")[0] })}</h1>
          <p className="m-0 text-[15px] leading-normal text-ink-soft">{t("deal", { bonus: kr(me.terms.bonus_minor), rate: pct(me.terms.rate_bp), months: me.terms.months })}</p>
        </div>
      </div>

      {me.status === "pending" && <Alert kind="info">{t("pending")}</Alert>}
      {me.status === "rejected" && <Alert kind="warn">{t("rejected")}{me.decision_note ? ` ${me.decision_note}` : ""}</Alert>}
      {me.status === "suspended" && <Alert kind="warn">{t("suspended")}{me.decision_note ? ` ${t("reason", { note: me.decision_note })}` : ""}</Alert>}
      {me.minor && !me.parent_consent_at && <ParentPending email={me.parent_email} />}

      <nav className="flex gap-1.5 overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 py-1" aria-label={t("tabs.label")}>
        {TABS.map(([k, i]) => (
          <button key={k} type="button" onClick={() => setTab(k)} aria-current={tab === k ? "page" : undefined}
            className={`inline-flex items-center gap-1.5 min-h-[44px] px-4 rounded-full border-2 whitespace-nowrap text-[14px] font-semibold ${tab === k ? "bg-ink border-ink text-white" : "bg-white border-ink text-ink hover:bg-panel"}`}>
            <Icon name={i} size={18} />{t(`tabs.${k}`)}{k === "oplysninger" && me.payout_blockers.length > 0 && me.status === "active" && <span className="w-2.5 h-2.5 rounded-full bg-danger" aria-label={t("tabs.missingDetails")} />}
          </button>
        ))}
      </nav>

      {tab === "overblik" && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat strong label={t("overview.payable")} value={kr(b.payable_minor)} hint={b.payable_minor >= b.min_payout_minor ? t("overview.payableNext") : t("overview.payableFrom", { amount: kr(b.min_payout_minor) })} />
            <Stat label={t("overview.held")} value={kr(b.held_minor)} hint={t("overview.heldHint", { days: me.terms.hold_days ?? 30 })} />
            <Stat label={t("overview.inPayout")} value={kr(b.in_payout_minor)} />
            <Stat label={t("overview.paid")} value={kr(b.paid_minor)} />
          </div>
          <section className="rounded-2xl bg-white border-2 border-ink p-5 md:p-6 flex flex-col gap-4">
            <h2 className="m-0 font-display font-extrabold text-[22px] leading-[1.15] text-ink">{t("overview.linkTitle")}</h2>
            {me.status === "active" ? (
              <div className="grid md:grid-cols-2 gap-4">
                <div className="rounded-xl border-[1.5px] border-ink bg-panel p-4 flex flex-col items-start gap-2 min-w-0">
                  <p className="m-0 eyebrow">{t("overview.personalLink")}</p>
                  <p className="m-0 text-[15px] text-ink font-semibold break-all select-all">{me.link}</p>
                  <Copy text={me.link} label={t("overview.copyLink")} />
                </div>
                <div className="rounded-xl border-[1.5px] border-ink bg-panel p-4 flex flex-col items-start gap-2">
                  <p className="m-0 eyebrow">{t("overview.code")}</p>
                  <p className="m-0 font-display font-extrabold text-[26px] text-ink tracking-[0.2em] select-all">{me.code}</p>
                  <Copy text={me.code} label={t("overview.copyCode")} />
                </div>
              </div>
            ) : <p className="m-0 text-[15px] text-ink-soft">{t("overview.linkPending")}</p>}
            <div className="grid grid-cols-3 gap-3 text-center">
              {[[t("overview.visits"), me.stats.clicks_30d], [t("overview.customers"), me.stats.customers], [t("overview.paying"), me.stats.paying]].map(([l, v]) => (
                <div key={l} className="rounded-xl border-[1.5px] border-ink bg-white p-3"><p className="m-0 font-display font-extrabold text-[22px] text-ink tabular-nums">{v}</p><p className="m-0 text-[13px] text-muted">{l}</p></div>
              ))}
            </div>
          </section>
          {me.payout_blockers.length > 0 && me.status === "active" && (
            <Alert kind="warn">{t("overview.blockers", { list: me.payout_blockers.join(" · ") })} <button type="button" className="underline underline-offset-4 font-semibold min-h-[44px]" onClick={() => setTab("oplysninger")}>{t("overview.fillDetails")}</button></Alert>
          )}
        </div>
      )}

      {tab === "kunder" && (
        <section className="rounded-2xl bg-white border-2 border-ink overflow-hidden">
          {customers.length === 0 ? <p className="m-0 p-6 text-[15px] leading-normal text-ink-soft">{t("customers.empty")}</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[15px] text-ink">
                <thead className="bg-panel border-b-2 border-ink text-[12px] font-semibold text-muted uppercase tracking-[0.12em]"><tr><th className="px-4 py-3">{t("customers.company")}</th><th className="px-4 py-3">{t("customers.status")}</th><th className="px-4 py-3">{t("customers.created")}</th><th className="px-4 py-3">{t("customers.shareUntil")}</th><th className="px-4 py-3 text-right">{t("customers.bonus")}</th></tr></thead>
                <tbody>{customers.map((c) => (
                  <tr key={c.workspace_id} className="border-t-[1.5px] border-line">
                    <td className="px-4 py-3 font-semibold text-ink">{c.company}<span className="block text-[13px] text-muted font-normal">{t("customers.via", { source: c.via === "code" ? t("customers.viaCode") : c.via === "link" ? t("customers.viaLink") : "Dialogbot" })}</span></td>
                    <td className="px-4 py-3">{c.status}</td><td className="px-4 py-3">{date(c.signed_up)}</td><td className="px-4 py-3">{monthLabel(c.share_until)}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold">{kr(c.earned_minor)}</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          )}
          <p className="m-0 px-4 py-3 text-[13px] text-muted border-t-[1.5px] border-line">{t("customers.privacy")}</p>
        </section>
      )}

      {tab === "kontoudtog" && (
        <section className="rounded-2xl bg-white border-2 border-ink overflow-hidden">
          {ledger.length === 0 ? <p className="m-0 p-6 text-[15px] leading-normal text-ink-soft">{t("ledger.empty")}</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[15px] text-ink">
                <thead className="bg-panel border-b-2 border-ink text-[12px] font-semibold text-muted uppercase tracking-[0.12em]"><tr><th className="px-4 py-3">{t("ledger.type")}</th><th className="px-4 py-3">{t("ledger.customer")}</th><th className="px-4 py-3">{t("ledger.month")}</th><th className="px-4 py-3">{t("ledger.status")}</th><th className="px-4 py-3 text-right">{t("ledger.amount")}</th></tr></thead>
                <tbody>{ledger.map((e) => (
                  <tr key={e.id} className="border-t-[1.5px] border-line">
                    <td className="px-4 py-3 font-semibold">{e.label}{e.kind === "share" && <span className="block text-[13px] text-muted font-normal">{t("ledger.shareOf", { rate: pct(me.terms.rate_bp), base: kr(e.base_minor) })}</span>}</td>
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
          {payouts.length === 0 ? <p className="m-0 p-6 text-[15px] leading-normal text-ink-soft">{t("payouts.empty", { amount: kr(b.min_payout_minor) })}</p> : (
            <ul>{payouts.map((p) => (
              <li key={p.id} className="border-t-[1.5px] first:border-t-0 border-line">
                <Link href={`/ambassador/udbetalinger/${p.id}`} className="flex items-center justify-between gap-4 p-4 min-h-[44px] text-ink no-underline hover:bg-panel">
                  <div><p className="m-0 text-[15px] font-semibold">{t("payouts.settlement", { number: p.number })}</p><p className="m-0 text-[13px] text-muted">{p.status === "paid" ? t("payouts.paidOn", { date: date(p.paid_at) }) : t("payouts.inPayout")} · {p.income_type === "b_income" ? t("payouts.bIncome") : t("payouts.invoice")}</p></div>
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
  const t = useT("auth.ambassador.parent");
  const [sent, setSent] = useState(false);
  const { run, pending, error } = useSubmit(async () => { await api("/ambassador/me/parent-consent/resend", { method: "POST" }); setSent(true); });
  return (
    <div className="rounded-xl border-[1.5px] border-ink bg-highlight text-ink p-4 flex flex-col sm:flex-row sm:items-center gap-3">
      <Icon name="family_restroom" size={24} />
      <p className="m-0 flex-1 text-[15px] leading-normal">{t("waiting", { email: email ?? "" })}</p>
      <ErrorBox error={error} />
      {sent ? <span className="text-[14px] font-semibold">{t("sent")}</span> : <Button variant="outline" icon="forward_to_inbox" disabled={pending} onClick={() => run()}>{t("resend")}</Button>}
    </div>
  );
}

function Details({ me }: { me: Profile }) {
  const t = useT("auth.ambassador.details");
  const { date } = useFormat();
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
      {saved && <Alert kind="ok">{t("saved")}</Alert>}
      <dl className="m-0 grid grid-cols-2 gap-y-1.5 text-[15px] text-ink">
        <dt className="text-muted">{t("name")}</dt><dd>{me.full_name}</dd>
        <dt className="text-muted">{t("email")}</dt><dd className="break-all">{me.email}</dd>
        {me.kind === "private" ? <><dt className="text-muted">{t("birthDate")}</dt><dd>{date(me.birth_date)}</dd>
          <dt className="text-muted">{t("cpr")}</dt><dd>{me.has_cpr ? t("cprSaved") : <span className="text-danger font-semibold">{t("missing")}</span>}</dd></>
          : <><dt className="text-muted">{t("company")}</dt><dd>{t("companyValue", { company: me.company_name ?? "", cvr: me.cvr ?? "" })}</dd></>}
        <dt className="text-muted">{t("bank")}</dt><dd>{me.has_bank ? t("bankEnds", { last4: me.bank_last4 ?? "" }) : <span className="text-danger font-semibold">{t("missing")}</span>}</dd>
        {me.minor && <><dt className="text-muted">{t("parentConsent")}</dt><dd>{me.parent_consent_at ? t("approvedOn", { date: date(me.parent_consent_at) }) : t("awaiting")}</dd></>}
      </dl>
      {me.kind === "private" && <Field label={me.has_cpr ? t("newCpr") : t("cprNumber")} hint={t("cprHint")} error={fieldError(error, "cpr")}><Input value={f.cpr} onChange={set("cpr")} inputMode="numeric" autoComplete="off" placeholder={t("cprPlaceholder")} /></Field>}
      <div className="grid grid-cols-3 gap-4">
        <Field label={t("regNo")} error={fieldError(error, "bank_reg")}><Input value={f.bank_reg} onChange={set("bank_reg")} inputMode="numeric" maxLength={4} /></Field>
        <div className="col-span-2"><Field label={me.has_bank ? t("newAccount") : t("account")} error={fieldError(error, "bank_account")}><Input value={f.bank_account} onChange={set("bank_account")} inputMode="numeric" /></Field></div>
      </div>
      <Field label={t("phone")}><Input value={f.phone} onChange={set("phone")} inputMode="tel" /></Field>
      <Field label={t("headline")} hint={t("headlineHint")}><Input maxLength={300} value={f.headline} onChange={set("headline")} /></Field>
      <Button type="submit" icon="save" disabled={pending} className="self-start">{pending ? t("saving") : t("save")}</Button>
    </form>
  );
}

function Materials({ me }: { me: Profile }) {
  const t = useT("auth.ambassador.materials");
  const { pct } = useFormat();
  const first = me.full_name.split(" ")[0];
  const d = pct(me.terms.customer_discount_bp ?? 5000);
  const v = { discount: d, link: me.link, code: me.code, name: first };
  const texts: [string, string][] = (["personal", "social", "linkedin", "inPerson"] as const).map((k) => [t(`${k}Title`), t(`${k}Text`, v)]);
  return (
    <div className="flex flex-col gap-4">
      <Alert kind="info">{t("rules")}</Alert>
      <section className="rounded-2xl bg-white border-2 border-ink p-5 md:p-6 flex flex-col gap-3">
        <h2 className="m-0 font-display font-extrabold text-[20px] leading-[1.15] text-ink">{t("salesTitle")}</h2>
        <p className="m-0 text-[15px] leading-normal text-ink-soft">{t("salesText")}</p>
        <ul className="m-0 p-0 list-none text-[15px] flex flex-col gap-1">
          <li><a className="inline-flex items-center min-h-[44px] sm:min-h-0 sm:py-1 underline underline-offset-4 text-accent font-semibold" target="_blank" rel="noopener" href={`/materiale/salgsmateriale.html?${new URLSearchParams({ navn: first, link: me.link, kode: me.code, rabat: String((me.terms.customer_discount_bp ?? 5000) / 100) })}`}>{t("personalBrochure")}</a></li>
          <li><a className="inline-flex items-center min-h-[44px] sm:min-h-0 sm:py-1 underline underline-offset-4 text-accent font-semibold" target="_blank" rel="noopener" href="/materiale/dialogbot-salgsmateriale.pdf">{t("brochurePdf")}</a></li>
          <li><a className="inline-flex items-center min-h-[44px] sm:min-h-0 sm:py-1 underline underline-offset-4 text-accent font-semibold" target="_blank" rel="noopener" href="/materiale/dialogbot-opsaetningsmanual.pdf">{t("setupManual")}</a></li>
          <li><a className="inline-flex items-center min-h-[44px] sm:min-h-0 sm:py-1 underline underline-offset-4 text-accent font-semibold" target="_blank" rel="noopener" href="/materiale/dialogbot-ambassadoerhaandbog.pdf">{t("handbook")}</a></li>
        </ul>
      </section>
      {texts.map(([title, text]) => (
        <section key={title} className="rounded-2xl bg-white border-2 border-ink p-5 md:p-6 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3 flex-wrap"><h2 className="m-0 font-display font-bold text-[18px] leading-[1.2] text-ink">{title}</h2><Copy text={text} label={t("copyText")} /></div>
          <p className="m-0 text-[15px] leading-normal text-ink-soft whitespace-pre-line select-all">{text}</p>
        </section>
      ))}
      <p className="m-0 text-[13px] text-muted">{t("nextVersion")}</p>
    </div>
  );
}
