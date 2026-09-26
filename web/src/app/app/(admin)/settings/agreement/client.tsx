"use client";
import { useRouter } from "next/navigation";
import { Button, ErrorBox, Icon, useSubmit } from "@/components/ui";
import { api } from "@/lib/client";
import { kr } from "../../leads/format";
import type { AgreementOut } from "./page";

const MODELS: [string, string, string, string][] = [
  ["A", "Model A · Abonnement", "1.495 kr./md. ekskl. moms", "Fast månedspris. Ingen betaling pr. henvendelse."],
  ["B", "Model B · Pr. godkendt lead", "149 kr. pr. godkendt henvendelse ekskl. moms", "Ingen månedspris. I betaler kun for henvendelser, I selv har godkendt."],
];

export function AgreementForm({ wsId, current, canEdit }: { wsId: string; current: AgreementOut["current"]; canEdit: boolean }) {
  const router = useRouter();
  const choose = useSubmit(async (model: string) => {
    await api(`/workspaces/${wsId}/agreement`, { method: "POST", body: JSON.stringify({ model }) });
    router.refresh();
  });
  return (
    <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
      <div>
        <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Prisaftale for reception</h2>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Aftalen bestemmer, hvad en godkendt henvendelse koster. Hver ændring gemmes som en ny version, og allerede godkendte henvendelser beholder den pris, der gjaldt, da de blev godkendt.</p>
      </div>
      <p className="p-space-sm rounded-lg bg-tertiary-fixed text-on-tertiary-fixed font-body-sm text-body-sm flex items-start gap-space-xs"><Icon name="info" size={18} />Der faktureres bagud hver måned på det betalingskort, ejeren har gemt under Fakturering. Uden kort faktureres der ikke.</p>
      {current ? <p className="font-body-md text-body-md">Gældende: <strong>model {current.model}</strong> (version {current.version}, {new Date(current.created_at).toLocaleDateString("da-DK")}). {current.model === "B" ? `Pr. godkendt henvendelse: ${kr(current.lead_fee.net_minor)} ekskl. moms (${kr(current.lead_fee.gross_minor)} inkl. moms).` : `Månedspris: ${kr(current.monthly.net_minor)} ekskl. moms.`}</p>
        : <p className="font-body-md text-body-md">Ingen aftale valgt endnu. Henvendelser kan ikke godkendes, før der er valgt en model.</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
        {MODELS.map(([m, title, price, text]) => {
          const on = current?.model === m;
          return (
            <div key={m} className={`rounded-xl p-space-md flex flex-col gap-space-xs ${on ? "bg-primary-container text-on-primary" : "bg-surface-container-low"}`}>
              <span className="font-label-lg text-label-lg font-bold">{title}</span>
              <span className="font-headline-sm text-headline-sm">{price}</span>
              <span className={`font-body-sm text-body-sm ${on ? "text-on-primary-container" : "text-on-surface-variant"}`}>{text}</span>
              {canEdit && !on && <div className="pt-space-xs"><Button type="button" variant="tonal" disabled={choose.pending} onClick={() => choose.run(m)}>Vælg model {m}</Button></div>}
              {on && <span className="font-label-md text-label-md flex items-center gap-1"><Icon name="check_circle" size={18} />Valgt</span>}
            </div>
          );
        })}
      </div>
      {!canEdit && <p className="font-body-sm text-body-sm text-on-surface-variant">Kun ejeren kan vælge prismodel.</p>}
      <ErrorBox error={choose.error} />
    </section>
  );
}
