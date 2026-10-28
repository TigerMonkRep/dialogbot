import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { OperatorVoices, type OpData, type Rights } from "./client";

/** Operator view: data sources, rights, versions, test clips, checks, approval and suspension. */
export default async function OperatorVoicesPage() {
  await requireWorkspace();
  let data: OpData | null = null;
  let rights: { items: Rights[] } = { items: [] };
  try {
    [data, rights] = await Promise.all([backend<OpData>("/operator/voices"), backend<{ items: Rights[] }>("/operator/voice-rights")]);
  } catch {
    return <p className="bg-surface-container-lowest rounded-2xl p-space-lg border-2 border-ink font-body-md text-body-md text-on-surface-variant">Operatørvisningen er kun for Dialogbot-operatører.</p>;
  }
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="eyebrow">Operatør</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Stemmer: kilder, rettigheder og udgivelse</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">En stemme kan først udgives, når rettighederne er gennemgået af en person, de automatiske kontroller er bestået med den rigtige talemotor, og lyttetest og telefontest er registreret med dokumentation. Intet her kan markeres som bestået uden bevis.</p>
      </div>
      <OperatorVoices data={data} rights={rights.items} />
    </section>
  );
}
