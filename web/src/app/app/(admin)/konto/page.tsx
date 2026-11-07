import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { kr as krDa } from "../leads/format";
import { AddCard, ConfirmSubscription, DiscountCode, InvoiceMonth, ReferralCode } from "./billing";
import { InstallApp, InstallCapture } from "@/components/install-app";
import { PushSettings } from "@/components/push-ask";
import { InvitationRow, InviteForm, MemberRow } from "./team";
import { LogoutButton } from "./logout";
import { LanguageSection } from "./language";
import { getLocale, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";
import type { T } from "@/i18n/translate";

type Member = { id: string; user_id: string; email: string; display_name: string; role: string };
type Inv = { id: string; email: string; role: string; status: string; expires_at: string };
type Me = { id: string; email: string; display_name: string; email_verified: boolean; is_platform_operator?: boolean };
type Session = { id: string; created_at: string; last_seen_at: string; user_agent: string | null; current: boolean };
type Agreement = { current: { version: number; model: string; created_at: string; monthly: { net_minor: number } } | null; plan: { monthly_net_minor: number; campaign_call_net_minor: number; campaign_minute_net_minor: number; inbound_included_minutes: number; inbound_extra_minute_net_minor: number } };
type Statement = { month: string; lines: { kind: string; calls?: number; minutes?: number; included_minutes?: number; extra_minutes?: number; net_minor: number }[]; totals: { net_minor: number; tax_minor: number; gross_minor: number } };
type Account = { configured: boolean; card: { brand: string; last4: string; exp: string | null } | null; can_manage: boolean };
type Invoice = { id: string; month: string; status: string; number: string | null; gross_minor: number; hosted_invoice_url: string | null; invoice_pdf: string | null };
type Referral = { referred: boolean; ambassador_first_name?: string | null; customer_discount_bp?: number; can_add_code: boolean };
type Discount = { code: string | null; text?: string; from_month?: string; to_month?: string | null; can_add: boolean; can_manage: boolean };

/** Invoice statuses; labels are `app.account.invoiceStatus.<status>`. */
const INV_STATUS = ["creating", "open", "paid", "payment_failed", "failed", "void"];
const monthLabel = (lang: string, ym: string) => { const s = new Date(`${ym}-15T12:00:00`).toLocaleDateString(lang, { month: "long", year: "numeric" }); return s.charAt(0).toUpperCase() + s.slice(1); };
const shift = (ym: string, d: number) => { const [y, m] = ym.split("-").map(Number); const t = new Date(Date.UTC(y, m - 1 + d, 1)); return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}`; };
const dt = (lang: string, s: string) => new Date(s).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" });
function device(t: T, ua: string | null) {
  if (!ua) return t("account.me.unknownDevice");
  const os = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "";
  const br = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : t("account.me.browser");
  return os ? t("account.me.device", { browser: br, os }) : br;
}

const BOX = "flex flex-col gap-4 px-5 md:px-6 py-5 rounded-2xl bg-paper border-2 border-ink";

/** «Konto»: who may see and change, the subscription and the invoices – and your own login on the right. */
export default async function KontoPage({ searchParams }: { searchParams: Promise<{ card?: string }> }) {
  const ws = await requireWorkspace();
  const t = await getT("app");
  const lang = HTML_LANG[await getLocale()];
  const kr = (minor: number) => krDa(minor, lang);
  const admin = ws.role === "owner" || ws.role === "admin";
  const owner = ws.role === "owner";
  const { card } = await searchParams;
  const month = new Date().toISOString().slice(0, 7);
  const [members, invitations, me, sessions] = await Promise.all([
    backend<Member[]>(`/workspaces/${ws.id}/members`),
    admin ? backend<Inv[]>(`/workspaces/${ws.id}/invitations`) : Promise.resolve([] as Inv[]),
    backend<Me>("/auth/me"),
    backend<Session[]>("/auth/sessions").catch(() => [] as Session[]),
  ]);
  const [agr, st, acc, invoices, referral, discount] = admin ? await Promise.all([
    backend<Agreement>(`/workspaces/${ws.id}/agreement`),
    backend<Statement>(`/workspaces/${ws.id}/billing/statement`),
    backend<Account>(`/workspaces/${ws.id}/billing/account`),
    backend<{ items: Invoice[] }>(`/workspaces/${ws.id}/billing/invoices`),
    backend<Referral>(`/workspaces/${ws.id}/referral`),
    backend<Discount>(`/workspaces/${ws.id}/billing/discount`).catch(() => null),
  ]) : [null, null, null, null, null, null];
  const pending = invitations.filter((i) => i.status === "pending");
  const confirmed = !!agr?.current && agr.current.model !== "B";
  const campaignCalls = st?.lines.filter((l) => l.kind === "campaign_calls").reduce((n, l) => n + (l.calls ?? 0), 0) ?? 0;
  const campaignNet = st?.lines.filter((l) => l.kind === "campaign_calls").reduce((n, l) => n + l.net_minor, 0) ?? 0;
  const campaignMinutes = st?.lines.filter((l) => l.kind === "campaign_calls").reduce((n, l) => n + (l.minutes ?? 0), 0) ?? 0;
  const inbound = st?.lines.find((l) => l.kind === "inbound_minutes");
  const previous = shift(month, -1);
  const initials = me.display_name.split(/\s+/).map((s) => s[0]).join("").slice(0, 2).toUpperCase();
  return (
    <div className="flex flex-wrap gap-6 items-start">
      <InstallCapture />
      <div className="flex-[999_1_460px] min-w-0 flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <span className="eyebrow">{t("account.eyebrow")}</span>
          <h1 className="font-display font-extrabold text-[26px] sm:text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{t("account.title")}</h1>
        </div>

        <section className={BOX} aria-labelledby="konto-1">
          <Head n={1} id="konto-1" title={t("account.team.title")} />
          <p className="text-[14px] text-ink-soft">{t("account.team.intro")}</p>
          <div className="overflow-x-auto">
            <table className="table-stack w-full text-left sm:min-w-[480px]">
              <thead><tr className="text-[12px] uppercase tracking-[0.08em] text-muted"><th className="pb-2 pr-3 font-semibold">{t("leads.editor.name")}</th><th className="pb-2 pr-3 font-semibold">{t("leads.editor.email")}</th><th className="pb-2 pr-3 font-semibold">{t("account.team.role")}</th><th /></tr></thead>
              <tbody>{members.map((m) => <MemberRow key={m.id} wsId={ws.id} m={m} myRole={ws.role} isMe={m.user_id === me.id} />)}</tbody>
            </table>
          </div>
          {pending.length > 0 && <ul>{pending.map((i) => <InvitationRow key={i.id} wsId={ws.id} id={i.id} email={i.email} role={i.role} expires={i.expires_at} />)}</ul>}
          {admin ? <InviteForm wsId={ws.id} myRole={ws.role} /> : <p className="text-[14px] text-muted">{t("account.team.onlyAdmins")}</p>}
        </section>

        {admin && agr && st && acc && invoices && referral && (
          <>
            <section id="abonnement" className={`${BOX.replace("bg-paper", !confirmed && owner ? "bg-highlight" : "bg-paper")}`} aria-labelledby="konto-2">
              <Head n={2} id="konto-2" title={t("account.sub.title")} />
              {card === "saved" && <p role="status" className="rounded-xl bg-success-soft px-4 py-3 text-[14px] font-semibold text-success">{t("account.sub.cardSaved")}</p>}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="flex flex-col gap-1 rounded-xl border-[1.5px] border-ink bg-paper px-4 py-3.5">
                  <span className="eyebrow">{t("account.sub.fixed")}</span>
                  <span className="font-display font-extrabold text-[22px] text-ink">{kr(agr.plan.monthly_net_minor)} <span className="text-[14px] font-semibold">{t("account.sub.perMonth")}</span></span>
                  <span className="text-[14px] text-ink-soft">{confirmed ? t("account.sub.confirmed", { v: agr.current!.version }) : t("account.sub.notConfirmed")}</span>
                </div>
                <div className="flex flex-col gap-1 rounded-xl border-[1.5px] border-ink bg-paper px-4 py-3.5">
                  <span className="eyebrow">{t("account.sub.campaign")}</span>
                  <span className="font-display font-extrabold text-[22px] text-ink">{kr(agr.plan.campaign_call_net_minor)} <span className="text-[14px] font-semibold">{t("account.sub.campaignPrice", { minute: kr(agr.plan.campaign_minute_net_minor) })}</span></span>
                  <span className="text-[14px] text-ink-soft">{t("account.sub.campaignMonth", { calls: campaignCalls, minutes: campaignMinutes, amount: kr(campaignNet) })}</span>
                </div>
                <div className="flex flex-col gap-1 rounded-xl border-[1.5px] border-ink bg-paper px-4 py-3.5 md:col-span-2">
                  <span className="eyebrow">{t("account.sub.inbound")}</span>
                  <span className="font-display font-extrabold text-[22px] text-ink">{inbound?.minutes ?? 0} <span className="text-[14px] font-semibold">{t("account.sub.inboundUsed", { n: agr.plan.inbound_included_minutes })}</span></span>
                  <span className="text-[14px] text-ink-soft">{inbound?.extra_minutes ? t("account.sub.inboundExtra", { n: inbound.extra_minutes, amount: kr(inbound.net_minor), price: kr(agr.plan.inbound_extra_minute_net_minor) }) : t("account.sub.inboundPrice", { n: agr.plan.inbound_included_minutes, price: kr(agr.plan.inbound_extra_minute_net_minor) })}</span>
                </div>
              </div>
              {!confirmed && (owner ? <ConfirmSubscription wsId={ws.id} label={t("account.sub.confirm")} /> : <p className="text-[14px] text-ink">{t("account.sub.ownerMustConfirm")}</p>)}
              {agr.current?.model === "B" && <p className="text-[14px] text-ink">{t("account.sub.older")}</p>}
              <div className="flex flex-col gap-2 rounded-xl border-[1.5px] border-ink bg-paper px-4 py-3.5">
                <span className="eyebrow">{t("account.pay.title")}</span>
                {!acc.configured ? <p className="text-[14px] text-ink-soft">{t("account.pay.notConfigured")}</p> : (
                  <>
                    <p className="text-[15px] font-semibold text-ink">{acc.card ? <>{t("account.pay.card")} <span className="capitalize">{acc.card.brand}</span> •••• {acc.card.last4}{acc.card.exp ? ` · ${t("account.pay.expires", { exp: acc.card.exp })}` : ""}</> : t("account.pay.noCard")}</p>
                    <p className="text-[14px] text-ink-soft">{acc.card ? t("account.pay.withCard") : t("account.pay.withoutCard")}</p>
                    {acc.can_manage ? <AddCard wsId={ws.id} hasCard={!!acc.card} /> : <p className="text-[13px] text-muted">{t("account.pay.onlyOwner")}</p>}
                    {acc.can_manage && acc.card && !invoices.items.some((i) => i.month === previous) && <InvoiceMonth wsId={ws.id} month={previous} label={monthLabel(lang, previous).toLowerCase()} />}
                  </>
                )}
              </div>
              {referral.referred
                ? <p className="rounded-xl bg-success-soft px-4 py-3 text-[14px] text-success">{t("account.referral.referred", { name: referral.ambassador_first_name ?? "", pct: (referral.customer_discount_bp ?? 5000) / 100 })}</p>
                : referral.can_add_code && <ReferralCode wsId={ws.id} />}
              {discount?.code
                ? <p className="rounded-xl bg-success-soft px-4 py-3 text-[14px] text-success">{discount.to_month ? t("account.discount.applied", { code: discount.code, text: discount.text ?? "", from: monthLabel(lang, discount.from_month!), to: monthLabel(lang, discount.to_month) }) : t("account.discount.appliedForever", { code: discount.code, text: discount.text ?? "", from: monthLabel(lang, discount.from_month!) })}</p>
                : discount?.can_add && discount.can_manage && <DiscountCode wsId={ws.id} />}
              <p className="text-[13px] text-muted">{t("account.sub.note")}</p>
            </section>

            <section id="fakturaer" className={BOX} aria-labelledby="konto-3">
              <Head n={3} id="konto-3" title={t("account.invoices.title")} />
              <div className="rounded-xl border-[1.5px] border-line px-4 py-3 text-[14px] text-ink-soft">
                <b className="text-ink">{t("account.invoices.soFar", { month: monthLabel(lang, st.month) })}</b> {t("account.invoices.totals", { net: kr(st.totals.net_minor), tax: kr(st.totals.tax_minor), gross: kr(st.totals.gross_minor) })} {acc.configured ? t("account.invoices.billedEnd") : t("account.invoices.billedEndCard")}
              </div>
              {invoices.items.length === 0 ? <p className="text-[14px] text-ink-soft">{t("account.invoices.none")}</p> : (
                <div className="overflow-x-auto">
                  <table className="table-stack w-full text-left sm:min-w-[440px]">
                    <thead><tr className="text-[12px] uppercase tracking-[0.08em] text-muted"><th className="pb-2 pr-3 font-semibold">{t("account.invoices.month")}</th><th className="pb-2 pr-3 font-semibold">{t("account.invoices.status")}</th><th className="pb-2 pr-3 font-semibold">{t("account.invoices.total")}</th><th /></tr></thead>
                    <tbody>{invoices.items.map((i) => (
                      <tr key={i.id} className="border-t-[1.5px] border-line text-[14px]">
                        <td className="py-3 pr-3 font-semibold text-ink">{monthLabel(lang, i.month)}{i.number && <span className="font-normal text-muted"> · {i.number}</span>}</td>
                        <td data-label={t("account.invoices.status")} className="py-3 pr-3 text-ink-soft">{INV_STATUS.includes(i.status) ? t(`account.invoiceStatus.${i.status}`) : i.status}</td>
                        <td data-label={t("account.invoices.total")} className="py-3 pr-3 tabular-nums text-ink">{kr(i.gross_minor)}</td>
                        <td className="py-3 text-right whitespace-nowrap">
                          {i.hosted_invoice_url && <a href={i.hosted_invoice_url} target="_blank" rel="noopener noreferrer" className="font-semibold text-accent hover:underline">{t("account.invoices.open")}</a>}
                          {i.invoice_pdf && <a href={i.invoice_pdf} target="_blank" rel="noopener noreferrer" className="ml-3 font-semibold text-accent hover:underline">{t("account.invoices.pdf")}</a>}
                        </td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </div>

      <aside className="flex-[1_1_300px] min-w-0 max-w-[420px] flex flex-col gap-5">
        <div className="flex flex-col gap-3 px-5 py-5 rounded-2xl bg-paper border-2 border-ink shadow-block">
          <div className="flex items-center gap-3">
            <span className="inline-flex w-12 h-12 rounded-full bg-highlight border-2 border-ink items-center justify-center font-display font-extrabold text-[18px] text-ink" aria-hidden>{initials}</span>
            <div className="min-w-0"><p className="font-display font-extrabold text-[18px] text-ink truncate">{me.display_name}</p><p className="text-[13px] text-muted truncate">{me.email} · {ws.role === "owner" ? t("account.me.owner") : ws.role === "reader" ? t("account.me.reader") : t("account.me.editor")}</p></div>
          </div>
          {!me.email_verified && <Link href="/verify-email" className="rounded-xl bg-danger-soft px-4 py-3 text-[14px] font-semibold text-danger">{t("account.me.notVerified")}</Link>}
          <div className="flex flex-wrap gap-2">
            <Link href="/password/forgot" className="inline-flex items-center min-h-[44px] px-4 rounded-xl border-[1.5px] border-ink text-[14px] font-semibold text-ink hover:bg-panel">{t("account.me.changePassword")}</Link>
            <LogoutButton />
          </div>
          {(process.env.NEXT_PUBLIC_PRIVAT_SWITCH === "1" || process.env.NEXT_PUBLIC_PRIVAT_FAKE === "1") && (
            <div role="group" aria-label={t("account.me.switchLabel")} className="grid grid-cols-2 gap-1 p-1 rounded-full border-2 border-ink max-w-xs">
              <span aria-current="true" className="min-h-[40px] rounded-full bg-ink text-paper text-[14px] font-semibold inline-flex items-center justify-center">{t("account.me.business")}</span>
              {/* Dialogbot Privat creates the private account itself (POST /privat/account) on its first load. */}
              <Link href="/privat/dag" className="min-h-[40px] rounded-full text-[14px] font-semibold inline-flex items-center justify-center hover:bg-panel">{t("account.me.private")}</Link>
            </div>
          )}
          {me.is_platform_operator && <Link href="/app/operator/admin" className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl bg-highlight border-[1.5px] border-ink text-[14px] font-semibold text-ink">{t("account.me.operator")}</Link>}
          {me.is_platform_operator && <Link href="/app/operator/salg" className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl bg-paper border-[1.5px] border-ink text-[14px] font-semibold text-ink">{t("account.me.sales")}</Link>}
          <p className="text-[13px] text-muted">{t("account.me.sessions", { n: sessions.length })}</p>
          <ul className="flex flex-col gap-1.5">{sessions.map((s) => <li key={s.id} className="text-[13px] text-ink-soft">{device(t, s.user_agent)}{s.current ? <b className="text-ink"> · {t("account.me.thisDevice")}</b> : ` · ${t("account.me.lastActive", { at: dt(lang, s.last_seen_at) })}`}</li>)}</ul>
        </div>
        <div className="flex flex-col gap-2 px-5 py-5 rounded-2xl bg-paper border-2 border-ink">
          <span className="eyebrow">{t("account.install.title")}</span>
          <InstallApp audience="erhverv" />
          <PushSettings workspaceId={ws.id} />
        </div>
        <LanguageSection />
        <div className="flex flex-col gap-2 px-5 py-5 rounded-2xl bg-paper border-2 border-ink">
          <span className="eyebrow">{t("account.ws.title")}</span>
          <p className="text-[15px] font-semibold text-ink">{ws.name} <span className="font-normal text-muted">· {t("account.ws.this")}</span></p>
          <Link href="/opsaetning/1?ny=1" className="inline-flex items-center min-h-[44px] text-[14px] font-semibold text-accent hover:underline">+ {t("account.ws.new")}</Link>
        </div>
        <div className="flex flex-col gap-2 px-5 py-5 rounded-2xl bg-paper border-2 border-ink">
          <span className="eyebrow">{t("account.data.title")}</span>
          <p className="text-[14px] text-ink-soft">{t("account.data.sub")}</p>
          <Link href="/app/indstillinger?ark=log" className="inline-flex items-center min-h-[44px] text-[14px] font-semibold text-accent hover:underline">{t("account.data.log")} →</Link>
          <Link href="/app/indstillinger" className="inline-flex items-center min-h-[44px] text-[14px] font-semibold text-accent hover:underline">{t("account.data.settings")} →</Link>
        </div>
      </aside>
    </div>
  );
}

function Head({ n, id, title }: { n: number; id: string; title: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="inline-flex w-10 h-10 rounded-[10px] bg-ink text-paper items-center justify-center font-display font-extrabold text-[20px]" aria-hidden>{n}</span>
      <h2 id={id} className="font-display font-extrabold text-[20px] text-ink">{title}</h2>
    </div>
  );
}
