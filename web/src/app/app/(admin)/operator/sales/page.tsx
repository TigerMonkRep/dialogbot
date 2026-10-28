import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { SellerDemoCall, type DemoRow, type SalesInfo } from "./client";

/** Operator (seller) view: a Dialogbot seller has a prospect on the phone, checks the company in CVR, gets a yes and
 *  lets the AI ring them now. Every call is audited with the seller; consent is stored on the call. */
export default async function OperatorSalesPage() {
  await requireWorkspace();
  let info: SalesInfo;
  let calls: { items: DemoRow[] };
  try {
    [info, calls] = await Promise.all([backend<SalesInfo>("/operator/sales"), backend<{ items: DemoRow[] }>("/operator/sales/demo-calls")]);
  } catch {
    return <p className="bg-surface-container-lowest rounded-2xl p-space-lg border-2 border-ink font-body-md text-body-md text-on-surface-variant">Salgsvisningen er kun for Dialogbot-operatører.</p>;
  }
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="eyebrow">Operatør</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Salgsopkald: lad AI&apos;en ringe op</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">Du ringer selv til virksomheden. Tjek CVR først – er den reklamebeskyttet, må du ikke ringe. Spørg: &quot;Må vores AI-receptionist ringe dig op lige nu i to minutter, så du kan høre den?&quot; Først når de siger ja, trykker du på knappen. Opkaldet og dit ja bliver gemt.</p>
      </div>
      <SellerDemoCall info={info} calls={calls.items} />
    </section>
  );
}
