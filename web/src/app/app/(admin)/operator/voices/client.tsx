"use client";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { api, apiAudio, type ApiError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, Textarea, useSubmit } from "@/components/ui";

export type Rights = { id: string; kind: string; subject: string; license: string; source_url: string; revision: string | null; status: string;
  allowed_uses: string; restrictions: string; commercial_use: boolean | null; notes: string; reviewed_at: string | null };
type Version = { id: string; version: number; status: string; engine: string; method: string; model_repo: string; model_revision: string;
  references: { key: string; sha256: string; seconds?: number; source_id?: string }[]; settings: Record<string, number>; rights_record_ids: string[];
  checks: Record<string, { status: string; at?: string; by?: string; problems?: string[]; reason?: string; evidence?: Record<string, unknown> }>;
  missing_checks: string[]; created_at: string };
type Profile = { id: string; slug: string; display_name: string; gender: string; dialect: string | null; dialect_basis: string; age_description: string | null;
  source: string; visibility: string; workspace_id: string | null; active_version_id: string | null; versions: Version[];
  history: { action: string; at: string; after: Record<string, unknown> | null }[] };
export type OpData = { items: Profile[]; engine: string; engine_health: Record<string, unknown> };

const STATUS: Record<string, string> = { draft: "Kladde", pending_review: "Afventer kontrol", approved: "Godkendt", active: "Aktiv", suspended: "Suspenderet", retired: "Udfaset" };
const CHECK: Record<string, string> = { rights: "Rettigheder", normalization: "Dansk normalisering", synthesis_smoke: "Syntese (motor)", listening_test: "Lyttetest (≥3 lyttere)", telephony_test: "Telefontest" };
const tone = (s?: string) => s === "passed" ? "bg-secondary-container text-on-secondary-container" : s === "failed" ? "bg-error-container text-on-error-container" : "bg-surface-container-high";

export function OperatorVoices({ data, rights }: { data: OpData; rights: Rights[] }) {
  return (
    <div className="flex flex-col gap-space-lg">
      <Alert kind={data.engine === "available" ? "info" : "warn"} icon="memory">Talemotor: {data.engine} · {JSON.stringify(data.engine_health)}</Alert>
      <RightsPanel rights={rights} />
      {data.items.map((p) => <ProfilePanel key={p.id} p={p} rights={rights} />)}
      <NewProfile />
    </div>
  );
}

function RightsPanel({ rights }: { rights: Rights[] }) {
  const router = useRouter();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const review = useSubmit(async (id: string, status: string) => {
    await api(`/operator/voice-rights/${id}/review`, { method: "POST", body: JSON.stringify({ status, notes: notes[id] ?? "" }) });
    router.refresh();
  });
  return (
    <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm" aria-labelledby="rights-h">
      <h2 id="rights-h" className="font-headline-sm text-headline-sm text-primary">Rettigheder</h2>
      <p className="font-body-sm text-body-sm text-on-surface-variant">Kode, modelvægte, datasæt og indtaleraftaler dokumenteres hver for sig. Skriv i noten, hvad du faktisk har læst og hvor.</p>
      <ul className="flex flex-col gap-space-sm">{rights.map((r) => (
        <li key={r.id} className="rounded-lg bg-surface-container-low p-space-sm flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-space-sm"><span className="font-label-lg text-label-lg">{r.kind}: {r.subject}</span>
            <span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm ${tone(r.status === "verified" ? "passed" : r.status === "blocked" ? "failed" : "")}`}>{r.status}</span></div>
          <span className="font-body-sm text-body-sm">Licens: {r.license || "–"} · Revision: {r.revision ?? "ikke fastlåst"} · <a className="underline" href={r.source_url} target="_blank" rel="noreferrer">kilde</a></span>
          <pre className="whitespace-pre-wrap font-body-sm text-body-sm text-on-surface-variant">{r.notes}</pre>
          <div className="flex flex-wrap gap-space-sm items-end">
            <Field label="Gennemgangsnote"><Input value={notes[r.id] ?? ""} onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })} placeholder="Læst hele licensen på … den …" /></Field>
            <Button type="button" variant="tonal" onClick={() => review.run(r.id, "verified")} disabled={(notes[r.id] ?? "").length < 10}>Verificeret</Button>
            <Button type="button" variant="ghost" onClick={() => review.run(r.id, "blocked")} disabled={(notes[r.id] ?? "").length < 10}>Blokér</Button>
          </div>
        </li>))}</ul>
      <ErrorBox error={review.error} />
    </section>
  );
}

function ProfilePanel({ p, rights }: { p: Profile; rights: Rights[] }) {
  const router = useRouter();
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const act = async (path: string, body?: unknown) => {
    setBusy(true); setErr(null);
    try { await api(path, { method: "POST", body: JSON.stringify(body ?? {}) }); router.refresh(); } catch (e) { setErr(e as ApiError); } finally { setBusy(false); }
  };
  return (
    <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm" aria-label={p.display_name}>
      <div className="flex flex-wrap items-center gap-space-sm">
        <Icon name="record_voice_over" className="text-primary" />
        <h2 className="font-headline-sm text-headline-sm text-primary">{p.display_name}</h2>
        <span className="font-label-sm text-label-sm text-on-surface-variant">{p.slug} · {p.visibility === "workspace" ? `privat (${p.workspace_id})` : "platform"}</span>
        {p.active_version_id && <Button type="button" variant="ghost" icon="undo" disabled={busy} onClick={() => act(`/operator/voices/${p.id}/rollback`)}>Rul tilbage</Button>}
      </div>
      <p className="font-body-sm text-body-sm">Kilde: {p.source || "–"}</p>
      <p className="font-body-sm text-body-sm">Køn: {p.gender} · Dialekt: {p.dialect ?? "ikke vurderet"} · Alder: {p.age_description ?? "ukendt"}</p>
      <p className="font-body-sm text-body-sm text-on-surface-variant">Begrundelse: {p.dialect_basis || "–"}</p>
      <References profileId={p.id} />
      <NewVersion p={p} rights={rights} />
      {p.versions.map((v) => (
        <div key={v.id} className="rounded-lg border border-surface-container-high p-space-sm flex flex-col gap-space-xs">
          <div className="flex flex-wrap items-center gap-space-sm">
            <span className="font-label-lg text-label-lg">Version {v.version}</span>
            <span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm ${v.status === "active" ? tone("passed") : tone()}`}>{STATUS[v.status] ?? v.status}</span>
            <span className="font-body-sm text-body-sm text-on-surface-variant">{v.engine} · {v.method} · {v.model_repo}@{v.model_revision.slice(0, 10)} · {v.references.length} referenceklip</span>
          </div>
          <ul className="flex flex-wrap gap-1">{Object.entries(CHECK).map(([k, label]) => (
            <li key={k} className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm ${tone(v.checks[k]?.status)}`} title={(v.checks[k]?.problems ?? []).join("; ") || v.checks[k]?.reason || ""}>{label}: {v.checks[k]?.status ?? "afventer"}</li>))}</ul>
          {v.missing_checks.length > 0 && <p className="font-body-sm text-body-sm text-on-surface-variant">Mangler før godkendelse: {v.missing_checks.map((c) => CHECK[c] ?? c).join(", ")}</p>}
          <div className="flex flex-wrap gap-space-sm">
            <Button type="button" variant="tonal" icon="rule" disabled={busy} onClick={() => act(`/operator/voice-versions/${v.id}/checks/run`)}>Kør automatiske kontroller</Button>
            {["submit", "approve", "activate", "suspend", "retire", "reject"].map((a) => (
              <Button key={a} type="button" variant="ghost" disabled={busy} onClick={() => act(`/operator/voice-versions/${v.id}/${a}`)}>{{ submit: "Send til kontrol", approve: "Godkend", activate: "Aktivér", suspend: "Suspendér", retire: "Udfas", reject: "Afvis" }[a]}</Button>))}
          </div>
          <HumanCheck versionId={v.id} onDone={() => router.refresh()} />
          <TestClip versionId={v.id} />
        </div>
      ))}
      <ErrorBox error={err} />
      <details><summary className="font-label-md text-label-md cursor-pointer">Historik</summary>
        <ul className="font-body-sm text-body-sm">{p.history.map((h, i) => <li key={i}>{new Date(h.at).toLocaleString("da-DK")} · {h.action} {h.after ? JSON.stringify(h.after) : ""}</li>)}</ul>
      </details>
    </section>
  );
}

function References({ profileId }: { profileId: string }) {
  const [out, setOut] = useState<string>("");
  const [err, setErr] = useState<ApiError | null>(null);
  const upload = async (file: File | undefined) => {
    if (!file) return;
    setErr(null);
    const r = await fetch(`/api/backend/operator/voices/${profileId}/references?source_id=${encodeURIComponent(file.name)}`, {
      method: "POST", body: await file.arrayBuffer(), credentials: "same-origin", headers: { "x-requested-with": "dialogbot", "content-type": "audio/wav" } });
    const body = await r.json();
    if (!r.ok) setErr({ ...body, status: r.status }); else setOut(JSON.stringify(body));
  };
  return (
    <div className="flex flex-col gap-1">
      <Field label="Upload referenceklip (WAV, privat lager)"><input type="file" accept="audio/wav,.wav" onChange={(e) => upload(e.target.files?.[0])} /></Field>
      {out && <code className="font-body-sm text-body-sm break-all">{out}</code>}
      <ErrorBox error={err} />
    </div>
  );
}

function NewVersion({ p, rights }: { p: Profile; rights: Rights[] }) {
  const router = useRouter();
  const [f, setF] = useState({ model_repo: "CoRal-project/roest-v3-chatterbox-500m", model_revision: "", references: "", temperature: "0.7", cfg_weight: "0.5", rights: rights.map((r) => r.id) });
  const save = useSubmit(async () => {
    const refs = f.references.trim() ? f.references.trim().split("\n").map((l) => JSON.parse(l)) : [];
    await api(`/operator/voices/${p.id}/versions`, { method: "POST", body: JSON.stringify({ model_repo: f.model_repo.trim(), model_revision: f.model_revision.trim(),
      references: refs, settings: { temperature: Number(f.temperature), cfg_weight: Number(f.cfg_weight) }, rights_record_ids: f.rights }) });
    router.refresh();
  });
  return (
    <details className="rounded-lg bg-surface-container-low p-space-sm"><summary className="font-label-md text-label-md cursor-pointer">Ny uforanderlig version</summary>
      <div className="flex flex-col gap-space-sm mt-space-sm">
        <Field label="Model (Hugging Face-repo)"><Input value={f.model_repo} onChange={(e) => setF({ ...f, model_repo: e.target.value })} /></Field>
        <Field label="Modelrevision (40 tegn commit-hash)"><Input value={f.model_revision} onChange={(e) => setF({ ...f, model_revision: e.target.value })} /></Field>
        <Field label="Referenceklip (én JSON pr. linje fra upload)"><Textarea value={f.references} onChange={(e) => setF({ ...f, references: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-space-sm">
          <Field label="temperature"><Input type="number" step="0.05" value={f.temperature} onChange={(e) => setF({ ...f, temperature: e.target.value })} /></Field>
          <Field label="cfg_weight"><Input type="number" step="0.05" value={f.cfg_weight} onChange={(e) => setF({ ...f, cfg_weight: e.target.value })} /></Field>
        </div>
        <fieldset><legend className="font-label-md text-label-md">Rettighedsposter</legend>{rights.map((r) => (
          <label key={r.id} className="flex items-center gap-1 font-body-sm text-body-sm"><input type="checkbox" checked={f.rights.includes(r.id)} onChange={(e) => setF({ ...f, rights: e.target.checked ? [...f.rights, r.id] : f.rights.filter((x) => x !== r.id) })} />{r.kind}: {r.subject}</label>))}</fieldset>
        <div><Button type="button" onClick={() => save.run()} disabled={save.pending}>Opret version</Button></div>
        <ErrorBox error={save.error} />
      </div>
    </details>
  );
}

function HumanCheck({ versionId, onDone }: { versionId: string; onDone: () => void }) {
  const [f, setF] = useState({ name: "listening_test", passed: "true", evidence: "" });
  const save = useSubmit(async () => {
    await api(`/operator/voice-versions/${versionId}/checks/${f.name}`, { method: "POST", body: JSON.stringify({ passed: f.passed === "true", evidence: JSON.parse(f.evidence || "{}") }) });
    onDone();
  });
  return (
    <details><summary className="font-label-md text-label-md cursor-pointer">Registrér lyttetest / telefontest</summary>
      <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_2fr_auto] gap-space-sm items-end mt-space-xs">
        <Field label="Kontrol"><Select value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}><option value="listening_test">Lyttetest</option><option value="telephony_test">Telefontest</option></Select></Field>
        <Field label="Resultat"><Select value={f.passed} onChange={(e) => setF({ ...f, passed: e.target.value })}><option value="true">Bestået</option><option value="false">Ikke bestået</option></Select></Field>
        <Field label="Dokumentation (JSON)" hint='fx {"raters":3,"intelligibility":4.2,"naturalness":4.1} eller {"provider_call_id":"…"}'><Input value={f.evidence} onChange={(e) => setF({ ...f, evidence: e.target.value })} /></Field>
        <Button type="button" onClick={() => save.run()} disabled={save.pending}>Gem</Button>
      </div>
      <ErrorBox error={save.error} />
    </details>
  );
}

function TestClip({ versionId }: { versionId: string }) {
  const [text, setText] = useState("Jeg har en ledig tid onsdag den 28. oktober klokken halv elleve.");
  const [err, setErr] = useState<ApiError | null>(null);
  const [sim, setSim] = useState(false);
  const audio = useRef<HTMLAudioElement>(null);
  const play = async () => {
    setErr(null);
    try {
      const { blob, simulated } = await apiAudio(`/operator/voice-versions/${versionId}/synthesize`, { text });
      setSim(simulated);
      if (audio.current) { audio.current.src = URL.createObjectURL(blob); await audio.current.play().catch(() => undefined); }
    } catch (e) { setErr(e as ApiError); }
  };
  return (
    <div className="flex flex-wrap items-end gap-space-sm">
      <Field label="Testklip"><Input value={text} onChange={(e) => setText(e.target.value)} /></Field>
      <Button type="button" variant="tonal" icon="play_arrow" onClick={play}>Generér</Button>
      <audio ref={audio} controls className="h-8" />
      {sim && <span className="font-label-sm text-label-sm">Simuleret lyd</span>}
      <ErrorBox error={err} />
    </div>
  );
}

function NewProfile() {
  const router = useRouter();
  const [f, setF] = useState({ slug: "", display_name: "", gender: "unknown", dialect: "", dialect_basis: "", visibility: "platform", workspace_id: "" });
  const save = useSubmit(async () => {
    await api("/operator/voices", { method: "POST", body: JSON.stringify({ ...f, dialect: f.dialect || null, workspace_id: f.workspace_id || null }) });
    router.refresh();
  });
  return (
    <details className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm"><summary className="font-label-lg text-label-lg cursor-pointer">Ny stemmeprofil</summary>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-sm mt-space-sm">
        <Field label="Stabilt ID"><Input value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value })} placeholder="jysk-kvinde-35-45-a" /></Field>
        <Field label="Visningsnavn"><Input value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></Field>
        <Field label="Køn"><Select value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}><option value="unknown">Ukendt</option><option value="female">Kvinde</option><option value="male">Mand</option></Select></Field>
        <Field label="Dialekt (tom = ukendt)"><Input value={f.dialect} onChange={(e) => setF({ ...f, dialect: e.target.value })} placeholder="let østjysk" /></Field>
        <Field label="Begrundelse for kategorisering"><Textarea value={f.dialect_basis} onChange={(e) => setF({ ...f, dialect_basis: e.target.value })} /></Field>
        <Field label="Synlighed"><Select value={f.visibility} onChange={(e) => setF({ ...f, visibility: e.target.value })}><option value="platform">Platform</option><option value="workspace">Privat for ét arbejdsrum</option></Select></Field>
        {f.visibility === "workspace" && <Field label="Arbejdsrums-ID"><Input value={f.workspace_id} onChange={(e) => setF({ ...f, workspace_id: e.target.value })} /></Field>}
      </div>
      <div className="mt-space-sm"><Button type="button" onClick={() => save.run()} disabled={save.pending}>Opret</Button></div>
      <ErrorBox error={save.error} />
    </details>
  );
}
