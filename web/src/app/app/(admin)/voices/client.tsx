"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, apiAudio, type ApiError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, Textarea, useSubmit } from "@/components/ui";

export type Voice = {
  id: string; slug: string; display_name: string; gender: "female" | "male" | "unknown"; dialect: string | null; dialect_basis: string;
  age_description: string | null; timbre: string | null; origin: "dataset_speaker" | "designed" | "customer_recorded" | "hired_speaker";
  description: string; source: string; visibility: "platform" | "workspace"; sample_text: string;
  active_version: { id: string; version: number; engine: string; method: string; model_revision: string; pilot: boolean;
    listening_test: string; telephony_test: string; simulated: boolean } | null;
};
export type StandardVoice = { key: string; name: string; gender: "female" | "male"; image: string; description: string };
export type VoicesData = {
  items: Voice[]; standard_voices: StandardVoice[]; engine: "available" | "simulated" | "not_configured"; preview_max_chars: number;
  assignments: { workspace_default: string | null; phone_numbers: { id: string; e164: string; label: string; voice_profile_id: string | null }[];
    campaigns: { id: string; name: string; status: string; voice_profile_id: string | null }[] };
  settings: { version: number; default_profile_id: string | null; standard_voice: string | null; standard_default: string; fallback: "provider_voice" | "transfer"; pronunciations: { term: string; say: string }[]; pronunciation_version: number };
};

const GENDER: Record<string, string> = { female: "Kvinde", male: "Mand", unknown: "Køn ikke angivet" };
const STEP_OK = (s: string) => s === "passed";

/** One shared audio player: playing a new sample stops the previous one; Stop cancels a pending request. */
function usePlayer() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const ctrl = useRef<AbortController | null>(null);
  const [state, setState] = useState<{ key: string; phase: "loading" | "playing"; simulated?: boolean } | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const stop = () => {
    ctrl.current?.abort();
    audio.current?.pause();
    setState(null);
  };
  const play = async (key: string, path: string, body: unknown) => {
    stop();
    setError(null);
    const c = new AbortController();
    ctrl.current = c;
    setState({ key, phase: "loading" });
    try {
      const { blob, simulated } = await apiAudio(path, body, c.signal);
      const el = audio.current ?? new Audio();
      audio.current = el;
      el.src = URL.createObjectURL(blob);
      el.onended = () => setState(null);
      setState({ key, phase: "playing", simulated });
      await el.play().catch(() => undefined);
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") setError(e as ApiError);
      setState(null);
    }
  };
  useEffect(() => () => stop(), []);
  return { state, error, play, stop };
}

function EngineNotice({ engine }: { engine: VoicesData["engine"] }) {
  if (engine === "available") return null;
  return engine === "simulated"
    ? <Alert kind="warn" icon="science">Testmiljø: talemotoren er simuleret. Prøverne er en tone, ikke tale, og tæller ikke som afprøvet stemme.</Alert>
    : <Alert kind="info" icon="info">Vælg den danske stemme, jeres kunder skal høre i telefonen. Flere stemmer kommer løbende.</Alert>;
}

function Steps({ hasDefault, heard, testCall }: { hasDefault: boolean; heard: string; testCall: string }) {
  const items: [string, boolean, string, string?][] = [
    ["Vælg stemme", hasDefault, "Vælg en standardstemme nedenfor."],
    ["Lyt til prøven", STEP_OK(heard), "Afspil standardprøven for den valgte stemme."],
    ["Afprøv jeres velkomst", STEP_OK(heard), "Hør velkomsten fra Reception med stemmen."],
    ["Gennemfør et prøveopkald", STEP_OK(testCall), "Ring til jeres nummer. Et gemt valg er ikke en bestået telefontest.", "/app/setup#checks"],
  ];
  return (
    <ol className="grid grid-cols-1 md:grid-cols-4 gap-space-sm" aria-label="Opsætning af stemme">
      {items.map(([label, done, hint, href], i) => (
        <li key={label} className={`rounded-xl p-space-sm flex flex-col gap-1 ${done ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-lowest shadow-sm"}`}>
          <span className="font-label-sm text-label-sm uppercase tracking-wider flex items-center gap-1"><Icon name={done ? "check_circle" : "radio_button_unchecked"} size={16} />Trin {i + 1}</span>
          <span className="font-label-lg text-label-lg">{label}</span>
          {!done && <span className="font-body-sm text-body-sm">{href ? <Link className="underline" href={href}>{hint}</Link> : hint}</span>}
        </li>
      ))}
    </ol>
  );
}

/** Ready-made Danish voices (Azure via Vapi). Work today without Dialogbot's own speech engine. */
function StandardVoices({ wsId, data, canManage }: { wsId: string; data: VoicesData; canManage: boolean }) {
  const router = useRouter();
  const current = data.settings.standard_voice ?? data.settings.standard_default;
  const pick = useSubmit(async (key: string) => {
    await api(`/workspaces/${wsId}/voices/settings`, { method: "PUT", body: JSON.stringify({ ...data.settings, expected_version: data.settings.version, standard_voice: key }) });
    router.refresh();
  });
  return (
    <section aria-labelledby="std-h" className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
      <div>
        <h2 id="std-h" className="font-headline-sm text-headline-sm text-primary">Vælg telefonstemme</h2>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">Danske stemmer, der virker med det samme. Valget gælder alle jeres telefonnumre og kampagner, og I kan altid skifte. I hører stemmen, når I ringer til jeres nummer.</p>
      </div>
      <ErrorBox error={pick.error} />
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-space-md">
        {data.standard_voices.map((v) => {
          const active = current === v.key;
          return (
            <li key={v.key} className={`rounded-2xl p-space-md flex items-center gap-space-md border-2 transition-colors ${active ? "border-primary bg-surface-container-low" : "border-surface-container-high"}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={v.image} alt="" width={96} height={96} className="w-24 h-24 shrink-0 rounded-[1.25rem]" />
              <div className="flex flex-col gap-space-xs min-w-0">
                <div className="flex flex-wrap items-center gap-space-sm">
                  <h3 className="font-headline-sm text-headline-sm text-primary">{v.name}</h3>
                  <span className="font-label-sm text-label-sm text-on-surface-variant">{GENDER[v.gender]} · Dansk</span>
                  {active && <span className="px-2 py-0.5 rounded-full bg-primary text-on-primary font-label-sm text-label-sm flex items-center gap-1"><Icon name="check" size={14} />Bruges nu</span>}
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant">{v.description}</p>
                {canManage && !active && <div><Button type="button" variant="tonal" disabled={pick.pending} onClick={() => pick.run(v.key)}>Vælg {v.name}</Button></div>}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const ORIGIN: Record<Voice["origin"], string> = {
  designed: "Designet stemme", dataset_speaker: "Professionel oplæser", customer_recorded: "Jeres egen stemme",
  hired_speaker: "Indtaler med aftale",
};

function Meta({ v }: { v: Voice }) {
  const bits = [GENDER[v.gender], v.dialect ?? "Dialekt ikke vurderet", v.age_description ?? "Alder ukendt"];
  if (v.timbre) bits.push(v.timbre);
  return <p className="font-body-sm text-body-sm text-on-surface-variant">{bits.join(" · ")}</p>;
}

export function VoiceLibrary({ wsId, data, canManage, greeting, steps }: {
  wsId: string; data: VoicesData; canManage: boolean; greeting: string; steps: { heard: string; testCall: string };
}) {
  const router = useRouter();
  const player = usePlayer();
  const [filter, setFilter] = useState({ gender: "", dialect: "" });
  const [own, setOwn] = useState({ voice: data.settings.default_profile_id ?? data.items[0]?.id ?? "", text: "" });
  const dialects = Array.from(new Set(data.items.map((v) => v.dialect ?? "Ikke vurderet")));
  const shown = data.items.filter((v) => (!filter.gender || v.gender === filter.gender) && (!filter.dialect || (v.dialect ?? "Ikke vurderet") === filter.dialect));
  const choose = useSubmit(async (profileId: string) => {
    await api(`/workspaces/${wsId}/voices/settings`, { method: "PUT", body: JSON.stringify({ ...data.settings, expected_version: data.settings.version, default_profile_id: profileId }) });
    router.refresh();
  });
  const playing = (key: string) => player.state?.key === key;
  return (
    <div className="flex flex-col gap-space-lg">
      <EngineNotice engine={data.engine} />
      <Steps hasDefault={!!(data.settings.default_profile_id || data.settings.standard_voice)} heard={steps.heard} testCall={steps.testCall} />
      <StandardVoices wsId={wsId} data={data} canManage={canManage} />
      {player.state?.simulated && <p role="status" className="font-body-sm text-body-sm text-on-surface-variant">Afspiller simuleret lyd (testmotor).</p>}
      <ErrorBox error={player.error ?? choose.error} />

      <section aria-labelledby="lib-h" className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
        <div className="flex flex-wrap items-end justify-between gap-space-sm">
          <h2 id="lib-h" className="font-headline-sm text-headline-sm text-primary">Dialogbot-stemmer</h2>
          {data.items.length > 0 && (
            <div className="flex flex-wrap gap-space-sm">
              <Field label="Køn"><Select value={filter.gender} onChange={(e) => setFilter({ ...filter, gender: e.target.value })}><option value="">Alle</option><option value="female">Kvinde</option><option value="male">Mand</option><option value="unknown">Ikke angivet</option></Select></Field>
              <Field label="Dialekt"><Select value={filter.dialect} onChange={(e) => setFilter({ ...filter, dialect: e.target.value })}><option value="">Alle</option>{dialects.map((d) => <option key={d}>{d}</option>)}</Select></Field>
            </div>
          )}
        </div>
        {data.items.length === 0 ? (
          <p className="font-body-md text-body-md text-on-surface-variant">Flere danske stemmer – også med dialekt – er på vej. De bliver vist her, når de har bestået vores kontrol af rettigheder, lydkvalitet og telefonlyd. Indtil da bruger telefonen den stemme, I har valgt ovenfor.</p>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-space-sm">
            {shown.map((v) => {
              const isDefault = data.settings.default_profile_id === v.id;
              return (
                <li key={v.id} className={`rounded-xl p-space-md flex flex-col gap-space-xs border ${isDefault ? "border-primary bg-surface-container-low" : "border-surface-container-high"}`}>
                  <div className="flex items-center gap-space-sm">
                    <Icon name="record_voice_over" className="text-primary" />
                    <h3 className="font-label-lg text-label-lg text-primary">{v.display_name}</h3>
                    {isDefault && <span className="ml-auto px-2 py-0.5 rounded-full bg-primary text-on-primary font-label-sm text-label-sm">Standard</span>}
                  </div>
                  <Meta v={v} />
                  {v.description && <p className="font-body-sm text-body-sm">{v.description}</p>}
                  <div className="flex flex-wrap gap-1">
                    <span className="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm">{ORIGIN[v.origin]}</span>
                    {v.active_version?.pilot && <span className="px-2 py-0.5 rounded-full bg-tertiary-fixed text-on-tertiary-fixed font-label-sm text-label-sm">Pilot i jeres arbejdsrum</span>}
                    {v.active_version && v.active_version.listening_test !== "passed" && <span className="px-2 py-0.5 rounded-full bg-surface-container-high font-label-sm text-label-sm">Lyttetest afventer</span>}
                    {v.active_version?.simulated && <span className="px-2 py-0.5 rounded-full bg-surface-container-high font-label-sm text-label-sm">Simuleret</span>}
                  </div>
                  <div className="flex flex-wrap gap-space-sm mt-space-xs">
                    {playing(`s-${v.id}`)
                      ? <Button type="button" variant="tonal" icon="stop" onClick={player.stop}>{player.state?.phase === "loading" ? "Genererer … stop" : "Stop"}</Button>
                      : <Button type="button" variant="tonal" icon="play_arrow" onClick={() => player.play(`s-${v.id}`, `/workspaces/${wsId}/voices/${v.id}/preview`, {})} aria-label={`Afspil prøve med ${v.display_name}`}>Lyt</Button>}
                    {canManage && !isDefault && <Button type="button" icon="check" onClick={() => choose.run(v.id)} disabled={choose.pending}>Vælg som standard</Button>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {data.items.length > 0 && (
        <section aria-labelledby="try-h" className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
          <h2 id="try-h" className="font-headline-sm text-headline-sm text-primary">Afprøv med jeres egen tekst</h2>
          <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-space-sm">
            <Field label="Stemme"><Select value={own.voice} onChange={(e) => setOwn({ ...own, voice: e.target.value })}>{data.items.map((v) => <option key={v.id} value={v.id}>{v.display_name}</option>)}</Select></Field>
            <Field label={`Tekst (højst ${data.preview_max_chars} tegn)`} hint={`${own.text.length}/${data.preview_max_chars}`}>
              <Textarea value={own.text} maxLength={data.preview_max_chars} onChange={(e) => setOwn({ ...own, text: e.target.value })} placeholder="Fx: Vi har en ledig tid onsdag den 28. oktober klokken 10.30." />
            </Field>
          </div>
          <div className="flex flex-wrap gap-space-sm">
            {playing("own")
              ? <Button type="button" variant="tonal" icon="stop" onClick={player.stop}>{player.state?.phase === "loading" ? "Genererer … stop" : "Stop"}</Button>
              : <Button type="button" icon="graphic_eq" disabled={!own.voice || !own.text.trim()} onClick={() => player.play("own", `/workspaces/${wsId}/voices/${own.voice}/preview`, { text: own.text })}>Generér og afspil</Button>}
            {greeting && data.settings.default_profile_id && (playing("greet")
              ? <Button type="button" variant="tonal" icon="stop" onClick={player.stop}>Stop</Button>
              : <Button type="button" variant="tonal" icon="waving_hand" onClick={() => player.play("greet", `/workspaces/${wsId}/voices/${data.settings.default_profile_id}/preview`, { text: greeting.replaceAll("{virksomhed}", "").slice(0, data.preview_max_chars) })}>Hør jeres velkomst</Button>)}
          </div>
        </section>
      )}

      {canManage && data.items.length > 0 && <Assignments wsId={wsId} data={data} />}
      {canManage && <Pronunciations wsId={wsId} data={data} />}
    </div>
  );
}

function Assignments({ wsId, data }: { wsId: string; data: VoicesData }) {
  const router = useRouter();
  const [msg, setMsg] = useState<string | null>(null);
  const save = useSubmit(async (kind: "phone-numbers" | "campaigns", id: string, value: string) => {
    await api(`/workspaces/${wsId}/voices/assignments/${kind}/${id}`, { method: "PUT", body: JSON.stringify({ voice_profile_id: value || null }) });
    setMsg("Gemt. Nye samtaler bruger stemmen; igangværende samtaler beholder deres stemme.");
    router.refresh();
  });
  const fallback = useSubmit(async (value: string) => {
    await api(`/workspaces/${wsId}/voices/settings`, { method: "PUT", body: JSON.stringify({ ...data.settings, expected_version: data.settings.version, fallback: value }) });
    router.refresh();
  });
  const opts = [<option key="" value="">Arbejdsrummets standard</option>, ...data.items.map((v) => <option key={v.id} value={v.id}>{v.display_name}</option>)];
  return (
    <section aria-labelledby="asg-h" className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
      <h2 id="asg-h" className="font-headline-sm text-headline-sm text-primary">Assistenter og kampagner</h2>
      {msg && <Alert kind="ok">{msg}</Alert>}
      {data.assignments.phone_numbers.length === 0 && data.assignments.campaigns.length === 0 && <p className="font-body-md text-body-md text-on-surface-variant">Ingen telefonnumre eller kampagner endnu. De bruger standardstemmen, når de oprettes.</p>}
      {data.assignments.phone_numbers.map((n) => (
        <Field key={n.id} label={`Telefonassistent ${n.e164}${n.label ? ` (${n.label})` : ""}`}>
          <Select defaultValue={n.voice_profile_id ?? ""} onChange={(e) => save.run("phone-numbers", n.id, e.target.value)}>{opts}</Select>
        </Field>
      ))}
      {data.assignments.campaigns.map((c) => (
        <Field key={c.id} label={`Kampagne: ${c.name}`} hint="Et stemmeskift starter aldrig opkald og ændrer ikke prisen.">
          <Select defaultValue={c.voice_profile_id ?? ""} onChange={(e) => save.run("campaigns", c.id, e.target.value)}>{opts}</Select>
        </Field>
      ))}
      <Field label="Hvis stemmen fejler under et opkald" hint="Reservestemmen er den stemme, der er valgt under Indstillinger → Telefoni.">
        <Select value={data.settings.fallback} onChange={(e) => fallback.run(e.target.value)}>
          <option value="provider_voice">Skift til den godkendte reservestemme</option>
          <option value="transfer">Ingen reservestemme – opkaldet går videre efter telefoniudbyderens fejlhåndtering</option>
        </Select>
      </Field>
      <ErrorBox error={save.error ?? fallback.error} />
    </section>
  );
}

function Pronunciations({ wsId, data }: { wsId: string; data: VoicesData }) {
  const router = useRouter();
  const [rows, setRows] = useState(data.settings.pronunciations.length ? data.settings.pronunciations : [{ term: "", say: "" }]);
  const [saved, setSaved] = useState(false);
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/voices/settings`, { method: "PUT", body: JSON.stringify({ ...data.settings, expected_version: data.settings.version, pronunciations: rows.filter((r) => r.term.trim() && r.say.trim()) }) });
    setSaved(true);
    router.refresh();
  });
  const set = (i: number, k: "term" | "say", v: string) => { setSaved(false); setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r))); };
  return (
    <section aria-labelledby="pron-h" className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
      <h2 id="pron-h" className="font-headline-sm text-headline-sm text-primary">Udtaleordbog</h2>
      <p className="font-body-sm text-body-sm text-on-surface-variant">Skriv hvordan navne skal udtales, fx firmanavne eller stednavne. Gælder hele ord. Version {data.settings.pronunciation_version}. En ændring kræver et nyt prøveopkald.</p>
      {saved && <Alert kind="ok">Gemt.</Alert>}
      {rows.map((r, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-space-sm items-end">
          <Field label={i === 0 ? "Skrives" : ""}><Input aria-label={`Ord ${i + 1}`} value={r.term} onChange={(e) => set(i, "term", e.target.value)} placeholder="ApS" /></Field>
          <Field label={i === 0 ? "Udtales" : ""}><Input aria-label={`Udtale ${i + 1}`} value={r.say} onChange={(e) => set(i, "say", e.target.value)} placeholder="a p s" /></Field>
          <Button type="button" variant="ghost" icon="delete" aria-label={`Fjern række ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))} />
        </div>
      ))}
      <div className="flex gap-space-sm">
        <Button type="button" variant="tonal" icon="add" onClick={() => setRows([...rows, { term: "", say: "" }])}>Tilføj ord</Button>
        <Button type="button" icon="save" onClick={() => save.run()} disabled={save.pending}>Gem udtaleordbog</Button>
      </div>
      <ErrorBox error={save.error} />
    </section>
  );
}
