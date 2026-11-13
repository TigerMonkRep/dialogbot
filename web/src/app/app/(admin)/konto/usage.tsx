"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { ErrorBox, inputCls, useSubmit } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";
import { formatPrice, currencyOr } from "@/lib/markets";

const BTN = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-[1.5px] border-ink bg-paper text-[14px] font-semibold text-ink hover:bg-panel disabled:opacity-50";
const BTN_PRIMARY = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-50";

type Dispute = { id: string; status: "open" | "approved" | "rejected"; credit_mode: "pool" | "invoice" | null; credit_net_minor: number; reason: string; decision_note?: string };
type Outcome = "answered" | "voicemail" | "no_answer";
type UsageCall = { kind: "inbound" | "outbound"; id: string; at: string; minutes: number; seconds?: number | null; pending?: boolean;
  package_minutes: number | null; extra_minutes: number | null; net_minor: number | null; call_net_minor?: number | null; outcome?: Outcome | null;
  credited: boolean; label: string | null; dispute: Dispute | null; can_dispute: boolean };
type Credit = { dispute_id: string; minutes: number; credit_net_minor: number; invoice_number: string | null; on_invoice: boolean };
type Usage = { month: string; shared_package: boolean; package: { included: number; used: number; remaining: number; over: number } | null;
  invoiced: boolean; invoice: { number?: string | null; lines: { kind: string; description?: string; net_minor: number }[]; currency: string;
    net_minor?: number; tax_minor?: number; gross_minor?: number; refunds?: { total_minor: number } } | null;
  credits?: Credit[]; calls: UsageCall[] };

/** 330 s → «5:30» (the call's length; billing rounds up to started minutes). */
const duration = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

const shift = (m: string, n: number) => { const d = new Date(`${m}-15T12:00:00Z`); d.setUTCMonth(d.getUTCMonth() + n); return d.toISOString().slice(0, 7); };

/** «Forbrug pr. opkald»: every billed call of the month with its minutes and the package, the invoice's frozen lines
 *  for an invoiced month, and «Klag over opkaldet» (the only way minutes are credited). */
export function UsagePerCall({ wsId, month: initial, currency, tz, canDispute }: { wsId: string; month: string; currency?: string; tz: string; canDispute: boolean }) {
  const t = useT("app");
  const lang = HTML_LANG[useLocale()];
  const [month, setMonth] = useState(initial);
  const [data, setData] = useState<Usage | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => { api<Usage>(`/workspaces/${wsId}/billing/usage?month=${month}`).then(setData).catch(() => setData(null)); }, [wsId, month, tick]);
  const cur = currencyOr(data?.invoice?.currency ?? currency);
  const money = (m: number) => formatPrice(m, cur, lang);
  const label = (m: string) => new Date(`${m}-15T12:00:00Z`).toLocaleDateString(lang, { month: "long", year: "numeric", timeZone: "UTC" });
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={BTN} onClick={() => setMonth(shift(month, -1))} aria-label={t("account.usage.prev")}>‹</button>
        <span className="font-semibold text-ink" aria-live="polite">{label(month)}</span>
        <button type="button" className={BTN} disabled={month >= initial} onClick={() => setMonth(shift(month, 1))} aria-label={t("account.usage.next")}>›</button>
      </div>
      {data?.package && <p className="text-[14px] text-ink-soft" data-testid="usage-package">{t("account.usage.packageLeft", { used: data.package.used, included: data.package.included, remaining: data.package.remaining, over: data.package.over })}</p>}
      {data?.invoiced && data.invoice && (
        <div className="rounded-xl border-[1.5px] border-line px-4 py-3 text-[14px]" data-testid="usage-invoice">
          <b className="text-ink">{t("account.usage.invoiced")}</b>
          <ul className="mt-1 flex flex-col gap-0.5 text-ink-soft">{data.invoice.lines.map((l, i) => <li key={i} className="flex justify-between gap-3"><span>{l.description ?? l.kind}</span><span className="tabular-nums">{money(l.net_minor)}</span></li>)}</ul>
          {data.invoice.net_minor !== undefined && <p className="mt-1 text-ink tabular-nums">{t("account.invoices.totals", { net: money(data.invoice.net_minor), tax: money(data.invoice.tax_minor ?? 0), gross: money(data.invoice.gross_minor ?? 0) })}</p>}
          {(data.invoice.refunds?.total_minor ?? 0) > 0 && <p className="mt-1 text-ink" role="status">{t("account.usage.refunded", { amount: money(data.invoice.refunds!.total_minor) })}</p>}
          {(data.credits ?? []).filter((c) => c.credit_net_minor > 0).map((c) => <p key={c.dispute_id} className="mt-1 text-ink" role="status">
            {c.on_invoice ? t("account.usage.creditOnInvoice", { amount: money(c.credit_net_minor), minutes: c.minutes, number: c.invoice_number ?? "" }) : t("account.usage.creditNext", { amount: money(c.credit_net_minor), minutes: c.minutes })}</p>)}
        </div>
      )}
      {!data ? null : data.calls.length === 0 ? <p className="text-[14px] text-ink-soft">{t("account.usage.none")}</p> : (
        <ul className="flex flex-col gap-2">{data.calls.map((c) => <CallRow key={`${c.kind}:${c.id}`} wsId={wsId} c={c} tz={tz} lang={lang} money={money} canDispute={canDispute} onDone={() => setTick(tick + 1)} />)}</ul>
      )}
      {data && !data.shared_package && <p className="text-[13px] text-muted">{t("account.usage.older")}</p>}
    </div>
  );
}

function CallRow({ wsId, c, tz, lang, money, canDispute, onDone }: { wsId: string; c: UsageCall; tz: string; lang: string; money: (m: number) => string; canDispute: boolean; onDone: () => void }) {
  const t = useT("app");
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const send = useSubmit(async () => {
    await api(`/workspaces/${wsId}/billing/disputes`, { method: "POST", body: JSON.stringify({ kind: c.kind, call_id: c.id, reason }) });
    setOpen(false); onDone();
  });
  const when = new Date(c.at).toLocaleString(lang, { dateStyle: "short", timeStyle: "short", timeZone: tz });
  const d = c.dispute;
  return (
    <li className="rounded-xl border-[1.5px] border-ink bg-paper px-3 py-2.5 text-[14px] flex flex-col gap-1.5" data-call={c.id}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-semibold text-ink">{when}</span>
        <span className="text-ink-soft">{c.kind === "inbound" ? t("account.usage.inbound") : t("account.usage.outbound")}{c.label ? ` · ${c.label}` : ""}</span>
        <span className="tabular-nums text-ink">{t("account.usage.minutes", { n: c.minutes })}</span>
        {c.seconds != null && <span className="tabular-nums text-ink-soft">{t("account.usage.duration", { d: duration(c.seconds) })}</span>}
      </div>
      {/* B03: how the package covered the call, and what it costs (minutes over the package + the call price by outcome) */}
      {c.pending ? <span className="text-[13px] text-ink-soft" data-testid="usage-pending">{t("account.usage.pending")}</span> : !c.credited && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[13px] text-ink-soft" data-testid="usage-split">
          <span>{c.extra_minutes ? t("account.usage.split", { pkg: c.package_minutes ?? 0, extra: c.extra_minutes }) : t("account.usage.inPackage", { n: c.package_minutes ?? c.minutes })}</span>
          {c.kind === "outbound" && c.outcome && <span>{t(`account.usage.outcome.${c.outcome}`)}</span>}
          {c.call_net_minor ? <span className="tabular-nums">{t("account.usage.callPrice", { amount: money(c.call_net_minor) })}</span> : null}
          {c.net_minor ? <span className="tabular-nums font-semibold text-ink">{t("account.usage.total", { amount: money(c.net_minor) })}</span> : null}
        </div>
      )}
      {c.pending && c.kind === "outbound" && c.call_net_minor ? <span className="text-[13px] text-ink-soft tabular-nums">{t("account.usage.callPrice", { amount: money(c.call_net_minor) })}</span> : null}
      {d && <span role="status" className="text-[13px] font-semibold text-ink">
        {d.status === "open" ? t("account.usage.disputeOpen")
          : d.status === "rejected" ? t("account.usage.disputeRejected")
          : d.credit_mode === "pool" ? t("account.usage.creditedPool")
          : d.credit_net_minor > 0 ? t("account.usage.creditedInvoice", { amount: money(d.credit_net_minor) }) : t("account.usage.creditedNothing")}
        {d.status !== "open" && d.decision_note ? <span className="block font-normal text-ink-soft">{t("account.usage.decisionNote", { note: d.decision_note })}</span> : null}
      </span>}
      {canDispute && c.can_dispute && !open && <button type="button" className={`${BTN} self-start`} onClick={() => setOpen(true)}>{t("account.usage.dispute")}</button>}
      {open && (
        <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); send.run(); }}>
          <label className="text-[13px] font-semibold" htmlFor={`reason-${c.id}`}>{t("account.usage.reason")}</label>
          <textarea id={`reason-${c.id}`} className={inputCls} rows={2} maxLength={2000} required value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="flex gap-2">
            <button type="submit" className={BTN_PRIMARY} disabled={send.pending || reason.trim().length < 5}>{t("account.usage.send")}</button>
            <button type="button" className={BTN} onClick={() => setOpen(false)}>{t("account.usage.cancel")}</button>
          </div>
          <ErrorBox error={send.error} />
        </form>
      )}
    </li>
  );
}
