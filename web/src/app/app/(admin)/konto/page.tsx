import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { kr } from "../leads/format";
import { AddCard, ConfirmSubscription, InvoiceMonth, ReferralCode } from "./billing";
import { InvitationRow, InviteForm, MemberRow } from "./team";
import { LogoutButton } from "./logout";

type Member = { id: string; user_id: string; email: string; display_name: string; role: string };
type Inv = { id: string; email: string; role: string; status: string; expires_at: string };
type Me = { id: string; email: string; display_name: string; email_verified: boolean; is_platform_operator?: boolean };
type Session = { id: string; created_at: string; last_seen_at: string; user_agent: string | null; current: boolean };
type Agreement = { current: { version: number; model: string; created_at: string; monthly: { net_minor: number } } | null; plan: { monthly_net_minor: number; campaign_call_net_minor: number; campaign_minute_net_minor: number; inbound_included_minutes: number; inbound_extra_minute_net_minor: number } };
type Statement = { month: string; lines: { kind: string; calls?: number; minutes?: number; included_minutes?: number; extra_minutes?: number; net_minor: number }[]; totals: { net_minor: number; tax_minor: number; gross_minor: number } };
type Account = { configured: boolean; card: { brand: string; last4: string; exp: string | null } | null; can_manage: boolean };
type Invoice = { id: string; month: string; status: string; number: string | null; gross_minor: number; hosted_invoice_url: string | null; invoice_pdf: string | null };
type Referral = { referred: boolean; ambassador_first_name?: string | null; customer_discount_bp?: number; can_add_code: boolean };

const INV_STATUS: Record<string, string> = { creating: "Oprettes", open: "Afventer betaling", paid: "Betalt", payment_failed: "Betaling fejlede", failed: "Ikke betalt", void: "Annulleret" };
const monthLabel = (ym: string) => { const s = new Date(`${ym}-15T12:00:00`).toLocaleDateString("da-DK", { month: "long", year: "numeric" }); return s.charAt(0).toUpperCase() + s.slice(1); };
const shift = (ym: string, d: number) => { const [y, m] = ym.split("-").map(Number); const t = new Date(Date.UTC(y, m - 1 + d, 1)); return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}`; };
const dt = (s: string) => new Date(s).toLocaleString("da-DK", { dateStyle: "medium", timeStyle: "short" });
function device(ua: string | null) {
  if (!ua) return "Ukendt enhed";
  const os = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "";
  const br = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
  return [br, os].filter(Boolean).join(" på ");
}

const BOX = "flex flex-col gap-4 px-5 md:px-6 py-5 rounded-2xl bg-paper border-2 border-ink";

/** «Konto»: who may see and change, the subscription and the invoices – and your own login on the right. */
export default async function KontoPage({ searchParams }: { searchParams: Promise<{ card?: string }> }) {
  const ws = await requireWorkspace();
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
  const [agr, st, acc, invoices, referral] = admin ? await Promise.all([
    backend<Agreement>(`/workspaces/${ws.id}/agreement`),
    backend<Statement>(`/workspaces/${ws.id}/billing/statement`),
    backend<Account>(`/workspaces/${ws.id}/billing/account`),
    backend<{ items: Invoice[] }>(`/workspaces/${ws.id}/billing/invoices`),
    backend<Referral>(`/workspaces/${ws.id}/referral`),
  ]) : [null, null, null, null, null];
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
      <div className="flex-[999_1_460px] min-w-0 flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <span className="eyebrow">Bagerst i hæftet · Konto</span>
          <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Team, abonnement og fakturaer</h1>
        </div>

        <section className={BOX} aria-labelledby="konto-1">
          <Head n={1} id="konto-1" title="Hvem må se og ændre" />
          <p className="text-[14px] text-ink-soft">Ejeren kan alt. «Kan ændre» retter viden og regler. «Kan se» læser opkald og rapporter.</p>
          <div className="overflow-x-auto">
            <table className="w-full text-left min-w-[480px]">
              <thead><tr className="text-[12px] uppercase tracking-[0.08em] text-muted"><th className="pb-2 pr-3 font-semibold">Navn</th><th className="pb-2 pr-3 font-semibold">E-mail</th><th className="pb-2 pr-3 font-semibold">Rolle</th><th /></tr></thead>
              <tbody>{members.map((m) => <MemberRow key={m.id} wsId={ws.id} m={m} myRole={ws.role} isMe={m.user_id === me.id} />)}</tbody>
            </table>
          </div>
          {pending.length > 0 && <ul>{pending.map((i) => <InvitationRow key={i.id} wsId={ws.id} id={i.id} email={i.email} role={i.role} expires={i.expires_at} />)}</ul>}
          {admin ? <InviteForm wsId={ws.id} myRole={ws.role} /> : <p className="text-[14px] text-muted">Kun ejere og administratorer kan invitere og ændre roller.</p>}
        </section>

        {admin && agr && st && acc && invoices && referral && (
          <>
            <section id="abonnement" className={`${BOX.replace("bg-paper", !confirmed && owner ? "bg-highlight" : "bg-paper")}`} aria-labelledby="konto-2">
              <Head n={2} id="konto-2" title="Abonnement" />
              {card === "saved" && <p role="status" className="rounded-xl bg-success-soft px-4 py-3 text-[14px] font-semibold text-success">Tak – kortet er gemt hos Stripe. Det kan tage et øjeblik, før det vises her.</p>}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="flex flex-col gap-1 rounded-xl border-[1.5px] border-ink bg-paper px-4 py-3.5">
                  <span className="eyebrow">Fast abonnement</span>
                  <span className="font-display font-extrabold text-[22px] text-ink">{kr(agr.plan.monthly_net_minor)} <span className="text-[14px] font-semibold">/md. ekskl. moms</span></span>
                  <span className="text-[14px] text-ink-soft">{confirmed ? `Bekræftet · aftale v${agr.current!.version}. Gør-det-selv-opsætning er med.` : "Gør-det-selv-opsætning er med. Ikke bekræftet endnu."}</span>
                </div>
                <div className="flex flex-col gap-1 rounded-xl border-[1.5px] border-ink bg-paper px-4 py-3.5">
                  <span className="eyebrow">Kampagneopkald</span>
                  <span className="font-display font-extrabold text-[22px] text-ink">{kr(agr.plan.campaign_call_net_minor)} <span className="text-[14px] font-semibold">pr. opkald + {kr(agr.plan.campaign_minute_net_minor)} pr. minut ekskl. moms</span></span>
                  <span className="text-[14px] text-ink-soft">Denne måned: {campaignCalls} opkald, {campaignMinutes} samtaleminutter · {kr(campaignNet)} ekskl. moms</span>
                </div>
                <div className="flex flex-col gap-1 rounded-xl border-[1.5px] border-ink bg-paper px-4 py-3.5 md:col-span-2">
                  <span className="eyebrow">Indgående opkald</span>
                  <span className="font-display font-extrabold text-[22px] text-ink">{inbound?.minutes ?? 0} <span className="text-[14px] font-semibold">af {agr.plan.inbound_included_minutes} inkluderede minutter brugt denne måned</span></span>
                  <span className="text-[14px] text-ink-soft">{inbound?.extra_minutes ? `${inbound.extra_minutes} minutter ud over de inkluderede · ${kr(inbound.net_minor)} ekskl. moms (${kr(agr.plan.inbound_extra_minute_net_minor)} pr. påbegyndt minut).` : `Minutter ud over de ${agr.plan.inbound_included_minutes} koster ${kr(agr.plan.inbound_extra_minute_net_minor)} pr. påbegyndt minut ekskl. moms.`}</span>
                </div>
              </div>
              {!confirmed && (owner ? <ConfirmSubscription wsId={ws.id} label="Bekræft abonnement" /> : <p className="text-[14px] text-ink">Ejeren skal bekræfte abonnementet.</p>)}
              {agr.current?.model === "B" && <p className="text-[14px] text-ink">Ældre aftale – bekræft abonnementet for at skifte til det nuværende abonnement.</p>}
              <div className="flex flex-col gap-2 rounded-xl border-[1.5px] border-ink bg-paper px-4 py-3.5">
                <span className="eyebrow">Betaling</span>
                {!acc.configured ? <p className="text-[14px] text-ink-soft">Kortbetaling er ikke sat op endnu. Indtil da er oversigten kun en forhåndsvisning, og der trækkes ingen betaling.</p> : (
                  <>
                    <p className="text-[15px] font-semibold text-ink">{acc.card ? <>Kort <span className="capitalize">{acc.card.brand}</span> •••• {acc.card.last4}{acc.card.exp ? ` · udløber ${acc.card.exp}` : ""}</> : "Intet betalingskort"}</p>
                    <p className="text-[14px] text-ink-soft">{acc.card ? "Hver måned faktureres bagud og trækkes automatisk på kortet." : "Uden kort bliver måneden ikke faktureret."}</p>
                    {acc.can_manage ? <AddCard wsId={ws.id} hasCard={!!acc.card} /> : <p className="text-[13px] text-muted">Kun ejeren kan ændre betalingskortet.</p>}
                    {acc.can_manage && acc.card && !invoices.items.some((i) => i.month === previous) && <InvoiceMonth wsId={ws.id} month={previous} label={monthLabel(previous).toLowerCase()} />}
                  </>
                )}
              </div>
              {referral.referred
                ? <p className="rounded-xl bg-success-soft px-4 py-3 text-[14px] text-success">I er anbefalet af {referral.ambassador_first_name} (Dialogbot-ambassadør) og får {(referral.customer_discount_bp ?? 5000) / 100} % rabat på første fakturerede måned.</p>
                : referral.can_add_code && <ReferralCode wsId={ws.id} />}
              <p className="text-[13px] text-muted">Priser er ekskl. moms. Ingen binding – sig det til assistenten eller skriv til info@dialogbot.dk, hvis I vil opsige. Betaling starter aldrig opkald.</p>
            </section>

            <section id="fakturaer" className={BOX} aria-labelledby="konto-3">
              <Head n={3} id="konto-3" title="Fakturaer" />
              <div className="rounded-xl border-[1.5px] border-line px-4 py-3 text-[14px] text-ink-soft">
                <b className="text-ink">{monthLabel(st.month)} indtil videre:</b> {kr(st.totals.net_minor)} ekskl. moms · moms {kr(st.totals.tax_minor)} · i alt {kr(st.totals.gross_minor)} Faktureres, når måneden er slut{acc.configured ? "" : " og kortbetaling er sat op"}.
              </div>
              {invoices.items.length === 0 ? <p className="text-[14px] text-ink-soft">Ingen fakturaer endnu.</p> : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left min-w-[440px]">
                    <thead><tr className="text-[12px] uppercase tracking-[0.08em] text-muted"><th className="pb-2 pr-3 font-semibold">Måned</th><th className="pb-2 pr-3 font-semibold">Status</th><th className="pb-2 pr-3 font-semibold">I alt inkl. moms</th><th /></tr></thead>
                    <tbody>{invoices.items.map((i) => (
                      <tr key={i.id} className="border-t-[1.5px] border-line text-[14px]">
                        <td className="py-3 pr-3 font-semibold text-ink">{monthLabel(i.month)}{i.number && <span className="font-normal text-muted"> · {i.number}</span>}</td>
                        <td className="py-3 pr-3 text-ink-soft">{INV_STATUS[i.status] ?? i.status}</td>
                        <td className="py-3 pr-3 tabular-nums text-ink">{kr(i.gross_minor)}</td>
                        <td className="py-3 text-right whitespace-nowrap">
                          {i.hosted_invoice_url && <a href={i.hosted_invoice_url} target="_blank" rel="noopener noreferrer" className="font-semibold text-accent hover:underline">Åben</a>}
                          {i.invoice_pdf && <a href={i.invoice_pdf} target="_blank" rel="noopener noreferrer" className="ml-3 font-semibold text-accent hover:underline">Hent PDF</a>}
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
            <div className="min-w-0"><p className="font-display font-extrabold text-[18px] text-ink truncate">{me.display_name}</p><p className="text-[13px] text-muted truncate">{me.email} · {ws.role === "owner" ? "ejer" : ws.role === "reader" ? "kan se" : "kan ændre"}</p></div>
          </div>
          {!me.email_verified && <Link href="/verify-email" className="rounded-xl bg-danger-soft px-4 py-3 text-[14px] font-semibold text-danger">E-mailen er ikke bekræftet – bekræft nu</Link>}
          <div className="flex flex-wrap gap-2">
            <Link href="/password/forgot" className="inline-flex items-center min-h-[44px] px-4 rounded-xl border-[1.5px] border-ink text-[14px] font-semibold text-ink hover:bg-panel">Skift adgangskode</Link>
            <LogoutButton />
          </div>
          {me.is_platform_operator && <Link href="/app/operator/admin" className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl bg-highlight border-[1.5px] border-ink text-[14px] font-semibold text-ink">Operatør</Link>}
          <p className="text-[13px] text-muted">Logget ind på {sessions.length} {sessions.length === 1 ? "enhed" : "enheder"}. Nulstiller du adgangskoden, logges alle ud.</p>
          <ul className="flex flex-col gap-1.5">{sessions.map((s) => <li key={s.id} className="text-[13px] text-ink-soft">{device(s.user_agent)}{s.current ? <b className="text-ink"> · denne enhed</b> : ` · sidst aktiv ${dt(s.last_seen_at)}`}</li>)}</ul>
        </div>
        <div className="flex flex-col gap-2 px-5 py-5 rounded-2xl bg-paper border-2 border-ink">
          <span className="eyebrow">Arbejdsrum</span>
          <p className="text-[15px] font-semibold text-ink">{ws.name} <span className="font-normal text-muted">· dette</span></p>
          <Link href="/opsaetning/1?ny=1" className="inline-flex items-center min-h-[44px] text-[14px] font-semibold text-accent hover:underline">+ Byg en Dialogbot til en anden virksomhed</Link>
        </div>
        <div className="flex flex-col gap-2 px-5 py-5 rounded-2xl bg-paper border-2 border-ink">
          <span className="eyebrow">Data og historik</span>
          <p className="text-[14px] text-ink-soft">Hvem der har ændret hvad, og hvornår, ligger i historikken.</p>
          <Link href="/app/indstillinger?ark=log" className="inline-flex items-center min-h-[44px] text-[14px] font-semibold text-accent hover:underline">Se alle ændringer →</Link>
          <Link href="/app/indstillinger" className="inline-flex items-center min-h-[44px] text-[14px] font-semibold text-accent hover:underline">Alle indstillinger →</Link>
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
