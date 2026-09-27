"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, useSubmit } from "@/components/ui";

type Qc = { seconds: number; flags: string[]; ok: boolean };
export type Project = {
  id: string; speaker_name: string; manuscript: "kort" | "standard"; status: "recording" | "submitted" | "withdrawn";
  recorded: number; approved_recordings: number; total: number; recordings: Record<string, { seconds: number; qc: Qc }>;
  values: { firma?: string; ydelse?: string; by?: string };
  voice: { profile_id: string; display_name: string; active: boolean; version_status: string | null; consent_review: string } | null;
  consent: { text: string; typed_name: string; accepted_at: string };
};
type Sentence = { id: string; category: string; text: string; spoken_hint: string };
export type Manuscript = {
  id: string; sentences: Sentence[]; instructions: string[]; estimated_minutes: number;
  values: { firma: string; ydelse: string; by: string }; consent_text: string;
};

const FLAG: Record<string, string> = {
  for_kort: "Optagelsen er for kort. Læs hele sætningen.",
  for_lang: "Optagelsen er for lang. Stop optagelsen, når sætningen er læst.",
  for_lav: "Lyden er for svag. Tal lidt højere eller hold mikrofonen tættere på.",
  overstyret: "Lyden er overstyret. Tal lidt lavere eller hold mikrofonen længere væk.",
  meget_baggrundsstøj: "Der er meget baggrundsstøj. Find et mere stille rum.",
};
const MANUS = { kort: "Kort manus (ca. 2 minutter): hurtig stemme med det samme", standard: "Standardmanus (ca. 30 minutter): bedste lighed, når træning er klar" };

/** Records mono 16-bit WAV in the browser (no compression, no browser noise suppression). */
function useRecorder() {
  const ctx = useRef<AudioContext | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const node = useRef<ScriptProcessorNode | null>(null);
  const chunks = useRef<Float32Array[]>([]);
  const [level, setLevel] = useState(0);
  const [recording, setRecording] = useState(false);

  const start = useCallback(async () => {
    stream.current = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    });
    ctx.current = new AudioContext();
    const src = ctx.current.createMediaStreamSource(stream.current);
    node.current = ctx.current.createScriptProcessor(4096, 1, 1);
    chunks.current = [];
    node.current.onaudioprocess = (e) => {
      const d = e.inputBuffer.getChannelData(0);
      chunks.current.push(new Float32Array(d));
      let m = 0;
      for (let i = 0; i < d.length; i += 64) m = Math.max(m, Math.abs(d[i]));
      setLevel(m);
    };
    src.connect(node.current);
    node.current.connect(ctx.current.destination);
    setRecording(true);
  }, []);

  const stop = useCallback(async (): Promise<Blob> => {
    const rate = ctx.current?.sampleRate ?? 48000;
    node.current?.disconnect();
    stream.current?.getTracks().forEach((t) => t.stop());
    await ctx.current?.close();
    setRecording(false);
    setLevel(0);
    const n = chunks.current.reduce((a, c) => a + c.length, 0);
    const buf = new ArrayBuffer(44 + n * 2);
    const v = new DataView(buf);
    const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt "); v.setUint32(16, 16, true);
    v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, n * 2, true);
    let o = 44;
    for (const c of chunks.current) for (let i = 0; i < c.length; i++, o += 2) v.setInt16(o, Math.max(-1, Math.min(1, c[i])) * 0x7fff, true);
    return new Blob([buf], { type: "audio/wav" });
  }, []);
  return { start, stop, level, recording };
}

function Consent({ wsId, defaults }: { wsId: string; defaults: Manuscript }) {
  const router = useRouter();
  const [f, setF] = useState({ speaker_name: "", speaker_gender: "unknown", manuscript: "kort", typed: "", ok: false,
    firma: defaults.values.firma, ydelse: defaults.values.ydelse, by: defaults.values.by });
  const text = defaults.consent_text.replace("{name}", f.speaker_name || "[indtalerens navn]").replaceAll("{firma}", f.firma || "virksomheden");
  const start = useSubmit(async () => {
    await api(`/workspaces/${wsId}/own-voices`, { method: "POST", body: JSON.stringify({
      speaker_name: f.speaker_name, speaker_gender: f.speaker_gender, manuscript: f.manuscript, consent_typed_name: f.typed,
      consent_accepted: f.ok, firma: f.firma, ydelse: f.ydelse, by: f.by }) });
    router.refresh();
  });
  return (
    <div className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm flex flex-col gap-space-md">
      <h2 className="font-title-md text-title-md text-primary font-bold">1. Hvem skal indtale?</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-sm">
        <Field label="Indtalerens fulde navn"><Input value={f.speaker_name} onChange={(e) => setF({ ...f, speaker_name: e.target.value })} autoComplete="name" /></Field>
        <Field label="Stemme" hint="Oplyses af indtaleren selv">
          <Select value={f.speaker_gender} onChange={(e) => setF({ ...f, speaker_gender: e.target.value })}>
            <option value="unknown">Vil ikke oplyse</option><option value="female">Kvindestemme</option><option value="male">Mandestemme</option>
          </Select>
        </Field>
        <Field label="Manuskript">
          <Select value={f.manuscript} onChange={(e) => setF({ ...f, manuscript: e.target.value })}>
            <option value="kort">{MANUS.kort}</option><option value="standard">{MANUS.standard}</option>
          </Select>
        </Field>
      </div>
      <p className="font-body-sm text-body-sm text-on-surface-variant">Manuskriptet bruger jeres egne oplysninger, så indtaleren læser sætninger om jeres forretning.</p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-space-sm">
        <Field label="Firmanavn"><Input value={f.firma} onChange={(e) => setF({ ...f, firma: e.target.value })} maxLength={60} /></Field>
        <Field label="Ydelse, fx gulvslibning"><Input value={f.ydelse} onChange={(e) => setF({ ...f, ydelse: e.target.value })} maxLength={60} /></Field>
        <Field label="By eller område"><Input value={f.by} onChange={(e) => setF({ ...f, by: e.target.value })} maxLength={60} /></Field>
      </div>
      <h2 className="font-title-md text-title-md text-primary font-bold">2. Samtykke fra indtaleren</h2>
      <blockquote className="rounded-lg bg-surface-container-low p-space-md font-body-md text-body-md">{text}</blockquote>
      <Field label="Indtaleren skriver sit fulde navn" hint="Skal være den person, der indtaler. Samtykket gennemgås af Dialogbot, før stemmen kan bruges.">
        <Input value={f.typed} onChange={(e) => setF({ ...f, typed: e.target.value })} />
      </Field>
      <label className="flex items-start gap-2 font-body-md text-body-md">
        <input type="checkbox" className="mt-1 w-5 h-5" checked={f.ok} onChange={(e) => setF({ ...f, ok: e.target.checked })} />
        Jeg er indtaleren og giver samtykke som beskrevet ovenfor.
      </label>
      <div><Button type="button" icon="mic" onClick={() => start.run()} disabled={start.pending || !f.ok || f.speaker_name.length < 2}>Start indtaling</Button></div>
      <ErrorBox error={start.error} />
    </div>
  );
}

function Studio({ wsId, project, manuscript }: { wsId: string; project: Project; manuscript: Manuscript }) {
  const router = useRouter();
  const rec = useRecorder();
  const [p, setP] = useState(project);
  const [active, setActive] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const next = manuscript.sentences.find((s) => !p.recordings[s.id]?.qc.ok)?.id ?? null;

  useEffect(() => { setP(project); }, [project]);

  const record = async (id: string) => {
    setError(null);
    try { await rec.start(); setActive(id); } catch { setError({ code: "mic", message: "Browseren fik ikke adgang til mikrofonen. Tillad mikrofonen i adresselinjen og prøv igen." } as ApiError); }
  };
  const stop = async (id: string) => {
    const wav = await rec.stop();
    setActive(null);
    setBusy(id);
    try {
      const r = await fetch(`/api/backend/workspaces/${wsId}/own-voices/${p.id}/recordings/${id}`, {
        method: "PUT", body: wav, credentials: "same-origin", headers: { "content-type": "audio/wav", "x-requested-with": "dialogbot" } });
      const body = await r.json();
      if (!r.ok) throw body;
      setP((old) => ({ ...old, recordings: { ...old.recordings, [id]: { seconds: body.qc.seconds, qc: body.qc } },
        recorded: Object.keys({ ...old.recordings, [id]: 1 }).length,
        approved_recordings: Object.entries({ ...old.recordings, [id]: { qc: body.qc } }).filter(([, x]) => (x as { qc: Qc }).qc.ok).length }));
    } catch (e) { setError(e as ApiError); } finally { setBusy(null); }
  };
  const listen = (id: string) => {
    audio.current?.pause();
    audio.current = new Audio(`/api/backend/workspaces/${wsId}/own-voices/${p.id}/recordings/${id}/audio`);
    void audio.current.play();
  };
  const submit = useSubmit(async () => { await api(`/workspaces/${wsId}/own-voices/${p.id}/submit`, { method: "POST" }); router.refresh(); });
  const done = p.approved_recordings;

  return (
    <div className="flex flex-col gap-space-md">
      <div className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm flex flex-col gap-space-sm">
        <div className="flex flex-wrap items-center justify-between gap-space-sm">
          <h2 className="font-title-md text-title-md text-primary font-bold">Indtaling: {p.speaker_name}</h2>
          <span className="font-label-lg text-label-lg tabular-nums">{done} af {p.total} godkendt</span>
        </div>
        <div className="h-2 rounded-full bg-surface-container-high overflow-hidden" aria-hidden="true">
          <div className="h-full bg-secondary-container transition-all" style={{ width: `${(100 * done) / p.total}%` }} />
        </div>
        <details><summary className="font-label-lg text-label-lg cursor-pointer">Sådan optager du</summary>
          <ul className="list-disc pl-5 mt-space-xs font-body-sm text-body-sm">{manuscript.instructions.map((i) => <li key={i}>{i}</li>)}</ul>
        </details>
        <ErrorBox error={error} />
      </div>
      <ol className="flex flex-col gap-space-sm">
        {manuscript.sentences.map((s, i) => {
          const r = p.recordings[s.id];
          const isActive = active === s.id;
          return (
            <li key={s.id} className={`rounded-xl p-space-md bg-surface-container-lowest shadow-sm flex flex-col gap-space-xs border ${s.id === next ? "border-primary" : "border-transparent"}`}>
              <div className="flex items-start gap-space-sm">
                <span className="font-label-sm text-label-sm text-on-surface-variant tabular-nums w-10 shrink-0">{i + 1}.</span>
                <div className="flex-1">
                  <p className="font-body-lg text-body-lg">{s.text}</p>
                  {s.spoken_hint !== s.text && <p className="font-body-sm text-body-sm text-on-surface-variant">Fx: {s.spoken_hint}</p>}
                </div>
                {r && <span className={`shrink-0 px-2 py-0.5 rounded-full font-label-sm text-label-sm ${r.qc.ok ? "bg-secondary-container text-on-secondary-container" : "bg-error-container text-on-error-container"}`}>{r.qc.ok ? "Godkendt" : "Optag igen"}</span>}
              </div>
              {r && !r.qc.ok && <Alert kind="warn">{r.qc.flags.map((f) => FLAG[f] ?? f).join(" ")}</Alert>}
              {isActive && <div className="h-2 rounded-full bg-surface-container-high overflow-hidden" aria-label="Lydniveau"><div className="h-full bg-primary" style={{ width: `${Math.min(100, rec.level * 140)}%` }} /></div>}
              <div className="flex flex-wrap gap-space-sm pl-12">
                {isActive
                  ? <Button type="button" icon="stop" onClick={() => stop(s.id)}>Stop og gem</Button>
                  : <Button type="button" variant={r ? "tonal" : "primary"} icon="mic" disabled={rec.recording || busy !== null || p.status !== "recording"} onClick={() => record(s.id)}>{r ? "Optag igen" : "Optag"}</Button>}
                {r && !isActive && <Button type="button" variant="tonal" icon="play_arrow" onClick={() => listen(s.id)}>Lyt</Button>}
                {busy === s.id && <span className="font-body-sm text-body-sm text-on-surface-variant self-center">Tjekker optagelsen …</span>}
              </div>
            </li>
          );
        })}
      </ol>
      <div className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm flex flex-col gap-space-sm">
        <p className="font-body-md text-body-md">Når alle sætninger er godkendt, sender du indtalingen. Dialogbot laver stemmen og gennemgår samtykket, før den kan bruges.</p>
        <div><Button type="button" icon="send" disabled={done < p.total || submit.pending} onClick={() => submit.run()}>Send til gennemgang</Button></div>
        <ErrorBox error={submit.error} />
      </div>
    </div>
  );
}

function Status({ wsId, p }: { wsId: string; p: Project }) {
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const withdraw = useSubmit(async () => { await api(`/workspaces/${wsId}/own-voices/${p.id}`, { method: "DELETE" }); router.refresh(); });
  const v = p.voice;
  const state = p.status === "withdrawn" ? "Samtykket er trukket tilbage. Optagelserne er slettet, og stemmen bruges ikke."
    : v?.active ? "Stemmen er klar og kan vælges på stemmesiden."
    : v?.consent_review === "blocked" ? "Samtykket er afvist. Kontakt Dialogbot."
    : "Afventer Dialogbots gennemgang af samtykket og en prøve af stemmen.";
  return (
    <li className="rounded-xl p-space-md bg-surface-container-lowest shadow-sm flex flex-col gap-space-xs">
      <div className="flex flex-wrap items-center gap-space-sm">
        <Icon name="record_voice_over" className="text-primary" />
        <h3 className="font-label-lg text-label-lg text-primary">{p.speaker_name}</h3>
        <span className="ml-auto font-body-sm text-body-sm text-on-surface-variant">{MANUS[p.manuscript].split(":")[0]} · {p.approved_recordings}/{p.total} optagelser</span>
      </div>
      <p className="font-body-sm text-body-sm">{state}</p>
      {p.status !== "withdrawn" && (confirm
        ? <div className="flex flex-wrap gap-space-sm items-center rounded-lg bg-error-container text-on-error-container p-space-sm">
            <span className="font-body-sm text-body-sm">Optagelserne slettes, og stemmen stopper med det samme.</span>
            <Button type="button" icon="delete" onClick={() => withdraw.run()} disabled={withdraw.pending}>Træk samtykket tilbage</Button>
            <Button type="button" variant="tonal" onClick={() => setConfirm(false)}>Behold</Button>
          </div>
        : <div><Button type="button" variant="tonal" icon="block" onClick={() => setConfirm(true)}>Træk samtykket tilbage</Button></div>)}
      <ErrorBox error={withdraw.error} />
    </li>
  );
}

export function OwnVoice({ wsId, projects, defaults, manuscript }: {
  wsId: string; projects: Project[]; defaults: Manuscript; manuscript: Manuscript | null;
}) {
  const current = projects.find((p) => p.status === "recording");
  const others = projects.filter((p) => p !== current);
  return (
    <div className="flex flex-col gap-space-lg">
      <Link href="/app/voices" className="flex items-center gap-1 font-label-lg text-label-lg text-primary underline w-fit"><Icon name="arrow_back" size={18} />Tilbage til stemmer</Link>
      <Alert kind="info">Egen stemme laves ud fra en kort optagelse. Ligheden med indtaleren kan variere, især for stemmer, der ligger langt fra modellens træningsstemmer. Fuld lighed kræver træning på standardmanuskriptet, som Dialogbot tilbyder senere.</Alert>
      {current && manuscript ? <Studio wsId={wsId} project={current} manuscript={manuscript} /> : <Consent wsId={wsId} defaults={defaults} />}
      {others.length > 0 && (
        <section className="flex flex-col gap-space-sm">
          <h2 className="font-title-md text-title-md text-primary font-bold">Tidligere indtalinger</h2>
          <ul className="flex flex-col gap-space-sm">{others.map((p) => <Status key={p.id} wsId={wsId} p={p} />)}</ul>
        </section>
      )}
    </div>
  );
}
