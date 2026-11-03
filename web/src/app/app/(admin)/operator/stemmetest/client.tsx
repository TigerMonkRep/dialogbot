"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Select, Textarea, useSubmit } from "@/components/ui";

type Access = { status: "klar" | "mangler_adgang" | "ikke_replaybar"; missing: string[]; reason: string };
type Profile = { id: string; label: string; purpose: string; adapter: string | null; model: string | null; turn_owner: string; live: string; notes: string; capabilities: Record<string, string>; access: Access };
type Stat = { n: number; median: number | null; p95: number | null; uncertain: boolean };
type Measured = { cases: number; wer: number | null; errors: number; ref_words: number; entities: Record<string, { hits: number; total: number }>; first_final_s: Stat; final_after_audio_s: Stat; turn_end_after_audio_s: Stat };
type Row = { profile: string; label: string; model: string | null; turn_owner: string; access: Access; status: string; measured?: Measured; human_cases?: number; note?: string | null; by_group?: Record<string, Measured> };
type Case = { id: string; group: string; split: string; text: string; status: string; synthetic: boolean; note?: string | null; audio_rate?: number | null };
type Scenario = { id: string; title: string; script: string[]; expected_action: string; tool_fault?: string | null; status: string };
export type Overview = {
  testmode: boolean; honesty: string[]; profiles: Profile[]; workspaces: { id: string; name: string }[];
  manifest: { note: string; counts: { kort: number; med_lyd: number; tuning: number; final: number; scenarier: number }; cases: Case[]; scenarios: Scenario[] };
  summary: { final: Row[]; tuning: Row[] };
  browser_call: { status: string; reason: string };
};
type Run = {
  id: string; profile: string; actual_profile: string; mode: string; case_id: string | null; split: string | null; source: string; status: string;
  reference: string; transcript_raw: string; synthetic: boolean; error: string | null; created_at: string;
  wer: { errors: number; ref_words: number; wer: number | null } | null;
  entities: { by_type: Record<string, { hits: number; total: number }>; missed: { type: string; value: string }[] } | null;
  timing: Record<string, number | string | null> | null; turn_count: number | null; premature_split: boolean | null;
  requested_model: string | null; reported_model: string | null;
  turns?: { text: string; segments: string[]; late: string[]; closed_by: string }[]; sdk?: Record<string, string>; turn_owner?: string;
  events?: { kind: string; text: string; at: number; source: string }[]; events_total?: number; vocabulary?: { offered: number; used: number };
  price?: { audio_seconds: number; usd: number | null; note: string }; audio_rate?: number;
};

const pct = (x: number | null | undefined) => (x == null ? "–" : `${(x * 100).toFixed(1).replace(".", ",")} %`);
const sec = (x: number | null | undefined) => (x == null ? "–" : `${x.toFixed(2).replace(".", ",")} s`);
const GROUP_LABEL: Record<string, string> = {
  tal_beloeb: "Beløb og procent", tal_stor: "Store tal og årstal", tal_telefon: "Telefonnumre", tal_nummer: "Ordre- og kundenumre",
  adresse: "Adresser og postnumre", tal_tid: "Tid og dato", tal_enhed: "Mål og enheder", tal_rettelse: "Rettelser midt i tal",
  kombineret: "Tal og navne i samme sætning", stoej_tal: "Tal med baggrundsstøj", navne: "Navne", steder: "Steder",
};
const statText = (s: Stat) => (s.n === 0 ? "ikke målt" : `median ${sec(s.median)} · p95 ${sec(s.p95)} · n=${s.n}${s.uncertain ? " (usikker, få målinger)" : ""}`);

function Entities({ e }: { e: Record<string, { hits: number; total: number }> }) {
  const items = Object.entries(e);
  if (!items.length) return <span>ingen vigtige oplysninger i prøven</span>;
  return <span>{items.map(([k, v]) => `${k} ${v.hits}/${v.total}`).join(" · ")}</span>;
}

function RunCard({ r }: { r: Run }) {
  const [detail, setDetail] = useState<Run | null>(null);
  const [open, setOpen] = useState(false);
  const toggle = async () => {
    setOpen(!open);
    if (!detail) setDetail(await api<Run>(`/operator/stemmetest/runs/${r.id}`));
  };
  const d = detail ?? r;
  return (
    <li className="rounded-xl border-2 border-ink bg-surface-container-lowest p-space-sm flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-space-sm">
        <strong>Profil {r.profile}</strong>
        <span>{r.case_id ?? "egen optagelse"}</span>
        <span className="px-2 py-0.5 rounded-full bg-surface-container-high">{r.status === "ok" ? "Færdig" : r.status === "kører" ? "Kører …" : r.status === "mangler_adgang" ? "Mangler adgang" : "Fejl"}</span>
        <span className="text-on-surface-variant">{r.mode === "controlled" ? "kontrolleret STT-test" : "naturlig afslutning"}{r.synthetic ? " · syntetisk tale" : ""}</span>
        <button className="ml-auto underline" onClick={toggle}>{open ? "Skjul" : "Avanceret"}</button>
      </div>
      {r.error && <Alert kind="warn">{r.error}</Alert>}
      {r.status === "ok" && (
        <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-space-md gap-y-1 font-body-sm text-body-sm">
          <div><dt className="text-on-surface-variant">Forstod kunden</dt><dd>Ordfejl {pct(r.wer?.wer)} ({r.wer?.errors}/{r.wer?.ref_words}) · {r.entities && <Entities e={r.entities.by_type} />}</dd></div>
          <div><dt className="text-on-surface-variant">Svartid (STT, ikke samlet svar)</dt><dd>første tekst {sec(r.timing?.first_final_s as number)} · efter lydens slutning {sec(r.timing?.final_after_audio_s as number)}</dd></div>
          <div className="md:col-span-2"><dt className="text-on-surface-variant">Råt genkendt (ikke rettet)</dt><dd>{r.transcript_raw || "(ingen tekst)"}</dd></div>
          <div className="md:col-span-2"><dt className="text-on-surface-variant">Reference</dt><dd>{r.reference || "(tavshed)"}</dd></div>
          {r.entities && r.entities.missed.length > 0 && <div className="md:col-span-2"><dt className="text-on-surface-variant">Ramte ikke</dt><dd>{r.entities.missed.map((m) => `${m.type}: ${m.value}`).join(" · ")}</dd></div>}
          {r.premature_split && <div className="md:col-span-2"><Alert kind="warn">Udbyderens egen afslutning delte udtalelsen i {r.turn_count} taleture (for tidligt svar-risiko). Det er endpointing, ikke genkendelsesmodellen.</Alert></div>}
        </dl>
      )}
      {open && (
        <div className="rounded-lg bg-surface-container-low p-space-sm font-body-sm text-body-sm flex flex-col gap-1">
          <div><b>Modelnavn</b> anmodet: {d.requested_model ?? "–"} · rapporteret af udbyder: {d.reported_model ?? "ukendt"}</div>
          <div><b>Ansvarlig for slut på taletur</b> {d.turn_owner ?? "–"}</div>
          <div><b>SDK/transport</b> {d.sdk ? Object.entries(d.sdk).map(([k, v]) => `${k} ${v}`).join(" · ") : "–"}</div>
          <div><b>Lyd</b> {d.audio_rate ? `${d.audio_rate} Hz, 16-bit mono PCM` : "–"} · <b>Ordliste</b> {d.vocabulary ? `${d.vocabulary.used} af ${d.vocabulary.offered} brugt` : "–"} · <b>Pris</b> {d.price ? (d.price.usd == null ? d.price.note : `$${d.price.usd} (${d.price.note})`) : "–"}</div>
          <div><b>Taleture</b></div>
          <ol className="list-decimal ml-5">{(d.turns ?? []).map((t, i) => <li key={i}>{t.segments.join(" | ")}{t.late.length ? ` (sent: ${t.late.join(" | ")})` : ""} — lukket af {t.closed_by}</li>)}</ol>
          <div><b>Eventtidslinje</b> ({d.events?.length ?? 0} af {d.events_total ?? 0}; tid = sekunder siden sessionsstart)</div>
          <pre className="overflow-x-auto max-h-64 text-[12px]">{(d.events ?? []).map((e) => `${e.at.toFixed(2).padStart(6)}  ${e.kind.padEnd(14)} ${e.source === "provider" ? "" : `[${e.source}] `}${e.text}`).join("\n")}</pre>
        </div>
      )}
    </li>
  );
}

export function Stemmetest({ data }: { data: Overview }) {
  const ready = useMemo(() => data.manifest.cases.filter((c) => c.status === "klar"), [data]);
  const [ws, setWs] = useState("");
  const [caseId, setCaseId] = useState(ready[0]?.id ?? "");
  const [mode, setMode] = useState("controlled");
  const [picked, setPicked] = useState<string[]>(data.profiles.filter((p) => p.access.status === "klar").map((p) => p.id));
  const [runs, setRuns] = useState<Run[]>([]);
  const [summary, setSummary] = useState(data.summary);
  const [split, setSplit] = useState<"final" | "tuning">("final");
  const [upRef, setUpRef] = useState("");
  const [upProfile, setUpProfile] = useState(data.profiles.find((p) => p.access.status === "klar")?.id ?? "");
  const [upFile, setUpFile] = useState<File | null>(null);

  const refresh = useCallback(async () => {
    const [r, f, t] = await Promise.all([
      api<{ runs: Run[] }>("/operator/stemmetest/runs?limit=30"),
      api<{ rows: Row[] }>("/operator/stemmetest/summary?split=final&mode=controlled"),
      api<{ rows: Row[] }>("/operator/stemmetest/summary?split=tuning&mode=controlled"),
    ]);
    setRuns(r.runs);
    setSummary({ final: f.rows, tuning: t.rows });
  }, []);
  useEffect(() => { refresh().catch(() => {}); }, [refresh]);
  useEffect(() => {
    if (!runs.some((r) => r.status === "kører")) return;
    const t = setInterval(() => { refresh().catch(() => {}); }, 3000);
    return () => clearInterval(t);
  }, [runs, refresh]);

  const start = useSubmit(async () => {
    for (const p of picked) {
      await api("/operator/stemmetest/runs", { method: "POST", body: JSON.stringify({ profile: p, case: caseId, mode, workspace_id: ws || undefined }) });
    }
    await refresh();
  });
  const [batchInfo, setBatchInfo] = useState("");
  const batch = useSubmit(async () => {
    const r = await api<{ runs: number; profiles: string[] }>("/operator/stemmetest/batch", { method: "POST", body: JSON.stringify({ profiles: picked, cases: "alle", mode, workspace_id: ws || undefined }) });
    setBatchInfo(`${r.runs} kørsler er sat i gang (${r.profiles.join(", ") || "ingen profiler med adgang"}). De kører i realtid, én ad gangen pr. profil – regn med nogle minutter.`);
    await refresh();
  });
  const upload = useSubmit(async () => {
    if (!upFile) return;
    const fd = new FormData();
    fd.set("file", upFile); fd.set("profile", upProfile); fd.set("reference", upRef); fd.set("mode", mode);
    if (ws) fd.set("workspace_id", ws);
    const r = await fetch("/api/backend/operator/stemmetest/runs/upload", { method: "POST", body: fd, credentials: "same-origin", headers: { "x-requested-with": "dialogbot" } });
    if (!r.ok) throw { ...(await r.json().catch(() => ({ code: "http_error", message: r.statusText }))), status: r.status };
    await refresh();
  });
  const active = data.profiles.filter((p) => picked.includes(p.id)).map((p) => p.label).join(", ") || "ingen";
  const rows = summary[split];
  const groups = useMemo(() => Array.from(new Set(rows.flatMap((r) => Object.keys(r.by_group ?? {})))).sort(), [rows]);
  const wsName = data.workspaces.find((w) => w.id === ws)?.name ?? "ingen valgt (fælles testordliste)";

  return (
    <div className="flex flex-col gap-space-lg">
      <Alert kind="info" icon="science">
        <b>Testtilstand.</b> Virksomhed: {wsName} · Aktiv profil: {active} · Teststatus: {runs.some((r) => r.status === "kører") ? "kører" : "klar"}. Kundens opkald flyttes aldrig automatisk til en anden udbyder af denne side.
      </Alert>
      <ul className="font-body-sm text-body-sm text-on-surface-variant list-disc ml-5">{data.honesty.map((h) => <li key={h}>{h}</li>)}</ul>

      <section className="rounded-2xl bg-surface-container-lowest border-2 border-ink p-space-md flex flex-col gap-space-sm">
        <h2 className="font-title-md text-title-md font-bold">Kør samme lyd gennem flere profiler</h2>
        <div className="grid md:grid-cols-3 gap-space-sm">
          <Field label="Virksomhed"><Select value={ws} onChange={(e) => setWs(e.target.value)}><option value="">Fælles testordliste</option>{data.workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</Select></Field>
          <Field label="Testcase (kun med optagelse)" hint={`${data.manifest.counts.med_lyd} af ${data.manifest.counts.kort} har lyd`}><Select value={caseId} onChange={(e) => setCaseId(e.target.value)}>{ready.map((c) => <option key={c.id} value={c.id}>{c.id} · {c.text.slice(0, 50)}{c.synthetic ? " (syntetisk)" : ""}</option>)}</Select></Field>
          <Field label="Afslutning af taletur"><Select value={mode} onChange={(e) => setMode(e.target.value)}><option value="controlled">Kontrolleret: kun genkendelse</option><option value="natural">Udbyderens egen afslutning</option></Select></Field>
        </div>
        <fieldset className="flex flex-wrap gap-space-sm">
          {data.profiles.map((p) => {
            const can = p.access.status === "klar";
            return (
              <label key={p.id} className={`flex items-center gap-1 px-2 py-1 rounded-lg border-2 ${can ? "border-ink" : "border-line text-on-surface-variant"}`} title={p.access.reason}>
                <input type="checkbox" disabled={!can} checked={picked.includes(p.id)} onChange={(e) => setPicked(e.target.checked ? [...picked, p.id] : picked.filter((x) => x !== p.id))} />
                {p.label}{!can && <em className="ml-1">{p.access.status === "mangler_adgang" ? "Mangler adgang" : "Måles i live-opkald"}</em>}
              </label>
            );
          })}
        </fieldset>
        <div className="flex gap-space-sm items-center"><Button onClick={() => start.run()} disabled={start.pending || !picked.length || !caseId}>Kør test</Button>{mode === "controlled" && <span className="font-body-sm text-on-surface-variant">Kontrolleret STT-test – ikke dokumentation for en naturlig samtale.</span>}</div>
        <div className="flex gap-space-sm items-center flex-wrap"><Button variant="secondary" onClick={() => batch.run()} disabled={batch.pending || !picked.length}>Kør alle {data.manifest.counts.med_lyd} cases med lyd</Button><span className="font-body-sm text-on-surface-variant">Hele den brede prøve (tal, telefonnumre, adresser, tid, støj, navne) gennem de valgte profiler.</span></div>
        {batchInfo && <Alert kind="info">{batchInfo}</Alert>}
        <ErrorBox error={start.error} />
        <ErrorBox error={batch.error} />
      </section>

      <section className="rounded-2xl bg-surface-container-lowest border-2 border-ink p-space-md flex flex-col gap-space-sm">
        <div className="flex items-center gap-space-sm"><h2 className="font-title-md text-title-md font-bold">Resultater</h2>
          <Select className="max-w-48" value={split} onChange={(e) => setSplit(e.target.value as "final" | "tuning")}><option value="final">Afsluttende cases</option><option value="tuning">Tuningcases</option></Select></div>
        <div className="overflow-x-auto"><table className="w-full font-body-sm text-body-sm">
          <thead><tr className="text-left text-on-surface-variant"><th>Profil</th><th>Forstod kunden</th><th>Bookede korrekt</th><th>Afbrydelser</th><th>Svartid (STT)</th><th>Stemme</th><th>Pris</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.profile} className="align-top border-t border-line">
              <td className="py-1"><b>{r.label}</b><div className="text-on-surface-variant">{r.model}</div></td>
              {r.measured ? (<>
                <td>Ordfejl {pct(r.measured.wer)} ({r.measured.errors}/{r.measured.ref_words}) · {r.measured.cases} cases<div><Entities e={r.measured.entities} /></div>{r.note && <div className="text-on-surface-variant">{r.note}</div>}</td>
                <td className="text-on-surface-variant">ikke målt (kræver samtale)</td><td className="text-on-surface-variant">ikke målt (kræver samtale)</td>
                <td>{statText(r.measured.final_after_audio_s)}</td><td className="text-on-surface-variant">separat lyttetest</td><td className="text-on-surface-variant">pris ikke angivet</td>
              </>) : (<td colSpan={6} className="text-on-surface-variant">{r.status}{r.access.reason ? ` – ${r.access.reason}` : ""}</td>)}
            </tr>))}</tbody></table></div>
      </section>

      <section className="rounded-2xl bg-surface-container-lowest border-2 border-ink p-space-md flex flex-col gap-space-sm">
        <h2 className="font-title-md text-title-md font-bold">Pr. område</h2>
        <p className="font-body-sm text-on-surface-variant">Samme mål delt op pr. type prøve, så svagheder ikke forsvinder i ét samlet tal. Hver celle viser ordfejl og de vigtige oplysninger (tal, tider, navne) den ramte rigtigt, med antal cases. Sammenlign &quot;Tal med baggrundsstøj&quot; med de rene områder for at se, hvad støj koster. Syntetisk tale er lettere end ægte opkald.</p>
        <div className="overflow-x-auto"><table className="w-full font-body-sm text-body-sm">
          <thead><tr className="text-left text-on-surface-variant"><th>Område</th>{rows.filter((r) => r.by_group).map((r) => <th key={r.profile}>{r.label}</th>)}</tr></thead>
          <tbody>{groups.map((g) => (
            <tr key={g} className="align-top border-t border-line">
              <td className="py-1"><b>{GROUP_LABEL[g] ?? g}</b></td>
              {rows.filter((r) => r.by_group).map((r) => { const m = r.by_group?.[g]; return (
                <td key={r.profile}>{m ? (<>Ordfejl {pct(m.wer)} · {m.cases} cases<div><Entities e={m.entities} /></div></>) : <span className="text-on-surface-variant">ikke målt</span>}</td>); })}
            </tr>))}
            {!groups.length && <tr><td className="text-on-surface-variant py-1">Kør hele prøven for at se resultater pr. område.</td></tr>}
          </tbody></table></div>
      </section>

      <section className="rounded-2xl bg-surface-container-lowest border-2 border-ink p-space-md flex flex-col gap-space-sm">
        <h2 className="font-title-md text-title-md font-bold">Egen optagelse</h2>
        <p className="font-body-sm text-on-surface-variant">WAV (16-bit) afspilles i realtid; lyden gemmes ikke, kun resultatet.</p>
        <div className="grid md:grid-cols-3 gap-space-sm">
          <Field label="Profil"><Select value={upProfile} onChange={(e) => setUpProfile(e.target.value)}>{data.profiles.filter((p) => p.access.status === "klar").map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</Select></Field>
          <Field label="Fil"><input type="file" accept="audio/wav,.wav" onChange={(e) => setUpFile(e.target.files?.[0] ?? null)} /></Field>
          <Field label="Reference (ordene, der siges)"><Textarea value={upRef} onChange={(e) => setUpRef(e.target.value)} /></Field>
        </div>
        <div><Button variant="secondary" onClick={() => upload.run()} disabled={upload.pending || !upFile || !upProfile}>Kør optagelse</Button></div>
        <ErrorBox error={upload.error} />
      </section>

      <section className="flex flex-col gap-space-sm">
        <h2 className="font-title-md text-title-md font-bold">Seneste kørsler</h2>
        <ul className="flex flex-col gap-space-sm">{runs.map((r) => <RunCard key={r.id} r={r} />)}{!runs.length && <li className="text-on-surface-variant">Ingen kørsler endnu.</li>}</ul>
      </section>

      <section className="rounded-2xl bg-surface-container-lowest border-2 border-ink p-space-md flex flex-col gap-space-sm">
        <h2 className="font-title-md text-title-md font-bold">Browser og telefon (målt for sig)</h2>
        <Alert kind="warn">Browsersamtale: {data.browser_call.status === "ikke_bygget" ? "ikke bygget" : data.browser_call.status}. {data.browser_call.reason}</Alert>
        <p className="font-body-sm text-on-surface-variant">Telefon: D, E og F kan prøves som rigtige opkald gennem den eksisterende bro på staging; resultaterne her er alene genkendelse på afspillet lyd.</p>
      </section>

      <section className="rounded-2xl bg-surface-container-lowest border-2 border-ink p-space-md flex flex-col gap-space-sm">
        <h2 className="font-title-md text-title-md font-bold">Testgrundlag</h2>
        <p className="font-body-sm text-on-surface-variant">{data.manifest.counts.kort} korte cases ({data.manifest.counts.tuning} tuning, {data.manifest.counts.final} afsluttende), {data.manifest.counts.med_lyd} med lyd, {data.manifest.counts.scenarier} samtalescenarier der kræver et menneske, som svarer på agentens spørgsmål.</p>
        <details><summary className="cursor-pointer">Cases</summary><ul className="font-body-sm">{data.manifest.cases.map((c) => <li key={c.id}>{c.id} · {c.split} · {c.text || "(tavshed)"} — <em>{c.status === "klar" ? `lyd${c.synthetic ? " (syntetisk)" : ""}` : "mangler optagelse"}</em></li>)}</ul></details>
        <details><summary className="cursor-pointer">Scenarier</summary><ul className="font-body-sm">{data.manifest.scenarios.map((s) => <li key={s.id}>{s.id} · {s.title} → {s.expected_action}{s.tool_fault ? ` (fejl: ${s.tool_fault})` : ""}</li>)}</ul></details>
      </section>

      <details className="rounded-2xl bg-surface-container-lowest border-2 border-ink p-space-md">
        <summary className="cursor-pointer font-title-md font-bold">Avanceret: profiler og kapabiliteter</summary>
        <div className="flex flex-col gap-space-md mt-space-sm">{data.profiles.map((p) => (
          <div key={p.id} className="font-body-sm">
            <b>{p.label}</b> — {p.purpose}
            <div className="text-on-surface-variant">Adgang: {p.access.status === "klar" ? "klar" : p.access.reason} · slut på taletur ejes af: {p.turn_owner} · live: {p.live || "–"}</div>
            {p.notes && <div>{p.notes}</div>}
            <table className="w-full mt-1"><tbody>{Object.entries(p.capabilities).map(([k, v]) => <tr key={k} className="border-t border-line"><td className="pr-2 text-on-surface-variant">{k}</td><td>{v}</td></tr>)}</tbody></table>
          </div>))}</div>
      </details>
    </div>
  );
}
