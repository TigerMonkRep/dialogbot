"use client";
import { useRouter } from "next/navigation";
import { Button, ErrorBox, Icon, useSubmit } from "@/components/ui";
import { api } from "@/lib/client";
import { kr } from "../../leads/format";
import type { AgreementOut } from "./page";

export function AgreementForm({ wsId, current, plan, canEdit }: { wsId: string; current: AgreementOut["current"]; plan: AgreementOut["plan"]; canEdit: boolean }) {
  const router = useRouter();
  const confirm = useSubmit(async () => {
    await api(`/workspaces/${wsId}/agreement`, { method: "POST", body: JSON.stringify({ model: "A" }) });
    router.refresh();
  });
  const legacy = current?.model === "B";
  return (
    <section className="bg-surface-container-lowest rounded-2xl p-space-md md:p-space-lg border-2 border-ink flex flex-col gap-space-md">
      <div>
        <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Abonnement</h2>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Der er ét abonnement. Hver bekræftelse gemmes som en ny version af aftalen, og prisen i en aftale ændrer sig ikke bagudrettet.</p>
      </div>
      <p className="p-space-sm rounded-lg bg-tertiary-fixed text-on-tertiary-fixed font-body-sm text-body-sm flex items-start gap-space-xs"><Icon name="info" size={18} />Der faktureres bagud hver måned på det betalingskort, ejeren har gemt under Fakturering. Uden kort faktureres der ikke.</p>
      {current ? <p className="font-body-md text-body-md">Gældende: <strong>version {current.version}</strong> ({new Date(current.created_at).toLocaleDateString("da-DK")}). {legacy ? `Ældre aftale med ${kr(current.lead_fee.net_minor)} ekskl. moms pr. godkendt henvendelse – bekræft abonnementet for at skifte.` : `Månedspris: ${kr(current.monthly.net_minor)} ekskl. moms (${kr(current.monthly.gross_minor)} inkl. moms).`}</p>
        : <p className="font-body-md text-body-md">Abonnementet er ikke bekræftet endnu. Henvendelser kan ikke godkendes, før det er bekræftet.</p>}
      <div className="rounded-xl p-space-md flex flex-col gap-space-xs bg-surface-container-low max-w-md">
        <span className="font-label-lg text-label-lg font-bold">Abonnement</span>
        <span className="font-headline-sm text-headline-sm">Fra {kr(plan.monthly_net_minor)}/md. ekskl. moms</span>
        <span className="font-body-sm text-body-sm text-on-surface-variant">Ingen pris pr. henvendelse. Udgående kampagneopkald: {kr(plan.campaign_call_net_minor)} pr. opkald ekskl. moms.</span>
        {canEdit && (!current || legacy) && <div className="pt-space-xs"><Button type="button" variant="tonal" disabled={confirm.pending} onClick={() => confirm.run()}>Bekræft abonnement</Button></div>}
        {current && !legacy && <span className="font-label-md text-label-md flex items-center gap-1"><Icon name="check_circle" size={18} />Bekræftet</span>}
      </div>
      {!canEdit && <p className="font-body-sm text-body-sm text-on-surface-variant">Kun ejeren kan bekræfte abonnementet.</p>}
      <ErrorBox error={confirm.error} />
    </section>
  );
}
