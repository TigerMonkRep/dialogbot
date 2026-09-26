"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, apiBlob, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, inputCls, useSubmit } from "@/components/ui";

export type PhoneNumber = {
  id: string; e164: string; provider_number_id: string | null; label: string; active: boolean; greeting: string;
  voice_id: string; voice_model: string; speaking_style: string; voice: Record<string, string> | null;
};

const VOICE_MODELS: [string, string][] = [
  ["eleven_multilingual_v2", "Multilingual v2 – mest naturlig udtale (lidt langsommere svar)"],
  ["eleven_flash_v2_5", "Flash v2.5 – hurtigst svar, fast sat til dansk"],
  ["eleven_turbo_v2_5", "Turbo v2.5 – mellemvej"],
];

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
  const [open, setOpen] = useState(false);
  const toggle = useSubmit(async () => {
    await api(`/workspaces/${wsId}/phone-numbers/${n.id}`, { method: "PATCH", body: JSON.stringify({ active: !n.active }) });
    router.refresh();
  });
  return (
    <li className="flex flex-col gap-space-sm p-space-sm rounded-lg bg-surface-container-low">
      <div className="flex flex-wrap items-center gap-space-sm">
        <span className="font-label-lg text-label-lg text-primary">{n.e164}</span>
        <span className="font-body-sm text-body-sm text-on-surface-variant">{n.label}{n.provider_number_id ? ` · Vapi-id ${n.provider_number_id}` : ""}</span>
        <span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm ${n.voice_id ? "bg-secondary-container text-on-secondary-container" : "bg-tertiary-fixed text-on-tertiary-fixed"}`}>{n.voice_id ? "Dansk stemme valgt" : "Ingen stemme valgt"}</span>
        <span className={`ml-auto px-2 py-0.5 rounded-full font-label-sm text-label-sm ${n.active ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-high text-on-surface-variant"}`}>{n.active ? "Aktiv" : "Slået fra"}</span>
        {canManage && <Button type="button" variant="ghost" icon="record_voice_over" onClick={() => setOpen(!open)} aria-expanded={open}>Stemme og talestil</Button>}
        {canManage && <Button type="button" variant="ghost" onClick={() => toggle.run()} disabled={toggle.pending}>{n.active ? "Slå fra" : "Slå til"}</Button>}
      </div>
      <ErrorBox error={toggle.error} />
      {open && canManage && <VoiceEditor wsId={wsId} n={n} onSaved={() => { setOpen(false); router.refresh(); }} />}
    </li>
  );
}

/** Voice for Danish calls: an ElevenLabs voice id + model, and free-text speaking style (tone, du/De, dialect words). */
function VoiceEditor({ wsId, n, onSaved }: { wsId: string; n: PhoneNumber; onSaved: () => void }) {
  const [f, setF] = useState({ voice_id: n.voice_id, voice_model: n.voice_model, speaking_style: n.speaking_style, greeting: n.greeting });
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/phone-numbers/${n.id}`, { method: "PATCH", body: JSON.stringify(f) });
    onSaved();
  });
  const preview = useSubmit(async () => {
    const blob = await apiBlob(`/workspaces/${wsId}/phone-numbers/${n.id}/voice-preview`, { voice_id: f.voice_id, voice_model: f.voice_model, text: f.greeting || undefined });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    await audio.play();
  });
  const id = (k: string) => `v-${n.id}-${k}`;
  return (
    <form className="flex flex-col gap-space-sm p-space-sm rounded-lg bg-surface-container-lowest" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      {!n.voice_id && <Alert kind="warn">Uden en valgt stemme bruger Vapi sin standardstemme, som ikke er dansk. Vælg en dansk stemme, før I ringer.</Alert>}
      <p className="font-body-sm text-body-sm text-on-surface-variant">Opkald transskriberes på dansk (Deepgram Nova-3). Stemmen hentes fra ElevenLabs via jeres Vapi-konto: find en dansk stemme i ElevenLabs&apos; stemmebibliotek (filtrér på dansk), tilføj den til jeres stemmer, og kopiér dens <em>Voice ID</em>. <strong>Dialekt og accent kommer fra stemmen</strong> – vælg fx en stemme med jysk eller københavnsk accent, eller klon en rigtig medarbejders stemme med deres samtykke.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-sm">
        <div><label htmlFor={id("voice")} className="block font-label-md text-label-md font-semibold mb-1">ElevenLabs Voice ID</label>
          <input id={id("voice")} className={inputCls} placeholder="Id på ca. 20 tegn fra ElevenLabs" value={f.voice_id} onChange={(e) => setF({ ...f, voice_id: e.target.value.trim() })} /></div>
        <div><label htmlFor={id("model")} className="block font-label-md text-label-md font-semibold mb-1">Stemmemodel</label>
          <select id={id("model")} className={inputCls} value={f.voice_model} onChange={(e) => setF({ ...f, voice_model: e.target.value })}>
            {VOICE_MODELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></div>
      </div>
      <div><label htmlFor={id("style")} className="block font-label-md text-label-md font-semibold mb-1">Talestil (valgfri)</label>
        <textarea id={id("style")} className={`${inputCls} min-h-24`} maxLength={1000} placeholder={"fx: Lun og jordnær. Sig \"hej hej\" til farvel. Brug gerne et par jyske vendinger som \"det ka' vi godt\", men hold det forståeligt."} value={f.speaking_style} onChange={(e) => setF({ ...f, speaking_style: e.target.value })} />
        <p className="mt-1 font-body-sm text-body-sm text-on-surface-variant">Styrer ordvalg og tone. Det ændrer ikke fakta og gør ikke i sig selv stemmen jysk – det gør stemmevalget.</p></div>
      <div><label htmlFor={id("greeting")} className="block font-label-md text-label-md font-semibold mb-1">Hilsen (valgfri)</label>
        <input id={id("greeting")} className={inputCls} maxLength={500} placeholder={"Standard: \"Hej, du har ringet til … Du taler med en digital assistent …\""} value={f.greeting} onChange={(e) => setF({ ...f, greeting: e.target.value })} /></div>
      {fieldError(save.error, "voice_id") ? <p role="alert" className="text-label-md text-error">Voice ID skal være ElevenLabs&apos; id – kun bogstaver og tal.</p> : <ErrorBox error={save.error} />}
      {preview.error && (preview.error.code === "voice_preview_not_configured"
        ? <Alert kind="info">Stemmeprøven kræver en ElevenLabs-nøgle på serveren (<code>ELEVENLABS_API_KEY</code> i Render). Opkald virker uden den.</Alert>
        : <ErrorBox error={preview.error} />)}
      <div className="flex flex-wrap gap-space-sm">
        <Button type="button" variant="tonal" icon="play_circle" disabled={preview.pending || !f.voice_id} onClick={() => preview.run()}>{preview.pending ? "Henter prøve…" : "Hør stemmen"}</Button>
        <Button type="submit" icon="save" disabled={save.pending}>Gem stemme</Button>
      </div>
    </form>
  );
}
