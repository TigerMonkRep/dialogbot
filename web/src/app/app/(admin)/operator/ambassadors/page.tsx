import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { AmbassadorAdmin, type OpList, type OpPayout } from "./client";

/** Operator: approve ambassadors, see balances, run payouts, mark them paid and export B-income for eIndkomst. */
export default async function OperatorAmbassadorsPage() {
  await requireWorkspace();
  let list: OpList;
  let payouts: { items: OpPayout[] };
  try {
    [list, payouts] = await Promise.all([backend<OpList>("/operator/ambassadors"), backend<{ items: OpPayout[] }>("/operator/ambassadors/payouts")]);
  } catch {
    return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Ambassadøradministrationen er kun for Dialogbot-operatører.</p>;
  }
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Operatør</span>
        <h1 className="font-headline-md text-headline-md text-primary font-bold">Ambassadører</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">Godkend nye ambassadører, hold øje med saldi og kør udbetalinger. Bonus optjenes kun af betalte fakturaer og frigives efter 30 dage. Alle handlinger logges.</p>
      </div>
      <AmbassadorAdmin list={list} payouts={payouts.items} />
    </section>
  );
}
