import Link from "next/link";
import { API_BASE_URL } from "@/lib/config";
import { isLoggedIn } from "@/lib/api.server";
import { Icon } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { AcceptOffer } from "./accept";

type Offer = {
  company: string; package: string; setup_kind: string; setup_text: string; status: string; valid_until: string; terms_version: string; notice: string;
  monthly_net_minor: number; monthly_vat_minor: number; setup_net_minor: number; setup_vat_minor: number;
  campaign_call_net_minor: number; campaign_minute_net_minor: number; inbound_included_minutes: number; inbound_extra_minute_net_minor: number;
};
const kr = (minor: number) => `${(minor / 100).toLocaleString("da-DK", { minimumFractionDigits: minor % 100 ? 2 : 0, maximumFractionDigits: 2 })} kr.`;
const STATUS: Record<string, string> = { accepted: "Tilbuddet er allerede accepteret.", expired: "Tilbuddet er udløbet. Bed om et nyt.", cancelled: "Tilbuddet er trukket tilbage.", draft: "Tilbuddet er ikke sendt endnu." };

/** The customer's offer from Dialogbot's sales: prices excl. and incl. VAT, terms, and acceptance (login required). */
export default async function OfferPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const r = await fetch(`${API_BASE_URL}/api/v1/public/offers/${encodeURIComponent(token)}`, { cache: "no-store" });
  const o: Offer | null = r.ok ? await r.json() : null;
  const loggedIn = await isLoggedIn();
  const next = `/tilbud/${token}`;
  return (
    <AuthFrame icon="request_quote" title={o ? `Tilbud til ${o.company}` : "Tilbud"} subtitle={o ? `${o.package} fra Dialogbot` : undefined}>
      {!o ? <p role="alert" className="text-body-md text-danger">Linket er ugyldigt eller erstattet af et nyere. Bed om et nyt link.</p> : (
        <div className="space-y-3">
          <dl className="rounded-lg bg-panel p-3 grid grid-cols-[1fr,auto] gap-x-3 gap-y-2 text-body-md">
            <dt className="text-ink-soft">Abonnement pr. måned</dt><dd className="font-semibold text-ink tabular-nums text-right">{kr(o.monthly_net_minor)} ekskl. moms</dd>
            <dt className="text-ink-soft">Moms (25 %)</dt><dd className="tabular-nums text-right">{kr(o.monthly_vat_minor)}</dd>
            <dt className="text-ink-soft">I alt pr. måned</dt><dd className="font-semibold tabular-nums text-right">{kr(o.monthly_net_minor + o.monthly_vat_minor)} inkl. moms</dd>
            <dt className="text-ink-soft">Opsætning</dt><dd className="text-right">{o.setup_net_minor ? `${kr(o.setup_net_minor)} én gang ekskl. moms (${kr(o.setup_net_minor + o.setup_vat_minor)} inkl.)` : "Gør-det-selv – med i abonnementet"}</dd>
            <dt className="text-ink-soft">Indgående opkald</dt><dd className="text-right">{o.inbound_included_minutes} min/md. med, derefter {kr(o.inbound_extra_minute_net_minor)}/min ekskl. moms</dd>
            <dt className="text-ink-soft">Udgående kampagneopkald</dt><dd className="text-right">{kr(o.campaign_call_net_minor)} pr. opkald + {kr(o.campaign_minute_net_minor)} pr. påbegyndt minut ekskl. moms</dd>
            <dt className="text-ink-soft">Binding</dt><dd className="text-right">{o.notice}</dd>
            <dt className="text-ink-soft">Gælder til</dt><dd className="text-right">{new Date(o.valid_until).toLocaleDateString("da-DK", { timeZone: "Europe/Copenhagen" })}</dd>
          </dl>
          <p className="text-body-sm text-ink-soft">Vilkår: prisliste {o.terms_version}. Intet er bestilt, før du selv accepterer her. Efter accept lægger du et betalingskort; første faktura kommer ved månedsskiftet{o.setup_net_minor ? " med opsætningen" : ""}.</p>
          {o.status !== "sent" ? <p role="alert" className="text-body-md text-danger">{STATUS[o.status] ?? o.status}</p>
            : loggedIn ? <AcceptOffer token={token} company={o.company} />
            : (
              <div className="space-y-2">
                <p className="text-body-sm text-ink-soft">Log ind eller opret en konto for at acceptere. Kontoen bliver jeres adgang til Dialogbot.</p>
                <Link className="w-full h-12 rounded-lg bg-ink text-paper text-label-lg flex items-center justify-center gap-1 hover:bg-ink" href={`/login?next=${encodeURIComponent(next)}`}><Icon name="login" size={18} />Log ind og acceptér</Link>
                <Link className="w-full h-12 rounded-lg bg-panel-deep text-ink text-label-lg flex items-center justify-center gap-1 hover:bg-line" href={`/signup?next=${encodeURIComponent(next)}`}><Icon name="person_add" size={18} />Accepter og opret konto</Link>
              </div>
            )}
        </div>
      )}
    </AuthFrame>
  );
}
