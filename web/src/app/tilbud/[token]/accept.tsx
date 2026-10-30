"use client";
import { useState } from "react";
import { api } from "@/lib/client";
import { Button, ErrorBox, Field, Input, useSubmit } from "@/components/ui";

export function AcceptOffer({ token, company }: { token: string; company: string }) {
  const [name, setName] = useState(company);
  const [ok, setOk] = useState(false);
  const { run, pending, error } = useSubmit(async () => {
    const r = await api<{ workspace_id: string; checkout_url: string | null; next: string }>(`/public/offers/${encodeURIComponent(token)}/accept`, { method: "POST", body: JSON.stringify({ confirm: ok, workspace_name: name }) });
    await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: r.workspace_id }) });
    window.location.assign(r.checkout_url ?? r.next);
  });
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); run(); }}>
      <Field label="Navn på jeres arbejdsrum"><Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} /></Field>
      <label className="flex items-start gap-2 text-body-sm"><input type="checkbox" className="mt-1 accent-primary" checked={ok} onChange={(e) => setOk(e.target.checked)} /><span>Jeg accepterer tilbuddet og vilkårene ovenfor på vegne af virksomheden.</span></label>
      <ErrorBox error={error} />
      <Button type="submit" icon="check_circle" disabled={pending || !ok || !name.trim()} className="w-full h-12 rounded-lg">{pending ? "Accepterer…" : "Accepter og gå til betaling"}</Button>
    </form>
  );
}
