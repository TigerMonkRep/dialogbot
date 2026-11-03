"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, useSubmit } from "@/components/ui";
import { useT } from "@/i18n/client";

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

const FLAGS = ["for_kort", "for_lang", "for_lav", "overstyret", "meget_baggrundsstøj"];

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
  const t = useT("settings");
  const [f, setF] = useState({ speaker_name: "", speaker_gender: "unknown", manuscript: "kort", typed: "", ok: false,
    firma: defaults.values.firma, ydelse: defaults.values.ydelse, by: defaults.values.by });
  const text = defaults.consent_text.replace("{name}", f.speaker_name || t("ownVoice.consent.speakerPlaceholder")).replaceAll("{firma}", f.firma || t("ownVoice.consent.companyPlaceholder"));
  const start = useSubmit(async () => {
    await api(`/workspaces/${wsId}/own-voices`, { method: "POST", body: JSON.stringify({
      speaker_name: f.speaker_name, speaker_gender: f.speaker_gender, manuscript: f.manuscript, consent_typed_name: f.typed,
      consent_accepted: f.ok, firma: f.firma, ydelse: f.ydelse, by: f.by }) });
    router.refresh();
  });
  return (
    <div className="bg-paper rounded-2xl p-4 border-2 border-ink flex flex-col gap-3">
      <h2 className="font-title-md text-title-md text-ink font-bold">{t("ownVoice.consent.who")}</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <Field label={t("ownVoice.consent.fullName")}><Input value={f.speaker_name} onChange={(e) => setF({ ...f, speaker_name: e.target.value })} autoComplete="name" /></Field>
        <Field label={t("ownVoice.consent.voice")} hint={t("ownVoice.consent.voiceHint")}>
          <Select value={f.speaker_gender} onChange={(e) => setF({ ...f, speaker_gender: e.target.value })}>
            <option value="unknown">{t("ownVoice.consent.unknown")}</option><option value="female">{t("ownVoice.consent.female")}</option><option value="male">{t("ownVoice.consent.male")}</option>
          </Select>
        </Field>
        <Field label={t("ownVoice.consent.manuscript")}>
          <Select value={f.manuscript} onChange={(e) => setF({ ...f, manuscript: e.target.value })}>
            <option value="kort">{t("ownVoice.manus.kort")}</option><option value="standard">{t("ownVoice.manus.standard")}</option>
          </Select>
        </Field>
      </div>
      <p className="text-body-sm text-ink-soft">{t("ownVoice.consent.manuscriptHelp")}</p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <Field label={t("ownVoice.consent.company")}><Input value={f.firma} onChange={(e) => setF({ ...f, firma: e.target.value })} maxLength={60} /></Field>
        <Field label={t("ownVoice.consent.service")}><Input value={f.ydelse} onChange={(e) => setF({ ...f, ydelse: e.target.value })} maxLength={60} /></Field>
        <Field label={t("ownVoice.consent.city")}><Input value={f.by} onChange={(e) => setF({ ...f, by: e.target.value })} maxLength={60} /></Field>
      </div>
      <h2 className="font-title-md text-title-md text-ink font-bold">{t("ownVoice.consent.consentTitle")}</h2>
      <blockquote className="rounded-lg bg-panel p-3 text-body-md">{text}</blockquote>
      <Field label={t("ownVoice.consent.typed")} hint={t("ownVoice.consent.typedHint")}>
        <Input value={f.typed} onChange={(e) => setF({ ...f, typed: e.target.value })} />
      </Field>
      <label className="flex items-start gap-2 text-body-md">
        <input type="checkbox" className="mt-1 w-5 h-5" checked={f.ok} onChange={(e) => setF({ ...f, ok: e.target.checked })} />
        {t("ownVoice.consent.accept")}
      </label>
      <div><Button type="button" icon="mic" onClick={() => start.run()} disabled={start.pending || !f.ok || f.speaker_name.length < 2}>{t("ownVoice.consent.start")}</Button></div>
      <ErrorBox error={start.error} />
    </div>
  );
}

function Studio({ wsId, project, manuscript }: { wsId: string; project: Project; manuscript: Manuscript }) {
  const router = useRouter();
  const t = useT("settings");
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
    try { await rec.start(); setActive(id); } catch { setError({ code: "mic", message: t("ownVoice.studio.micError") } as ApiError); }
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
    <div className="flex flex-col gap-3">
      <div className="bg-paper rounded-2xl p-4 border-2 border-ink flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-title-md text-title-md text-ink font-bold">{t("ownVoice.studio.title", { name: p.speaker_name })}</h2>
          <span className="text-label-lg tabular-nums">{t("ownVoice.studio.progress", { done, total: p.total })}</span>
        </div>
        <div className="h-2 rounded-full bg-line overflow-hidden" aria-hidden="true">
          <div className="h-full bg-success-soft transition-all" style={{ width: `${(100 * done) / p.total}%` }} />
        </div>
        <details><summary className="text-label-lg cursor-pointer">{t("ownVoice.studio.howTo")}</summary>
          <ul className="list-disc pl-5 mt-1 text-body-sm">{manuscript.instructions.map((i) => <li key={i}>{i}</li>)}</ul>
        </details>
        <ErrorBox error={error} />
      </div>
      <ol className="flex flex-col gap-2">
        {manuscript.sentences.map((s, i) => {
          const r = p.recordings[s.id];
          const isActive = active === s.id;
          return (
            <li key={s.id} className={`rounded-2xl p-3 bg-paper border-2 border-ink flex flex-col gap-1 border ${s.id === next ? "border-ink" : "border-transparent"}`}>
              <div className="flex items-start gap-2">
                <span className="text-label-sm text-ink-soft tabular-nums w-10 shrink-0">{i + 1}.</span>
                <div className="flex-1">
                  <p className="text-body-lg">{s.text}</p>
                  {s.spoken_hint !== s.text && <p className="text-body-sm text-ink-soft">{t("ownVoice.studio.example", { text: s.spoken_hint })}</p>}
                </div>
                {r && <span className={`shrink-0 px-2 py-0.5 rounded-full text-label-sm ${r.qc.ok ?"bg-success-soft text-success":"bg-danger-soft text-danger"}`}>{r.qc.ok ? t("ownVoice.studio.approved") : t("ownVoice.studio.notApproved")}</span>}
              </div>
              {r && !r.qc.ok && <Alert kind="warn">{r.qc.flags.map((f) => (FLAGS.includes(f) ? t(`ownVoice.flag.${f}`) : f)).join(" ")}</Alert>}
              {isActive && <div className="h-2 rounded-full bg-line overflow-hidden" aria-label={t("ownVoice.studio.level")}><div className="h-full bg-ink" style={{ width: `${Math.min(100, rec.level * 140)}%` }} /></div>}
              <div className="flex flex-wrap gap-2 pl-12">
                {isActive
                  ? <Button type="button" icon="stop" onClick={() => stop(s.id)}>{t("ownVoice.studio.stopSave")}</Button>
                  : <Button type="button" variant={r ? "tonal" : "primary"} icon="mic" disabled={rec.recording || busy !== null || p.status !== "recording"} onClick={() => record(s.id)}>{r ? t("ownVoice.studio.again") : t("ownVoice.studio.record")}</Button>}
                {r && !isActive && <Button type="button" variant="tonal" icon="play_arrow" onClick={() => listen(s.id)}>{t("ownVoice.studio.listen")}</Button>}
                {busy === s.id && <span className="text-body-sm text-ink-soft self-center">{t("ownVoice.studio.checking")}</span>}
              </div>
            </li>
          );
        })}
      </ol>
      <div className="bg-paper rounded-2xl p-4 border-2 border-ink flex flex-col gap-2">
        <p className="text-body-md">{t("ownVoice.studio.submitIntro")}</p>
        <div><Button type="button" icon="send" disabled={done < p.total || submit.pending} onClick={() => submit.run()}>{t("ownVoice.studio.submit")}</Button></div>
        <ErrorBox error={submit.error} />
      </div>
    </div>
  );
}

function Status({ wsId, p }: { wsId: string; p: Project }) {
  const router = useRouter();
  const t = useT("settings");
  const [confirm, setConfirm] = useState(false);
  const withdraw = useSubmit(async () => { await api(`/workspaces/${wsId}/own-voices/${p.id}`, { method: "DELETE" }); router.refresh(); });
  const v = p.voice;
  const state = p.status === "withdrawn" ? t("ownVoice.status.withdrawn")
    : v?.active ? t("ownVoice.status.ready")
    : v?.consent_review === "blocked" ? t("ownVoice.status.blocked")
    : t("ownVoice.status.pending");
  return (
    <li className="rounded-2xl p-3 bg-paper border-2 border-ink flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <Icon name="record_voice_over" className="text-ink" />
        <h3 className="text-label-lg text-ink">{p.speaker_name}</h3>
        <span className="ml-auto text-body-sm text-ink-soft">{t("ownVoice.status.recordings", { manus: t(`ownVoice.manus.${p.manuscript}Short`), done: p.approved_recordings, total: p.total })}</span>
      </div>
      <p className="text-body-sm">{state}</p>
      {p.status !== "withdrawn" && (confirm
        ? <div className="flex flex-wrap gap-2 items-center rounded-lg bg-danger-soft text-danger p-2">
            <span className="text-body-sm">{t("ownVoice.status.withdrawWarning")}</span>
            <Button type="button" icon="delete" onClick={() => withdraw.run()} disabled={withdraw.pending}>{t("ownVoice.status.withdraw")}</Button>
            <Button type="button" variant="tonal" onClick={() => setConfirm(false)}>{t("ownVoice.status.keep")}</Button>
          </div>
        : <div><Button type="button" variant="tonal" icon="block" onClick={() => setConfirm(true)}>{t("ownVoice.status.withdraw")}</Button></div>)}
      <ErrorBox error={withdraw.error} />
    </li>
  );
}

export function OwnVoice({ wsId, projects, defaults, manuscript }: {
  wsId: string; projects: Project[]; defaults: Manuscript; manuscript: Manuscript | null;
}) {
  const t = useT("settings");
  const current = projects.find((p) => p.status === "recording");
  const others = projects.filter((p) => p !== current);
  return (
    <div className="flex flex-col gap-4">
      <Link href="/app/voices" className="flex items-center gap-1 text-label-lg text-ink underline w-fit"><Icon name="arrow_back" size={18} />{t("ownVoice.back")}</Link>
      <Alert kind="info">{t("ownVoice.notice")}</Alert>
      {current && manuscript ? <Studio wsId={wsId} project={current} manuscript={manuscript} /> : <Consent wsId={wsId} defaults={defaults} />}
      {others.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="font-title-md text-title-md text-ink font-bold">{t("ownVoice.previous")}</h2>
          <ul className="flex flex-col gap-2">{others.map((p) => <Status key={p.id} wsId={wsId} p={p} />)}</ul>
        </section>
      )}
    </div>
  );
}
