import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { OperatorTelephony, type OpTelephony } from "./client";

/** Operator view: provider configuration (as booleans), provisioning jobs and errors, documentation review,
 *  manual verification, number mapping and caller-ID permission. Customers never see this. */
export default async function OperatorTelephonyPage() {
  await requireWorkspace();
  let data: OpTelephony;
  try {
    data = await backend<OpTelephony>("/operator/telephony");
  } catch {
    return <p className="bg-surface-container-lowest rounded-2xl p-space-lg border-2 border-ink font-body-md text-body-md text-on-surface-variant">Operatørvisningen er kun for Dialogbot-operatører.</p>;
  }
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="eyebrow">Operatør</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Telefoni: leverandører, klargøring og numre</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">Dialogbot ejer leverandørkonti og underkonti. Hemmeligheder står kun i serverens hemmelighedsstyring og vises aldrig her. Alle handlinger bliver auditeret.</p>
      </div>
      <OperatorTelephony data={data} />
    </section>
  );
}
