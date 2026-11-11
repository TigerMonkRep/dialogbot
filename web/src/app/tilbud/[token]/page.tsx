import Link from "@/i18n/link";
import { HTML_LANG } from "@/i18n/config";
import { getLocale, getT } from "@/i18n/server";
import { API_BASE_URL } from "@/lib/config";
import { isLoggedIn } from "@/lib/api.server";
import { Icon } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { AcceptOffer } from "./accept";
import { currencyOr, formatPrice } from "@/lib/markets";

type Offer = {
  company: string; package: string; setup_kind: string; setup_text: string; status: string; valid_until: string; terms_version: string; notice: string;
  monthly_net_minor: number; monthly_vat_minor: number; setup_net_minor: number; setup_vat_minor: number;
  campaign_call_net_minor: number; campaign_minute_net_minor: number;
  /** The voicemail and unanswered call prices after the package (the agreement snapshots the same values on accept). */
  campaign_call_voicemail_net_minor: number; campaign_call_no_answer_net_minor: number; inbound_included_minutes: number; inbound_extra_minute_net_minor: number;
  /** The offer's currency (DKK when the backend does not say). */
  currency?: string;
};
const STATUSES = new Set(["accepted", "expired", "cancelled", "draft"]);

/** The customer's offer from Dialogbot's sales: prices excl. and incl. VAT, terms, and acceptance (login required). */
export default async function OfferPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const t = await getT("auth");
  const lang = HTML_LANG[await getLocale()];
  const r = await fetch(`${API_BASE_URL}/api/v1/public/offers/${encodeURIComponent(token)}`, { cache: "no-store" });
  const o: Offer | null = r.ok ? await r.json() : null;
  const kr = (minor: number) => formatPrice(minor, currencyOr(o?.currency), lang);
  const loggedIn = await isLoggedIn();
  const next = `/tilbud/${token}`;
  return (
    <AuthFrame icon="request_quote" title={o ? t("offer.title", { company: o.company }) : t("offer.titleFallback")} subtitle={o ? t("offer.subtitle", { package: o.package }) : undefined}>
      {!o ? <p role="alert" className="text-body-md text-danger">{t("offer.invalid")}</p> : (
        <div className="space-y-3">
          <dl className="rounded-lg bg-panel p-3 grid grid-cols-[1fr,auto] gap-x-3 gap-y-2 text-body-md">
            <dt className="text-ink-soft">{t("offer.monthly")}</dt><dd className="font-semibold text-ink tabular-nums text-right">{t("offer.exVat", { amount: kr(o.monthly_net_minor) })}</dd>
            <dt className="text-ink-soft">{t("offer.vat")}</dt><dd className="tabular-nums text-right">{kr(o.monthly_vat_minor)}</dd>
            <dt className="text-ink-soft">{t("offer.totalMonthly")}</dt><dd className="font-semibold tabular-nums text-right">{t("offer.inclVat", { amount: kr(o.monthly_net_minor + o.monthly_vat_minor) })}</dd>
            <dt className="text-ink-soft">{t("offer.setup")}</dt><dd className="text-right">{o.setup_net_minor ? t("offer.setupPaid", { amount: kr(o.setup_net_minor), total: kr(o.setup_net_minor + o.setup_vat_minor) }) : t("offer.setupDiy")}</dd>
            <dt className="text-ink-soft">{t("offer.inbound")}</dt><dd className="text-right">{t("offer.inboundValue", { minutes: o.inbound_included_minutes, price: kr(o.inbound_extra_minute_net_minor) })}</dd>
            <dt className="text-ink-soft">{t("offer.outbound")}</dt><dd className="text-right">{t("offer.outboundValue", { call: kr(o.campaign_call_net_minor), voicemail: kr(o.campaign_call_voicemail_net_minor), noAnswer: kr(o.campaign_call_no_answer_net_minor), minute: kr(o.campaign_minute_net_minor) })}</dd>
            <dt className="text-ink-soft">{t("offer.binding")}</dt><dd className="text-right">{o.notice}</dd>
            <dt className="text-ink-soft">{t("offer.validUntil")}</dt><dd className="text-right">{new Date(o.valid_until).toLocaleDateString(lang, { timeZone: "Europe/Copenhagen" })}</dd>
          </dl>
          <p className="text-body-sm text-ink-soft">{t(o.setup_net_minor ? "offer.termsWithSetup" : "offer.terms", { version: o.terms_version })}</p>
          {o.status !== "sent" ? <p role="alert" className="text-body-md text-danger">{STATUSES.has(o.status) ? t(`offer.statuses.${o.status}`) : o.status}</p>
            : loggedIn ? <AcceptOffer token={token} company={o.company} />
            : (
              <div className="space-y-2">
                <p className="text-body-sm text-ink-soft">{t("offer.loginPrompt")}</p>
                <Link className="w-full h-12 rounded-lg bg-ink text-paper text-label-lg flex items-center justify-center gap-1 hover:bg-ink" href={`/login?next=${encodeURIComponent(next)}`}><Icon name="login" size={18} />{t("offer.loginAccept")}</Link>
                <Link className="w-full h-12 rounded-lg bg-panel-deep text-ink text-label-lg flex items-center justify-center gap-1 hover:bg-line" href={`/signup?next=${encodeURIComponent(next)}`}><Icon name="person_add" size={18} />{t("offer.signupAccept")}</Link>
              </div>
            )}
        </div>
      )}
    </AuthFrame>
  );
}
