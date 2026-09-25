"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Button, ErrorBox, inputCls, useSubmit } from "@/components/ui";

export type PhoneNumber = { id: string; e164: string; provider_number_id: string | null; label: string; active: boolean; greeting: string };

export function NumberForm({ wsId }: { wsId: string }) {
  const router = useRouter();
  const [f, setF] = useState({ e164: "", provider_number_id: "", label: "", greeting: "" });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const add = useSubmit(async () => {
    await api(`/workspaces/${wsId}/phone-numbers`, { method: "POST", body: JSON.stringify({ ...f, provider_number_id: f.provider_number_id || null }) });
    setF({ e164: "", provider_number_id: "", label: "", greeting: "" }); router.refresh();
  });
  const field = (k: keyof typeof f, label: string, placeholder: string) => (
    <div><label htmlFor={`pn-${k}`} className="block font-label-md text-label-md font-semibold mb-1">{label}</label><input id={`pn-${k}`} className={inputCls} placeholder={placeholder} value={f[k]} onChange={set(k)} /></div>
  );
  return (
    <form className="flex flex-col gap-space-sm p-space-md rounded-lg bg-surface-container-low" onSubmit={(e) => { e.preventDefault(); add.run(); }}>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-space-sm">{field("e164", "Nummer", "+4570123456")}{field("provider_number_id", "Vapi nummer-id", "fx 3f1c…")}{field("label", "Navn", "Hovednummer")}</div>
      {field("greeting", "Hilsen (valgfri)", "Standard: \"Hej, du har ringet til … Du taler med en digital assistent …\"")}
      {fieldError(add.error, "e164") && <p role="alert" className="text-label-md text-error">Nummeret skal være i internationalt format, fx +4570123456.</p>}
      {!fieldError(add.error, "e164") && <ErrorBox error={add.error} />}
      <div><Button type="submit" icon="add_call" disabled={add.pending || !f.e164.trim()}>Tilknyt nummer</Button></div>
    </form>
  );
}

export function NumberRow({ wsId, n, canManage }: { wsId: string; n: PhoneNumber; canManage: boolean }) {
  const router = useRouter();
  const toggle = useSubmit(async () => {
    await api(`/workspaces/${wsId}/phone-numbers/${n.id}`, { method: "PATCH", body: JSON.stringify({ active: !n.active }) });
    router.refresh();
  });
  return (
    <li className="flex flex-wrap items-center gap-space-sm p-space-sm rounded-lg bg-surface-container-low">
      <span className="font-label-lg text-label-lg text-primary">{n.e164}</span>
      <span className="font-body-sm text-body-sm text-on-surface-variant">{n.label}{n.provider_number_id ? ` · Vapi-id ${n.provider_number_id}` : ""}</span>
      <span className={`ml-auto px-2 py-0.5 rounded-full font-label-sm text-label-sm ${n.active ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-high text-on-surface-variant"}`}>{n.active ? "Aktiv" : "Slået fra"}</span>
      {canManage && <Button type="button" variant="ghost" onClick={() => toggle.run()} disabled={toggle.pending}>{n.active ? "Slå fra" : "Slå til"}</Button>}
      <ErrorBox error={toggle.error} />
    </li>
  );
}
