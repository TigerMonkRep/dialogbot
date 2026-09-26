"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Select, Textarea, useSubmit } from "@/components/ui";

/** O03/G02: product intent, guidance preference and reception capabilities. Callback belongs to reception; booking is optional. */
type GoalSuggestion = { conversation_goals: string[]; channels: Record<string, boolean>; reason: string };

export function GoalsForm({ wsId, goals, canEdit, aiReady = false }: { wsId: string; goals: Record<string, unknown>; canEdit: boolean; aiReady?: boolean }) {
  const router = useRouter();
  const [f, setF] = useState(goals);
  const [saved, setSaved] = useState(false);
  const reception = f.product_intent !== "campaigns";
  const [suggested, setSuggested] = useState<GoalSuggestion | null>(null);
  const suggest = useSubmit(async () => {
    const r = await api<GoalSuggestion>(`/workspaces/${wsId}/goals/suggestions`, { method: "POST", body: "{}" });
    setSaved(false); setSuggested(r);
    setF((cur) => ({ ...cur, ...(cur.product_intent !== "campaigns" ? r.channels : {}), conversation_goals: r.conversation_goals.length ? r.conversation_goals : cur.conversation_goals }));
  });
  // Empty goals: propose a starting point right away. The owner edits and saves; nothing is stored before that.
  const auto = useRef(false);
  useEffect(() => {
    if (auto.current || !aiReady || !canEdit || ((goals.conversation_goals as string[] | undefined) ?? []).length) return;
    auto.current = true; suggest.run();
  }, [aiReady, canEdit, goals.conversation_goals, suggest]);
  const { run, pending, error } = useSubmit(async () => {
    const body = { ...f, expected_version: goals.version, inbound_phone: reception && f.inbound_phone, callback: reception && f.callback, webchat: reception && f.webchat };
    await api(`/workspaces/${wsId}/goals`, { method: "PUT", body: JSON.stringify(body) });
    setSaved(true); router.refresh();
  });
  const cb = (k: string, label: string, hint?: string) => (
    <label className={`flex items-start gap-space-md p-space-md rounded-xl bg-surface-container-low transition-all hover:bg-surface-container ${canEdit ? "cursor-pointer" : ""}`}>
      <input type="checkbox" className="mt-1 w-4 h-4 rounded accent-primary" checked={Boolean(f[k])} onChange={(e) => { setSaved(false); setF({ ...f, [k]: e.target.checked }); }} disabled={!canEdit} />
      <span className="space-y-0.5"><span className="block font-label-lg text-label-lg font-bold text-on-surface">{label}</span>{hint && <span className="block font-body-sm text-body-sm text-on-surface-variant">{hint}</span>}</span>
    </label>
  );
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-space-lg">
      <ErrorBox error={error} />
      {saved && <Alert kind="ok">Gemt. Planen er opdateret ud fra dine mål.</Alert>}
      {suggest.pending && <p role="status" className="font-body-sm text-body-sm text-on-surface-variant flex items-center gap-space-xs"><Icon name="auto_awesome" size={18} />Laver forslag ud fra jeres virksomhed og viden…</p>}
      {suggested && !saved && <Alert kind="info">Forslag fra AI er sat ind nedenfor{suggested.reason ? ` – ${suggested.reason}` : ""}. Ret til, og tryk &quot;Gem mål&quot;.</Alert>}
      <ErrorBox error={suggest.error} />
      <Field label="Produkt">
        <Select value={String(f.product_intent)} onChange={(e) => { setSaved(false); setF({ ...f, product_intent: e.target.value }); }} disabled={!canEdit}>
          <option value="reception">Reception</option><option value="campaigns">Kampagner</option><option value="both">Begge dele</option>
        </Select>
      </Field>
      <Field label="Vejledning">
        <Select value={String(f.guidance_mode)} onChange={(e) => { setSaved(false); setF({ ...f, guidance_mode: e.target.value }); }} disabled={!canEdit}>
          <option value="guided">Guid mig trin for trin</option><option value="self_managed">Jeg vil selv sætte op</option>
        </Select>
      </Field>
      {reception ? (
        <div className="grid gap-space-md md:grid-cols-2">
          {cb("inbound_phone", "Indgående telefoni", "Assistenten tager telefonen på jeres nummer (via Vapi).")}
          {cb("webchat", "Hjemmeside-webchat", "Widget på jeres hjemmeside.")}
          {cb("callback", "Bestilt callback", "Hører under reception – ikke en separat prisplan.")}
          {cb("booking", "Aftalebooking", "Valgfri. Kræver kalenderforbindelse.")}
        </div>
      ) : <Alert kind="info">Et kampagne-only arbejdsrum får ingen telefon- eller kalendertrin i planen.</Alert>}
      <Field label="Samtalemål (ét pr. linje)" hint="Fx ‘uforpligtende tilbud på gulvafslibning’">
        <Textarea value={(f.conversation_goals as string[] ?? []).join("\n")} onChange={(e) => { setSaved(false); setF({ ...f, conversation_goals: e.target.value.split("\n").filter(Boolean) }); }} disabled={!canEdit} />
      </Field>
      <div className="flex flex-wrap items-center justify-end gap-space-md pt-space-sm">
        {aiReady && canEdit && <Button type="button" variant="ghost" icon="auto_awesome" disabled={suggest.pending} onClick={() => suggest.run()}>Foreslå igen</Button>}
        <Button type="submit" variant="tonal" icon="save" disabled={pending || !canEdit}>{pending ? "Gemmer…" : "Gem mål"}</Button>
        <Button type="button" onClick={() => router.push("/onboarding/languages")}>Fortsæt til sprog <Icon name="arrow_forward" size={18} className="text-secondary-fixed" /></Button>
      </div>
    </form>
  );
}
