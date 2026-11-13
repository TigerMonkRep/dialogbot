import { AdminFrame, NotOperator, load } from "../admin/shared";
import { Outreach, type BatchReport, type Overview } from "./client";

/** Operator: cold B2B e-mail for Dialogbot's own sales. One page, three things: what must be fixed before going live,
 *  the tools to start a campaign (market, city, category → businesses → e-mails), and the campaigns with every
 *  decision, e-mail and audit. Nothing is sent from here unless OUTREACH_MODE=live and the operator presses send. */
export default async function OutreachPage({ searchParams }: { searchParams: Promise<{ batch?: string }> }) {
  const data = await load<Overview>("/operator/outreach/overview");
  if (!data) return <NotOperator />;
  const sp = await searchParams;
  const name = sp.batch && /^[A-Za-z0-9_.-]{1,60}$/.test(sp.batch) ? sp.batch : "";
  const report = name && data.mode !== "off" ? await load<BatchReport>(`/operator/outreach/batches/${name}`) : null;
  return (
    <AdminFrame active="/app/operator/outreach" title="Kold e-mail" eyebrow="Admin · Dialogbots eget salg"
      intro="Find virksomheder i et land, en by og en branche, få skrevet én kort e-mail til hver, og se præcis hvad der bliver sendt. Landereglerne bliver tjekket, før noget andet sker – og intet sendes, før du selv trykker.">
      <Outreach data={data} report={report} />
    </AdminFrame>
  );
}
