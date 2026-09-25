"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, useSubmit } from "@/components/ui";

const LANGS = [["da", "Dansk"], ["en", "Engelsk"], ["de", "Tysk"], ["sv", "Svensk"], ["no", "Norsk"]];

/** O04: four separately configured language levels. Voice preview requires the AI adapter (not yet available). */
export function LanguagesForm({ wsId, settings, canEdit }: { wsId: string; settings: Record<string, unknown>; canEdit: boolean }) {
  const router = useRouter();
  const [f, setF] = useState(settings);
  const [saved, setSaved] = useState(false);
  const enabled = (f.enabled_conversation_languages as string[]) ?? ["da"];
  const { run, pending, error } = useSubmit(async () => { await api(`/workspaces/${wsId}/languages`, { method: "PUT", body: JSON.stringify({ ...f, expected_version: settings.version }) }); setSaved(true); router.refresh(); });
  const sel = (k: string, label: string, hint: string) => (
    <Field label={label} hint={hint} error={fieldError(error, k)}>
      <select className="w-full rounded-xl border border-line bg-white px-3.5 py-2.5 text-sm" value={String(f[k])} onChange={(e) => { setSaved(false); setF({ ...f, [k]: e.target.value }); }} disabled={!canEdit}>
        {LANGS.map(([c, l]) => <option key={c} value={c}>{l}</option>)}
      </select>
    </Field>
  );
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-4">
      <ErrorBox error={error} />
      {saved && <Alert kind="ok">Gemt.</Alert>}
      {sel("interface_language", "a) Brugerfladesprog", "Menuer og knapper i portalen")}
      {sel("default_conversation_language", "b) Standardsamtalesprog", "Assistenten svarer som standard på dette sprog")}
      <fieldset className="space-y-2 text-sm"><legend className="font-semibold text-primary-dark">c) Tilladte samtalesprog</legend>
        <div className="flex flex-wrap gap-3">{LANGS.map(([c, l]) => (
          <label key={c} className="flex items-center gap-2"><input type="checkbox" checked={enabled.includes(c)} disabled={!canEdit} onChange={(e) => { setSaved(false); setF({ ...f, enabled_conversation_languages: e.target.checked ? [...enabled, c] : enabled.filter((x) => x !== c) }); }} /> {l}</label>
        ))}</div>
        {fieldError(error, "default_conversation_language") && <p className="text-xs text-danger">Standardsproget skal være blandt de tilladte.</p>}
      </fieldset>
      {sel("report_language", "d) Rapportsprog", "Daglige resuméer på SMS/e-mail")}
      <p className="text-xs text-muted">Stemmeprøve kræver stemmeadapteren, som tilkobles i receptionsmilepælen.</p>
      <div className="flex gap-3">
        <Button type="submit" disabled={pending || !canEdit}>{pending ? "Gemmer…" : "Gem sprog"}</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/app/knowledge")}>Fortsæt til viden →</Button>
      </div>
    </form>
  );
}
