"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Button, ErrorBox, Field, Input, Select, useSubmit } from "@/components/ui";

export function IntegrationNote() {
  const router = useRouter();
  const [f, setF] = useState({ system: "", status: "UKENDT", note: "" });
  const save = useSubmit(async () => {
    await api("/operator/salg/integrations", { method: "PUT", body: JSON.stringify({ ...f, label: f.system }) });
    setF({ system: "", status: "UKENDT", note: "" });
    router.refresh();
  });
  return (
    <form className="grid md:grid-cols-[1fr_12rem_1fr_auto] gap-2 items-end mt-3" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <Field label="System"><Input value={f.system} onChange={(e) => setF({ ...f, system: e.target.value })} placeholder="Planway" /></Field>
      <Field label="Status"><Select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
        <option value="AKTIV">Aktiv</option><option value="KRÆVER_OPSÆTNING">Kræver opsætning</option><option value="PLANLAGT">Planlagt</option><option value="UKENDT">Ukendt</option>
      </Select></Field>
      <Field label="Note"><Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="Fx via Zapier" /></Field>
      <Button type="submit" variant="secondary" disabled={!f.system.trim() || save.pending}>Gem</Button>
      <div className="md:col-span-4"><ErrorBox error={save.error} /></div>
    </form>
  );
}
