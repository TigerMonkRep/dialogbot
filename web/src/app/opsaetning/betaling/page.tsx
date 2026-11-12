import { backend } from "@/lib/api.server";
import { setupStatus } from "@/lib/setup.server";
import { stepNumber } from "@/lib/setup-steps";
import { EU_COUNTRIES } from "@/lib/markets";
import { requireWorkspace } from "@/lib/workspace.server";
import { Part, StepHead } from "@/components/setup-parts";
import { SetupShell } from "@/components/setup-shell";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";
import type { Telephony } from "@/app/app/(admin)/settings/telephony/client";
import { CardAndVat, ConfirmSubscription } from "@/app/app/(admin)/konto/billing";
import { kr as krDa } from "@/app/app/(admin)/leads/format";
import { SetupChecklist } from "@/components/setup-checklist";
import { GoLive, type Webchat } from "../_parts/channels";

type Agreement = { current: { version: number; model: string; currency?: string; monthly: { net_minor: number }; included_minutes?: number; inbound_extra_minute?: { net_minor: number }; outbound_extra_minute?: { net_minor: number } } | null;
  plan: { currency?: string; monthly_net_minor: number; included_minutes: number; inbound_extra_minute_net_minor: number; outbound_extra_minute_net_minor: number }; currency?: string };
type Account = { configured: boolean; test_mode?: boolean; card: { brand: string; last4: string; exp: string | null } | null; can_manage: boolean; country?: string | null; currency?: string; vat_number?: string | null; vat?: { kind: string } | null };

/** Betaling – always the last step, visible in the stepper: the subscription (one plan) and the card, and then the
 *  chosen channels go live. Neither the phone nor the website chat goes live before it is paid (Fürster 12/11). */
export default async function BetalingStep({ searchParams }: { searchParams: Promise<{ card?: string }> }) {
  const ws = await requireWorkspace();
  const { card } = await searchParams;
  const staff = ws.role !== "reader";
  const admin = ws.role === "owner" || ws.role === "admin";
  const [st, profile, tel, webchat, agr, acc] = await Promise.all([
    setupStatus(ws.id, ws.role),
    backend<{ legal_name: string; phone: string | null; cvr: string | null; address_line: string | null; postal_code: string | null; city: string | null }>(`/workspaces/${ws.id}/profile`),
    staff ? backend<Telephony>(`/workspaces/${ws.id}/telephony`).catch(() => null) : Promise.resolve(null),
    staff ? backend<Webchat>(`/workspaces/${ws.id}/webchat`).catch(() => null) : Promise.resolve(null),
    admin ? backend<Agreement>(`/workspaces/${ws.id}/agreement`).catch(() => null) : Promise.resolve(null),
    admin ? backend<Account>(`/workspaces/${ws.id}/billing/account`).catch(() => null) : Promise.resolve(null),
  ]);
  const t = await getT("setup.betalingPage");
  const ta = await getT("app");
  const tc = await getT("setup.checklist");
  const raw = await getRaw();
  const lang = HTML_LANG[await getLocale()];
  const n = stepNumber("betaling", st.goals);
  const confirmed = Boolean(agr?.current && agr.current.model !== "B");
  const cur = confirmed ? agr!.current! : null;
  const kr = (minor: number) => krDa(minor, lang, cur?.currency ?? agr?.plan.currency ?? agr?.currency ?? acc?.currency);
  const terms = agr ? {
    monthly: cur?.monthly.net_minor ?? agr.plan.monthly_net_minor,
    included: cur?.included_minutes ?? agr.plan.included_minutes,
    inbound: cur?.inbound_extra_minute?.net_minor ?? agr.plan.inbound_extra_minute_net_minor,
    outbound: cur?.outbound_extra_minute?.net_minor ?? agr.plan.outbound_extra_minute_net_minor,
  } : null;
  const country = (acc?.country ?? "").toUpperCase();
  const vatMode = acc?.vat?.kind === "vat_number_required" || (country && country !== "DK" && EU_COUNTRIES.includes(country)) ? "required"
    : country === "NO" ? "optional" : null;
  const address = [profile.address_line, [profile.postal_code, profile.city].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  return (
    <SetupShell step="betaling" steps={st.steps} workspaceName={ws.name} wide assistant={{ wsId: ws.id, canChange: staff }}>
      <StepHead n={n} eyebrow={t("eyebrow", { n, total: st.steps.length })} title={t("title")} intro={t("intro")} need={raw<[string, string, string?][]>("setup.betalingPage.need")} needTitle={raw<string>("setup.need.title")} />
      <div className="flex flex-col gap-6">
        <SetupChecklist st={st} where="guide" />
        {card === "saved" && <p role="status" className="rounded-xl bg-success-soft px-4 py-3 text-[14px] font-semibold text-success">{ta("account.sub.cardSaved")}</p>}
        {admin && agr && acc && terms ? (<>
          <Part letter="A" title={t("plan.title")} hint={t("plan.hint")}>
            {/* One plan: the subscription. Chosen = confirmed; the price is the list price (or the agreement's own snapshot). */}
            <div>
              <div className={`flex flex-col gap-1 rounded-xl border-2 border-ink px-4 py-3.5 ${confirmed ? "bg-highlight" : "bg-paper"}`}>
                <span className="eyebrow">{ta("account.sub.fixed")}</span>
                <span className="font-display font-extrabold text-[24px] text-ink">{kr(terms.monthly)} <span className="text-[14px] font-semibold">{ta("account.sub.perMonth")}</span></span>
                <span className="text-[14px] text-ink-soft">{ta("account.sub.packagePrice", { n: terms.included, inPrice: kr(terms.inbound), outPrice: kr(terms.outbound) })}</span>
                <span className="text-[14px] font-semibold text-ink">{confirmed ? ta("account.sub.confirmed", { v: agr.current!.version }) : ta("account.sub.notConfirmed")}</span>
              </div>
            </div>
            {!confirmed && (ws.role === "owner" ? <ConfirmSubscription wsId={ws.id} label={ta("account.sub.confirm")} /> : <p className="text-[14px] text-ink">{ta("account.sub.ownerMustConfirm")}</p>)}
            {agr.current?.model === "B" && <p className="text-[14px] text-ink">{ta("account.sub.older")}</p>}
          </Part>
          <Part letter="B" title={t("card.title")} hint={acc.configured ? t("card.hint") : undefined}>
            {acc.test_mode && <p role="note" className="self-start rounded-full border-[1.5px] border-ink bg-highlight px-3 py-1 text-[13px] font-semibold text-ink">{ta("account.pay.testMode")}</p>}
            {!acc.configured ? <p className="text-[14px] text-ink-soft">{ta("account.pay.notConfigured")}</p> : (<>
              <p className="text-[15px] font-semibold text-ink">{acc.card ? <>{ta("account.pay.card")} <span className="capitalize">{acc.card.brand}</span> •••• {acc.card.last4}{acc.card.exp ? ` · ${ta("account.pay.expires", { exp: acc.card.exp })}` : ""}</> : ta("account.pay.noCard")}</p>
              <CardAndVat wsId={ws.id} hasCard={!!acc.card} canManage={acc.can_manage} vatNumber={acc.vat_number ?? null} vatMode={vatMode} returnTo="opsaetning" />
              {!acc.can_manage && <p className="text-[13px] text-muted">{ta("account.pay.onlyOwner")}</p>}
            </>)}
          </Part>
        </>) : (
          <p role="status" className="rounded-xl border-2 border-ink bg-paper px-4 py-3 text-[15px] text-ink">{st.paid ? t("paidByOwner") : t("ownerPays")}</p>
        )}
        <p role="status" data-testid="betaling-status" className={`rounded-xl px-4 py-3 text-[15px] font-semibold ${st.paid ? "bg-success-soft text-success" : "border-2 border-ink bg-paper text-ink"}`}>
          {st.billing?.graceEnds ? tc("grace", { date: new Date(new Date(st.billing.graceEnds).getTime() - 1000).toLocaleDateString(lang, { day: "numeric", month: "long" }) }) : st.paid ? t("paid") : !admin ? t("notPaidYet") : !confirmed ? (acc?.configured ? t("nextConfirm") : t("nextConfirmNoCard")) : t("nextCard")}
        </p>
        <GoLive wsId={ws.id} canManage={admin} reader={!staff} paid={st.paid} goals={st.goals} t={tel} webchat={webchat}
          company={profile.legal_name} cvr={profile.cvr ?? ""} address={address} phone={profile.phone ?? ""} />
      </div>
    </SetupShell>
  );
}
