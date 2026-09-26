"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";

export type Script = { version: number; persona_name: string; address_form: string; greeting: string; collect: string[]; escalation: string; avoid: string; closing: string };
type Suggestion = Pick<Script, "greeting" | "collect" | "escalation" | "avoid" | "closing">;

/** R05 manuscript. Empty script + AI available: a proposal is filled in (not saved) for the owner to edit. */
export function ScriptEditor({ wsId, script, canManage, aiReady }: { wsId: string; script: Script; canManage: boolean; aiReady: boolean }) {
  const router = useRouter();
  const [f, setF] = useState<Script>(script);
  const [collectText, setCollectText] = useState(script.collect.join("\n"));
  const [note, setNote] = useState<"suggested" | "saved" | null>(null);
  useEffect(() => { setF(script); setCollectText(script.collect.join("\n")); }, [script.version]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/reception/script`, { method: "PUT", body: JSON.stringify({ ...f, collect: collectText.split("\n"), expected_version: script.version }) });
    setNote("saved"); router.refresh();
  });
  const suggest = useSubmit(async () => {
    const s = await api<Suggestion>(`/workspaces/${wsId}/reception/script/suggestions`, { method: "POST", body: "{}" });
    setF((cur) => ({ ...cur, ...s })); setCollectText(s.collect.join("\n")); setNote("suggested");
  });
  const empty = !script.greeting && !script.collect.length && !script.escalation && !script.avoid && !script.closing;
  const auto = useRef(false);
  useEffect(() => {
    if (auto.current || !empty || !canManage || !aiReady) return;
    auto.current = true; suggest.run();
  }, [empty, canManage, aiReady, suggest]);
  const set = (k: keyof Script) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { setNote(null); setF({ ...f, [k]: e.target.value }); };
  const field = (k: keyof Script, label: string, hint: string, rows = 2) => (
    <div>
      <label htmlFor={`rs-${k}`} className="block font-label-md text-label-md font-semibold mb-1">{label}</label>
      <textarea id={`rs-${k}`} rows={rows} className={`${inputCls} resize-y`} value={String(f[k] ?? "")} onChange={set(k)} disabled={!canManage} />
      <p className="mt-1 font-body-sm text-body-sm text-on-surface-variant">{hint}</p>
    </div>
  );
  return (
    <form className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <div className="flex flex-wrap items-start justify-between gap-space-sm">
        <div>
          <h2 className="font-headline-sm text-headline-sm text-primary">Receptionsmanuskript</h2>
          <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Styrer hvordan assistenten hilser, hvad den spørger om, og hvornår en medarbejder skal overtage – i telefonen og i chatten. Fakta og priser kommer stadig kun fra godkendt viden.</p>
        </div>
        {script.version > 0 && <span className="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-semibold">Aktiv version {script.version}</span>}
      </div>
      {!canManage && <Alert kind="info">Kun ejere og administratorer kan ændre manuskriptet.</Alert>}
      {suggest.pending && <p role="status" className="font-body-sm text-body-sm text-on-surface-variant flex items-center gap-space-xs"><Icon name="auto_awesome" size={18} />Skriver et forslag ud fra jeres virksomhed og viden…</p>}
      {note === "suggested" && <Alert kind="info">Forslag fra AI er sat ind. Ret til, og tryk &quot;Gem manuskript&quot;.</Alert>}
      {note === "saved" && <Alert kind="ok">Gemt. Assistenten bruger manuskriptet fra næste samtale.</Alert>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
        <div>
          <label htmlFor="rs-persona" className="block font-label-md text-label-md font-semibold mb-1">Navn på assistenten (valgfri)</label>
          <input id="rs-persona" className={inputCls} maxLength={60} placeholder="fx Sofie" value={f.persona_name} onChange={set("persona_name")} disabled={!canManage} />
        </div>
        <div>
          <label htmlFor="rs-form" className="block font-label-md text-label-md font-semibold mb-1">Tiltale</label>
          <select id="rs-form" className={inputCls} value={f.address_form} onChange={set("address_form")} disabled={!canManage}><option value="du">du (uformel)</option><option value="De">De (formel)</option></select>
        </div>
      </div>
      {field("greeting", "Telefonhilsen", "Brug {virksomhed} for firmanavnet. Nævner hilsenen ikke, at det er en digital assistent, tilføjer vi det automatisk.")}
      <div>
        <label htmlFor="rs-collect" className="block font-label-md text-label-md font-semibold mb-1">Det skal assistenten spørge om (ét pr. linje)</label>
        <textarea id="rs-collect" rows={4} className={`${inputCls} resize-y`} value={collectText} onChange={(e) => { setNote(null); setCollectText(e.target.value); }} disabled={!canManage} />
        <p className="mt-1 font-body-sm text-body-sm text-on-surface-variant">Bruges når kunden vil have tilbud, en tid eller et opkald. Ét spørgsmål ad gangen.</p>
      </div>
      {field("escalation", "Giv straks videre til en medarbejder når …", "Fx akutte skader eller klager. Assistenten lover et hurtigt opkald og opretter en henvendelse.")}
      {field("avoid", "Det må assistenten ikke love eller udtale sig om", "Fx endelige priser uden besigtigelse.")}
      {field("closing", "Afslutning", "Kort og venlig.", 1)}
      <ErrorBox error={save.error ?? suggest.error} />
      {canManage && (
        <div className="flex flex-wrap justify-end gap-space-sm">
          {aiReady && <Button type="button" variant="ghost" icon="auto_awesome" disabled={suggest.pending} onClick={() => suggest.run()}>Foreslå igen</Button>}
          <Button type="submit" icon="save" disabled={save.pending}>{save.pending ? "Gemmer…" : "Gem manuskript"}</Button>
        </div>
      )}
    </form>
  );
}
