"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, apiAudio, type ApiError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, Textarea, useSubmit } from "@/components/ui";
import { useT } from "@/i18n/client";

export type Voice = {
  id: string; slug: string; display_name: string; gender: "female" | "male" | "unknown"; dialect: string | null; dialect_basis: string;
  age_description: string | null; timbre: string | null; origin: "dataset_speaker" | "designed" | "customer_recorded" | "hired_speaker";
  description: string; source: string; visibility: "platform" | "workspace"; sample_text: string;
  active_version: { id: string; version: number; engine: string; method: string; model_revision: string; pilot: boolean;
    listening_test: string; telephony_test: string; simulated: boolean } | null;
};
export type StandardVoice = { key: string; name: string; gender: "female" | "male"; image: string; description: string; sample: boolean };
export type VoicesData = {
  items: Voice[]; standard_voices: StandardVoice[]; engine: "available" | "simulated" | "not_configured"; preview_max_chars: number;
  assignments: { workspace_default: string | null; phone_numbers: { id: string; e164: string; label: string; voice_profile_id: string | null }[];
    campaigns: { id: string; name: string; status: string; voice_profile_id: string | null }[] };
  settings: { version: number; default_profile_id: string | null; standard_voice: string | null; standard_default: string; fallback: "provider_voice" | "transfer"; pronunciations: { term: string; say: string }[]; pronunciation_version: number };
};

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
  const t = useT("settings");
  if (engine === "available") return null;
  return engine === "simulated"
    ? <Alert kind="warn" icon="science">{t("voices.engineSimulated")}</Alert>
    : <Alert kind="info" icon="info">{t("voices.engineMissing")}</Alert>;
}

function Steps({ standardVoice, heard, testCall }: { standardVoice: boolean; heard: string; testCall: string }) {
  // A ready-made standard voice has no sample to play: steps 2–3 are covered by the test call.
  const t = useT("settings");
  const viaCall = t("voices.steps.viaCall");
  const items: [string, boolean, string, string?][] = [
    [t("voices.steps.choose"), true, t("voices.steps.chooseHint")],
    [t("voices.steps.listen"), standardVoice || STEP_OK(heard), standardVoice ? viaCall : t("voices.steps.listenHint")],
    [t("voices.steps.greeting"), standardVoice || STEP_OK(heard), standardVoice ? viaCall : t("voices.steps.greetingHint")],
    [t("voices.steps.testCall"), STEP_OK(testCall), t("voices.steps.testCallHint"), "/app/setup#checks"],
  ];
  return (
    <ol className="grid grid-cols-1 md:grid-cols-4 gap-2" aria-label={t("voices.steps.aria")}>
      {items.map(([label, done, hint, href], i) => (
        <li key={label} className={`rounded-2xl p-2 flex flex-col gap-1 ${done ? "bg-success-soft text-success" : "bg-paper border-2 border-ink"}`}>
          <span className="flex items-center gap-1 eyebrow"><Icon name={done ? "check_circle" : "radio_button_unchecked"} size={16} />{t("voices.steps.step", { n: i + 1 })}</span>
          <span className="text-label-lg">{label}</span>
          {(!done || hint === viaCall) && <span className="text-body-sm">{href ? <Link className="underline" href={href}>{hint}</Link> : hint}</span>}
        </li>
      ))}
    </ol>
  );
}

/** Saves one change to the voice settings on top of the latest saved version, so an earlier save on the page
 *  (or a double click) never turns into a "changed by someone else" conflict. */
async function saveSettings(wsId: string, patch: Partial<VoicesData["settings"]>) {
  const fresh = (await api<VoicesData>(`/workspaces/${wsId}/voices`)).settings;
  await api(`/workspaces/${wsId}/voices/settings`, { method: "PUT", body: JSON.stringify({ ...fresh, expected_version: fresh.version, ...patch }) });
}

/** Ready-made Danish voices. Work today without Dialogbot's own speech engine. The provider is never shown. */
function StandardVoices({ wsId, data, canManage }: { wsId: string; data: VoicesData; canManage: boolean }) {
  const router = useRouter();
  const t = useT("settings");
  const player = usePlayer();
  const current = data.settings.standard_voice ?? data.settings.standard_default;
  const pick = useSubmit(async (key: string) => {
    await saveSettings(wsId, { standard_voice: key });
    router.refresh();
  });
  return (
    <section aria-labelledby="std-h" className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-3">
      <div>
        <h2 id="std-h" className="font-display text-headline-sm text-ink">{t("voices.standard.title")}</h2>
        <p className="text-body-sm text-ink-soft max-w-3xl">{t("voices.standard.intro")}</p>
      </div>
      <ErrorBox error={pick.error ?? player.error} />
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {data.standard_voices.map((v) => {
          const active = current === v.key;
          const playing = player.state?.key === `std-${v.key}`;
          return (
            <li key={v.key} className={`rounded-2xl p-3 flex items-center gap-3 border-2 transition-colors ${active ? "border-ink bg-panel" : "border-line"}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={v.image} alt="" width={96} height={96} className="w-24 h-24 shrink-0 rounded-[1.25rem]" />
              <div className="flex flex-col gap-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-display text-headline-sm text-ink">{v.name}</h3>
                  <span className="text-label-sm text-ink-soft">{t(`voices.gender.${v.gender}`)} · {t("voices.standard.danish")}</span>
                  {active && <span className="px-2 py-0.5 rounded-full bg-ink text-paper text-label-sm flex items-center gap-1"><Icon name="check" size={14} />{t("voices.standard.inUse")}</span>}
                </div>
                <p className="text-body-sm text-ink-soft">{v.description}</p>
                <div className="flex flex-wrap gap-2">
                  {v.sample && (playing
                    ? <Button type="button" variant="tonal" icon={player.state?.phase === "loading" ? "hourglass_top" : "stop"} onClick={player.stop} aria-label={t("voices.standard.stopAria", { name: v.name })}>{player.state?.phase === "loading" ? t("voices.standard.loading") : t("voices.standard.stop")}</Button>
                    : <Button type="button" variant="tonal" icon="play_arrow" onClick={() => player.play(`std-${v.key}`, `/workspaces/${wsId}/voices/standard/${v.key}/sample`, {})} aria-label={t("voices.standard.hearAria", { name: v.name })}>{t("voices.standard.hear", { name: v.name })}</Button>)}
                  {canManage && !active && <Button type="button" variant="tonal" disabled={pick.pending} onClick={() => pick.run(v.key)}>{t("voices.standard.choose", { name: v.name })}</Button>}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Meta({ v }: { v: Voice }) {
  const t = useT("settings");
  const bits = [t(`voices.gender.${v.gender}`), v.dialect ?? t("voices.meta.noDialect"), v.age_description ?? t("voices.meta.ageUnknown")];
  if (v.timbre) bits.push(v.timbre);
  return <p className="text-body-sm text-ink-soft">{bits.join(" · ")}</p>;
}

export function VoiceLibrary({ wsId, data, canManage, greeting, steps }: {
  wsId: string; data: VoicesData; canManage: boolean; greeting: string; steps: { heard: string; testCall: string };
}) {
  const router = useRouter();
  const t = useT("settings");
  const player = usePlayer();
  const [filter, setFilter] = useState({ gender: "", dialect: "" });
  const [own, setOwn] = useState({ voice: data.settings.default_profile_id ?? data.items[0]?.id ?? "", text: "" });
  const notAssessed = t("voices.library.notAssessed");
  const dialects = Array.from(new Set(data.items.map((v) => v.dialect ?? notAssessed)));
  const shown = data.items.filter((v) => (!filter.gender || v.gender === filter.gender) && (!filter.dialect || (v.dialect ?? notAssessed) === filter.dialect));
  const choose = useSubmit(async (profileId: string) => {
    await saveSettings(wsId, { default_profile_id: profileId });
    router.refresh();
  });
  const playing = (key: string) => player.state?.key === key;
  return (
    <div className="flex flex-col gap-4">
      <EngineNotice engine={data.engine} />
      <Steps standardVoice={!data.settings.default_profile_id} heard={steps.heard} testCall={steps.testCall} />
      <StandardVoices wsId={wsId} data={data} canManage={canManage} />
      {player.state?.simulated && <p role="status" className="text-body-sm text-ink-soft">{t("voices.library.playingSimulated")}</p>}
      <ErrorBox error={player.error ?? choose.error} />

      <section aria-labelledby="lib-h" className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 id="lib-h" className="font-display text-headline-sm text-ink">{t("voices.library.title")}</h2>
          {data.items.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <Field label={t("voices.library.gender")}><Select value={filter.gender} onChange={(e) => setFilter({ ...filter, gender: e.target.value })}><option value="">{t("voices.library.all")}</option><option value="female">{t("voices.library.female")}</option><option value="male">{t("voices.library.male")}</option><option value="unknown">{t("voices.library.unknown")}</option></Select></Field>
              <Field label={t("voices.library.dialect")}><Select value={filter.dialect} onChange={(e) => setFilter({ ...filter, dialect: e.target.value })}><option value="">{t("voices.library.all")}</option>{dialects.map((d) => <option key={d}>{d}</option>)}</Select></Field>
            </div>
          )}
        </div>
        {data.items.length === 0 ? (
          <p className="text-body-md text-ink-soft">{t("voices.library.empty")}</p>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {shown.map((v) => {
              const isDefault = data.settings.default_profile_id === v.id;
              return (
                <li key={v.id} className={`rounded-xl p-3 flex flex-col gap-1 border ${isDefault ? "border-ink bg-panel" : "border-line"}`}>
                  <div className="flex items-center gap-2">
                    {v.origin === "designed"
                      // eslint-disable-next-line @next/next/no-img-element
                      ? <img src={`/voices/designed/${v.slug}.svg`} alt="" width={56} height={56} className="w-14 h-14 rounded-xl shrink-0" />
                      : <Icon name="record_voice_over" className="text-ink" />}
                    <h3 className="text-label-lg text-ink">{v.display_name}</h3>
                    {isDefault && <span className="ml-auto px-2 py-0.5 rounded-full bg-ink text-paper text-label-sm">{t("voices.library.default")}</span>}
                  </div>
                  <Meta v={v} />
                  {v.description && <p className="text-body-sm">{v.description}</p>}
                  <div className="flex flex-wrap gap-1">
                    <span className="px-2 py-0.5 rounded-full bg-success-soft text-success text-label-sm">{t(`voices.origin.${v.origin}`)}</span>
                    {v.active_version?.pilot && <span className="px-2 py-0.5 rounded-full bg-accent-soft text-accent-deep text-label-sm">{t("voices.library.pilot")}</span>}
                    {v.active_version && v.active_version.listening_test !== "passed" && <span className="px-2 py-0.5 rounded-full bg-line text-label-sm">{t("voices.library.listeningPending")}</span>}
                    {v.active_version?.simulated && <span className="px-2 py-0.5 rounded-full bg-line text-label-sm">{t("voices.library.simulated")}</span>}
                  </div>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {playing(`s-${v.id}`)
                      ? <Button type="button" variant="tonal" icon="stop" onClick={player.stop}>{player.state?.phase === "loading" ? t("voices.library.generatingStop") : t("voices.library.stop")}</Button>
                      : <Button type="button" variant="tonal" icon="play_arrow" onClick={() => player.play(`s-${v.id}`, `/workspaces/${wsId}/voices/${v.id}/preview`, {})} aria-label={t("voices.library.playAria", { name: v.display_name })}>{t("voices.library.listen")}</Button>}
                    {canManage && !isDefault && <Button type="button" icon="check" onClick={() => choose.run(v.id)} disabled={choose.pending}>{t("voices.library.makeDefault")}</Button>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {data.items.length > 0 && (
        <section aria-labelledby="try-h" className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
          <h2 id="try-h" className="font-display text-headline-sm text-ink">{t("voices.library.tryTitle")}</h2>
          <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-2">
            <Field label={t("voices.library.voice")}><Select value={own.voice} onChange={(e) => setOwn({ ...own, voice: e.target.value })}>{data.items.map((v) => <option key={v.id} value={v.id}>{v.display_name}</option>)}</Select></Field>
            <Field label={t("voices.library.text", { n: data.preview_max_chars })} hint={`${own.text.length}/${data.preview_max_chars}`}>
              <Textarea value={own.text} maxLength={data.preview_max_chars} onChange={(e) => setOwn({ ...own, text: e.target.value })} placeholder={t("voices.library.textPlaceholder")} />
            </Field>
          </div>
          <div className="flex flex-wrap gap-2">
            {playing("own")
              ? <Button type="button" variant="tonal" icon="stop" onClick={player.stop}>{player.state?.phase === "loading" ? t("voices.library.generatingStop") : t("voices.library.stop")}</Button>
              : <Button type="button" icon="graphic_eq" disabled={!own.voice || !own.text.trim()} onClick={() => player.play("own", `/workspaces/${wsId}/voices/${own.voice}/preview`, { text: own.text })}>{t("voices.library.generate")}</Button>}
            {greeting && data.settings.default_profile_id && (playing("greet")
              ? <Button type="button" variant="tonal" icon="stop" onClick={player.stop}>{t("voices.library.stop")}</Button>
              : <Button type="button" variant="tonal" icon="waving_hand" onClick={() => player.play("greet", `/workspaces/${wsId}/voices/${data.settings.default_profile_id}/preview`, { text: greeting.replaceAll("{virksomhed}", "").slice(0, data.preview_max_chars) })}>{t("voices.library.hearGreeting")}</Button>)}
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
  const t = useT("settings");
  const [msg, setMsg] = useState<string | null>(null);
  const save = useSubmit(async (kind: "phone-numbers" | "campaigns", id: string, value: string) => {
    await api(`/workspaces/${wsId}/voices/assignments/${kind}/${id}`, { method: "PUT", body: JSON.stringify({ voice_profile_id: value || null }) });
    setMsg(t("voices.assignments.saved"));
    router.refresh();
  });
  const fallback = useSubmit(async (value: string) => {
    await saveSettings(wsId, { fallback: value as VoicesData["settings"]["fallback"] });
    router.refresh();
  });
  const opts = [<option key="" value="">{t("voices.assignments.workspaceDefault")}</option>, ...data.items.map((v) => <option key={v.id} value={v.id}>{v.display_name}</option>)];
  return (
    <section aria-labelledby="asg-h" className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
      <h2 id="asg-h" className="font-display text-headline-sm text-ink">{t("voices.assignments.title")}</h2>
      {msg && <Alert kind="ok">{msg}</Alert>}
      {data.assignments.phone_numbers.length === 0 && data.assignments.campaigns.length === 0 && <p className="text-body-md text-ink-soft">{t("voices.assignments.empty")}</p>}
      {data.assignments.phone_numbers.map((n) => (
        <Field key={n.id} label={`${t("voices.assignments.phone", { number: n.e164 })}${n.label ? ` (${n.label})` : ""}`}>
          <Select defaultValue={n.voice_profile_id ?? ""} onChange={(e) => save.run("phone-numbers", n.id, e.target.value)}>{opts}</Select>
        </Field>
      ))}
      {data.assignments.campaigns.map((c) => (
        <Field key={c.id} label={t("voices.assignments.campaign", { name: c.name })} hint={t("voices.assignments.campaignHint")}>
          <Select defaultValue={c.voice_profile_id ?? ""} onChange={(e) => save.run("campaigns", c.id, e.target.value)}>{opts}</Select>
        </Field>
      ))}
      <Field label={t("voices.assignments.fallback")} hint={t("voices.assignments.fallbackHint")}>
        <Select value={data.settings.fallback} onChange={(e) => fallback.run(e.target.value)}>
          <option value="provider_voice">{t("voices.assignments.fallbackProvider")}</option>
          <option value="transfer">{t("voices.assignments.fallbackTransfer")}</option>
        </Select>
      </Field>
      <ErrorBox error={save.error ?? fallback.error} />
    </section>
  );
}

function Pronunciations({ wsId, data }: { wsId: string; data: VoicesData }) {
  const router = useRouter();
  const t = useT("settings");
  const [rows, setRows] = useState(data.settings.pronunciations.length ? data.settings.pronunciations : [{ term: "", say: "" }]);
  const [saved, setSaved] = useState(false);
  const save = useSubmit(async () => {
    await saveSettings(wsId, { pronunciations: rows.filter((r) => r.term.trim() && r.say.trim()) });
    setSaved(true);
    router.refresh();
  });
  const set = (i: number, k: "term" | "say", v: string) => { setSaved(false); setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r))); };
  return (
    <section aria-labelledby="pron-h" className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
      <h2 id="pron-h" className="font-display text-headline-sm text-ink">{t("voices.pronunciations.title")}</h2>
      <p className="text-body-sm text-ink-soft">{t("voices.pronunciations.intro", { version: data.settings.pronunciation_version })}</p>
      {saved && <Alert kind="ok">{t("voices.pronunciations.saved")}</Alert>}
      {rows.map((r, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end">
          <Field label={i === 0 ? t("voices.pronunciations.written") : ""}><Input aria-label={t("voices.pronunciations.wordAria", { n: i + 1 })} value={r.term} onChange={(e) => set(i, "term", e.target.value)} placeholder={t("voices.pronunciations.termPlaceholder")} /></Field>
          <Field label={i === 0 ? t("voices.pronunciations.spoken") : ""}><Input aria-label={t("voices.pronunciations.sayAria", { n: i + 1 })} value={r.say} onChange={(e) => set(i, "say", e.target.value)} placeholder={t("voices.pronunciations.sayPlaceholder")} /></Field>
          <Button type="button" variant="ghost" icon="delete" aria-label={t("voices.pronunciations.removeAria", { n: i + 1 })} onClick={() => setRows(rows.filter((_, j) => j !== i))} />
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="tonal" icon="add" onClick={() => setRows([...rows, { term: "", say: "" }])}>{t("voices.pronunciations.add")}</Button>
        <Button type="button" icon="save" onClick={() => save.run()} disabled={save.pending}>{t("voices.pronunciations.save")}</Button>
      </div>
      <ErrorBox error={save.error} />
    </section>
  );
}
