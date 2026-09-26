"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Icon, Select, useSubmit } from "@/components/ui";

const LANGS = [["da", "Dansk"], ["en", "Engelsk"], ["de", "Tysk"], ["sv", "Svensk"], ["no", "Norsk"]];

/** O04: four separately configured language levels. Voice preview requires the AI adapter (not yet available). */
export function LanguagesForm({ wsId, settings, canEdit }: { wsId: string; settings: Record<string, unknown>; canEdit: boolean }) {
  const router = useRouter();
  const [f, setF] = useState(settings);
  const [saved, setSaved] = useState(false);
  const enabled = (f.enabled_conversation_languages as string[]) ?? ["da"];
  const { run, pending, error } = useSubmit(async () => { await api(`/workspaces/${wsId}/languages`, { method: "PUT", body: JSON.stringify({ ...f, expected_version: settings.version }) }); setSaved(true); router.refresh(); });
  const sel = (k: string, label: string, hint: string) => (
    <div className="p-space-md rounded-xl bg-surface-container-low space-y-space-sm">
      <label className="block">
        <span className="font-label-sm text-label-sm uppercase text-on-surface-variant">{label}</span>
        <Select className="mt-1 bg-surface-container-lowest font-label-lg text-label-lg font-bold" value={String(f[k])} onChange={(e) => { setSaved(false); setF({ ...f, [k]: e.target.value }); }} disabled={!canEdit}>
          {LANGS.map(([c, l]) => <option key={c} value={c}>{l}</option>)}
        </Select>
      </label>
      <p className="font-body-sm text-body-sm text-on-surface-variant">{hint}</p>
      {fieldError(error, k) && <p role="alert" className="font-label-md text-label-md text-error">{fieldError(error, k)}</p>}
    </div>
  );
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-space-lg">
      <ErrorBox error={error} />
      {saved && <Alert kind="ok">Gemt.</Alert>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
        {sel("interface_language", "a) Brugerfladesprog", "Administration, menupunkter og knapper i denne portal.")}
        {sel("default_conversation_language", "b) Standardsamtalesprog", "Assistenten svarer som standard på dette sprog.")}
        <fieldset className="p-space-md rounded-xl bg-surface-container-low space-y-space-sm">
          <legend className="sr-only">c) Tilladte samtalesprog</legend>
          <span aria-hidden className="font-label-sm text-label-sm uppercase text-on-surface-variant">c) Tilladte samtalesprog</span>
          <div className="flex flex-wrap gap-1.5">{LANGS.map(([c, l]) => (
            <label key={c} className={`flex items-center gap-1.5 px-2 py-1 rounded font-label-sm text-label-sm font-semibold cursor-pointer ${enabled.includes(c) ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container text-on-surface"}`}>
              <input type="checkbox" className="w-3.5 h-3.5 accent-primary" checked={enabled.includes(c)} disabled={!canEdit} onChange={(e) => { setSaved(false); setF({ ...f, enabled_conversation_languages: e.target.checked ? [...enabled, c] : enabled.filter((x) => x !== c) }); }} />{l}
            </label>
          ))}</div>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Sprog assistenten må skifte til, når kunden gør det.</p>
          {fieldError(error, "default_conversation_language") && <p role="alert" className="font-label-md text-label-md text-error">Standardsproget skal være blandt de tilladte.</p>}
        </fieldset>
        {sel("report_language", "d) Daglig rapportsprog", "Daglige resuméer og ledelsesrapporter.")}
      </div>
      <p className="font-body-sm text-body-sm text-on-surface-variant flex items-center gap-space-xs"><Icon name="graphic_eq" size={16} />Stemmeprøve kræver stemmeadapteren, som ikke er tilkoblet endnu.</p>
      <div className="flex flex-wrap items-center justify-end gap-space-md pt-space-sm">
        <Button type="submit" variant="tonal" icon="save" disabled={pending || !canEdit}>{pending ? "Gemmer…" : "Gem sprog"}</Button>
        <Button type="button" onClick={() => router.push("/app/knowledge")}>Fortsæt til viden <Icon name="arrow_forward" size={18} className="text-secondary-fixed" /></Button>
      </div>
    </form>
  );
}
