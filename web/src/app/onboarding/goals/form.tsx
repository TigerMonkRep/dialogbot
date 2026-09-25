"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Textarea, useSubmit } from "@/components/ui";

/** O03/G02: product intent, guidance preference and reception capabilities. Callback belongs to reception; booking is optional. */
export function GoalsForm({ wsId, goals, canEdit }: { wsId: string; goals: Record<string, unknown>; canEdit: boolean }) {
  const router = useRouter();
  const [f, setF] = useState(goals);
  const [saved, setSaved] = useState(false);
  const reception = f.product_intent !== "campaigns";
  const { run, pending, error } = useSubmit(async () => {
    const body = { ...f, expected_version: goals.version, inbound_phone: reception && f.inbound_phone, callback: reception && f.callback, webchat: reception && f.webchat };
    await api(`/workspaces/${wsId}/goals`, { method: "PUT", body: JSON.stringify(body) });
    setSaved(true); router.refresh();
  });
  const cb = (k: string, label: string, hint?: string) => (
    <label className="flex items-start gap-3 rounded-xl border border-line bg-white p-3 text-sm">
      <input type="checkbox" className="mt-1" checked={Boolean(f[k])} onChange={(e) => { setSaved(false); setF({ ...f, [k]: e.target.checked }); }} disabled={!canEdit} />
      <span><strong>{label}</strong>{hint && <span className="block text-xs text-muted">{hint}</span>}</span>
    </label>
  );
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-4">
      <ErrorBox error={error} />
      {saved && <Alert kind="ok">Gemt. Planen er opdateret ud fra dine mål.</Alert>}
      <Field label="Produkt">
        <select className="w-full rounded-xl border border-line bg-white px-3.5 py-2.5 text-sm" value={String(f.product_intent)} onChange={(e) => { setSaved(false); setF({ ...f, product_intent: e.target.value }); }} disabled={!canEdit}>
          <option value="reception">Reception</option><option value="campaigns">Kampagner</option><option value="both">Begge dele</option>
        </select>
      </Field>
      <Field label="Vejledning">
        <select className="w-full rounded-xl border border-line bg-white px-3.5 py-2.5 text-sm" value={String(f.guidance_mode)} onChange={(e) => { setSaved(false); setF({ ...f, guidance_mode: e.target.value }); }} disabled={!canEdit}>
          <option value="guided">Guid mig trin for trin</option><option value="self_managed">Jeg vil selv sætte op</option>
        </select>
      </Field>
      {reception ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {cb("inbound_phone", "Indgående telefoni", "Besvarer hovednummer. Kræver telefoniudbyder (senere milepæl).")}
          {cb("webchat", "Hjemmeside-webchat", "Widget på jeres hjemmeside.")}
          {cb("callback", "Bestilt callback", "Hører under reception – ikke en separat prisplan.")}
          {cb("booking", "Aftalebooking", "Valgfri. Kræver kalenderforbindelse.")}
        </div>
      ) : <Alert kind="info">Et kampagne-only arbejdsrum får ingen telefon- eller kalendertrin i planen.</Alert>}
      <Field label="Samtalemål (ét pr. linje)" hint="Fx ‘uforpligtende tilbud på gulvafslibning’">
        <Textarea value={(f.conversation_goals as string[] ?? []).join("\n")} onChange={(e) => { setSaved(false); setF({ ...f, conversation_goals: e.target.value.split("\n").filter(Boolean) }); }} disabled={!canEdit} />
      </Field>
      <div className="flex gap-3">
        <Button type="submit" disabled={pending || !canEdit}>{pending ? "Gemmer…" : "Gem mål"}</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/onboarding/languages")}>Fortsæt til sprog →</Button>
      </div>
    </form>
  );
}
