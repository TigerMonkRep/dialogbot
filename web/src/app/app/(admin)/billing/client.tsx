"use client";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client";
import { Button, ErrorBox, useSubmit } from "@/components/ui";

/** Opens Stripe Checkout (setup mode) where the owner saves a card. Nothing is charged there. */
export function AddCard({ wsId, hasCard }: { wsId: string; hasCard: boolean }) {
  const go = useSubmit(async () => {
    const r = await api<{ url: string }>(`/workspaces/${wsId}/billing/card/checkout`, { method: "POST", body: "{}" });
    window.location.assign(r.url);
  });
  return (
    <div className="flex flex-col gap-space-xs">
      <div><Button type="button" variant={hasCard ? "tonal" : "primary"} icon="credit_card" onClick={() => go.run()} disabled={go.pending}>{go.pending ? "Åbner Stripe…" : hasCard ? "Skift betalingskort" : "Tilføj betalingskort"}</Button></div>
      <ErrorBox error={go.error} />
    </div>
  );
}

export function InvoiceMonth({ wsId, month, label }: { wsId: string; month: string; label: string }) {
  const router = useRouter();
  const run = useSubmit(async () => {
    await api(`/workspaces/${wsId}/billing/invoices`, { method: "POST", body: JSON.stringify({ month }) });
    router.refresh();
  });
  return (
    <div className="flex flex-col gap-space-xs">
      <div><Button type="button" variant="tonal" icon="receipt_long" onClick={() => run.run()} disabled={run.pending}>{run.pending ? "Opretter…" : `Fakturér ${label} nu`}</Button></div>
      <ErrorBox error={run.error} />
    </div>
  );
}
