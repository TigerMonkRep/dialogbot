"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Button, ErrorBox, Field, Input, useSubmit } from "@/components/ui";

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

/** A customer who was recommended but did not use the link can type the ambassador's code (first 30 days). */
export function ReferralCode({ wsId }: { wsId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const { run, pending, error } = useSubmit(async () => {
    await api(`/workspaces/${wsId}/referral`, { method: "PUT", body: JSON.stringify({ code }) });
    router.refresh();
  });
  if (!open) return <button type="button" onClick={() => setOpen(true)} className="self-start font-label-md text-label-md text-primary underline">Har I fået en ambassadørkode?</button>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm flex flex-col sm:flex-row sm:items-end gap-space-sm">
      <div className="flex-1"><Field label="Ambassadørkode" hint="Fra den, der anbefalede Dialogbot. I får 50 % rabat på første fakturerede måned." error={fieldError(error, "code")}><Input required value={code} onChange={(e) => setCode(e.target.value)} placeholder="Fx MADS42" /></Field></div>
      <Button type="submit" icon="loyalty" disabled={pending}>{pending ? "Gemmer…" : "Tilføj kode"}</Button>
      <ErrorBox error={error} />
    </form>
  );
}
