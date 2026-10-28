"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Part } from "@/components/setup-parts";
import { Icon, inputCls } from "@/components/ui";
import { api, type ApiError } from "@/lib/client";
import { cardsFromGoals, goalsFromCards, hoursText, originOf, parseHours, parseZones, zonesText, type Cards, type WeeklyRange } from "@/lib/setup";

export type Profile = { version: number; legal_name: string; description: string; website_url: string | null; manual_setup: boolean; cvr: string | null; address_line: string | null; postal_code: string | null; city: string | null; country: string; timezone: string; phone: string | null };
export type Goals = { version: number; product_intent: string; guidance_mode: string; inbound_phone: boolean; webchat: boolean; callback: boolean; booking: boolean; conversation_goals: string[] };
export type Languages = { version: number; interface_language: string; default_conversation_language: string; enabled_conversation_languages: string[]; report_language: string };
type Version = { id: string; status: string; title: string; content: Record<string, unknown>; edit_version: number };
export type Fact = { id: string; kind: string; approved_version: Version | null; open_draft: Version | null };
type Created = { kind: string; title: string; item_id: string; version_id: string };
type ImportState = { status: "running" | "done" | "failed"; error: string | null; created_items: Created[]; profile_suggestion: Partial<Record<"description" | "cvr" | "phone" | "address_line" | "postal_code" | "city" | "legal_name", string>> };
type Tag = { key: string; label: string; ok: boolean; versionId?: string };

const KIND_LABEL: Record<string, string> = { opening_hours: "Åbningstider", coverage_area: "Kører i", service: "Ydelse", fact: "Fakta", known_answer: "Svar", offer: "Tilbud", unknown_answer: "Må ikke" };
const OK_KINDS = new Set(["opening_hours", "coverage_area", "fact"]);
const PROFILE_TAG: Record<string, string> = { legal_name: "Navn", cvr: "CVR", phone: "Telefon", description: "Hvad I laver", address_line: "Adresse" };
const LANGS: [string, string][] = [["da", "Dansk"], ["en", "Engelsk"], ["de", "Tysk"]];
const labelCls = "text-[13px] font-semibold text-ink";

type Save = "idle" | "saving" | "saved" | "error";

/** Trin 1 – Virksomhed. One page, three parts, saved as you type. */
export function Step1({ wsId, canEdit, canApprove, aiReady, cvrReady, profile, goals, languages, facts }: { wsId: string; canEdit: boolean; canApprove: boolean; aiReady: boolean; cvrReady: boolean; profile: Profile; goals: Goals; languages: Languages; facts: Fact[] }) {
  const router = useRouter();
  const hoursItem = facts.find((f) => f.kind === "opening_hours");
  const zonesItem = facts.find((f) => f.kind === "coverage_area");
  const pick = (f?: Fact) => f?.approved_version ?? f?.open_draft ?? null;

  const [p, setP] = useState(profile);
  const [cards, setCards] = useState<Cards>(cardsFromGoals(goals));
  const [langs, setLangs] = useState<string[]>(languages.enabled_conversation_languages);
  const [hours, setHours] = useState(hoursText(pick(hoursItem)?.content.weekly as WeeklyRange[] | undefined));
  const [zones, setZones] = useState(zonesText(pick(zonesItem)?.content.zones as string[] | undefined));
  const [save, setSave] = useState<Save>("idle");
  const [problem, setProblem] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);

  // Versions move on after every save; keep the latest in refs so a quick second edit never sends an old one.
  const ver = useRef({ profile: profile.version, goals: goals.version, languages: languages.version });
  const items = useRef<{ hours?: Fact; zones?: Fact }>({ hours: hoursItem, zones: zonesItem });
  const latest = useRef({ p, cards, langs, hours, zones });
  latest.current = { p, cards, langs, hours, zones };
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const pending = useRef(0);
  const dirty = useRef(new Set<string>());

  const run = useCallback(async (fn: () => Promise<void>) => {
    pending.current += 1; setSave("saving"); setProblem(null);
    try { await fn(); pending.current -= 1; if (pending.current === 0 && dirty.current.size === 0) setSave("saved"); }
    catch (e) {
      pending.current -= 1; setSave("error");
      const err = e as ApiError;
      setProblem(err.code === "version_conflict" ? "Siden er ændret et andet sted. Genindlæs den for at se det nyeste." : err.message ?? "Kunne ikke gemme. Prøv igen.");
    }
  }, []);

  const saveProfile = useCallback(() => run(async () => {
    const x = latest.current.p;
    if (!x.legal_name.trim()) return;
    const next = await api<Profile>(`/workspaces/${wsId}/profile`, { method: "PUT", body: JSON.stringify({ ...x, expected_version: ver.current.profile, website_url: x.website_url?.trim() || null, manual_setup: !x.website_url?.trim() }) });
    ver.current.profile = next.version;
  }), [run, wsId]);

  const saveGoals = useCallback(() => run(async () => {
    const g = goalsFromCards(latest.current.cards);
    const next = await api<Goals>(`/workspaces/${wsId}/goals`, { method: "PUT", body: JSON.stringify({ ...g, guidance_mode: goals.guidance_mode, conversation_goals: goals.conversation_goals, expected_version: ver.current.goals }) });
    ver.current.goals = next.version;
  }), [run, wsId, goals.guidance_mode, goals.conversation_goals]);

  const saveLangs = useCallback(() => run(async () => {
    const enabled = latest.current.langs;
    const next = await api<Languages>(`/workspaces/${wsId}/languages`, { method: "PUT", body: JSON.stringify({ interface_language: "da", default_conversation_language: "da", report_language: "da", enabled_conversation_languages: enabled, expected_version: ver.current.languages }) });
    ver.current.languages = next.version;
  }), [run, wsId]);

  /** A fact (hours, area) is saved as a new draft or an edit of the open draft, and approved straight away by someone who may. */
  const saveFact = useCallback((slot: "hours" | "zones", kind: string, title: string, content: Record<string, unknown>) => run(async () => {
    const cur = items.current[slot];
    let versionId: string;
    if (!cur) {
      const it = await api<Fact>(`/workspaces/${wsId}/knowledge/items`, { method: "POST", body: JSON.stringify({ kind, title, content }) });
      items.current[slot] = it; versionId = it.open_draft!.id;
    } else if (cur.open_draft) {
      const v = await api<Version>(`/workspaces/${wsId}/knowledge/versions/${cur.open_draft.id}`, { method: "PUT", body: JSON.stringify({ title, content, expected_edit_version: cur.open_draft.edit_version }) });
      items.current[slot] = { ...cur, open_draft: v }; versionId = v.id;
    } else {
      const v = await api<Version>(`/workspaces/${wsId}/knowledge/items/${cur.id}/drafts`, { method: "POST", body: JSON.stringify({ title, content }) });
      items.current[slot] = { ...cur, open_draft: v }; versionId = v.id;
    }
    if (canApprove) {
      const v = await api<Version>(`/workspaces/${wsId}/knowledge/versions/${versionId}/approve`, { method: "POST", body: "{}" });
      const base = items.current[slot]!;
      items.current[slot] = { ...base, approved_version: v, open_draft: null };
    }
  }), [run, wsId, canApprove]);

  /** Save one group now (also used when the owner presses Videre before the pause has run out). */
  const exec = useCallback(async (group: string) => {
    if (group === "profile") await saveProfile();
    if (group === "goals") await saveGoals();
    if (group === "langs") await saveLangs();
    if (group === "hours") {
      const w = parseHours(latest.current.hours);
      if (!latest.current.hours.trim()) { setHint(null); return; }
      if (!w) { setHint("Skriv fx «Man–fre 07–16» eller «Man–fre 07–16; lør 09–12». Det gemmes, så snart det kan læses."); return; }
      setHint(null); await saveFact("hours", "opening_hours", "Åbningstider", { weekly: w });
    }
    if (group === "zones") { const z = parseZones(latest.current.zones); if (z.length) await saveFact("zones", "coverage_area", "Kørselsområde", { zones: z }); }
  }, [saveProfile, saveGoals, saveLangs, saveFact]);
  /** Short pause after the last keystroke, then save that group. */
  const later = (group: "profile" | "goals" | "langs" | "hours" | "zones", ms = 900) => {
    clearTimeout(timers.current[group]);
    dirty.current.add(group);
    setSave("saving");
    timers.current[group] = setTimeout(() => {
      dirty.current.delete(group);
      // If nothing could be saved (e.g. hours that cannot be read yet), the status must not stay on «Gemmer …».
      void exec(group).then(() => { if (pending.current === 0 && dirty.current.size === 0) setSave((cur) => (cur === "saving" ? "idle" : cur)); });
    }, ms);
  };
  const flush = async () => {
    for (const g of [...dirty.current]) { clearTimeout(timers.current[g]); dirty.current.delete(g); await exec(g); }
  };
  useEffect(() => () => { Object.values(timers.current).forEach(clearTimeout); }, []);

  const field = (k: keyof Profile) => (e: React.ChangeEvent<HTMLInputElement>) => { setP((cur) => ({ ...cur, [k]: e.target.value })); later("profile"); };

  // --- categories follow "hvad I laver" (no search field): the first time there is a description and no category yet ---
  const catDone = useRef(false);
  const deriveCategory = useCallback(async () => {
    if (catDone.current || !latest.current.p.description.trim()) return;
    catDone.current = true;
    try {
      const have = await api<unknown[]>(`/workspaces/${wsId}/categories`);
      if (have.length) return;
      const sugg = (await api<{ items: { slug: string; label: string }[] }>(`/workspaces/${wsId}/categories/suggested`)).items;
      const text = latest.current.p.description.toLowerCase();
      const hit = sugg.find((s) => s.label.toLowerCase().split(/[\s&,]+/).some((w) => w.length >= 5 && text.includes(w.slice(0, 5))));
      const label = hit?.label ?? latest.current.p.description.split(/[,.]| og /)[0].trim().slice(0, 60);
      if (label) await api(`/workspaces/${wsId}/categories`, { method: "POST", body: JSON.stringify({ label, slug: hit?.slug ?? null, is_primary: true }) });
    } catch { /* a category is never the reason a save fails */ }
  }, [wsId]);

  // --- A: read the website ---
  const [site, setSite] = useState<{ busy: boolean; error: string | null; tags: Tag[]; approved: boolean } | null>(null);
  const fetchSite = async () => {
    const url = (p.website_url ?? "").trim();
    if (!url) return;
    setSite({ busy: true, error: null, tags: [], approved: false });
    try {
      let imp = await api<ImportState>(`/workspaces/${wsId}/knowledge/import`, { method: "POST", body: JSON.stringify({ url }) });
      for (let i = 0; i < 60 && imp.status === "running"; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        imp = (await api<{ import: ImportState }>(`/workspaces/${wsId}/knowledge/imports/latest`)).import;
      }
      if (imp.status === "failed") throw { message: imp.error ?? "Hjemmesiden kunne ikke læses." };
      if (imp.status === "running") throw { message: "Hjemmesiden tager lang tid at læse. Prøv igen om lidt." };
      // Fill only empty fields: what the owner already wrote is never overwritten.
      const sug = imp.profile_suggestion ?? {};
      const fill: Partial<Profile> = {};
      const tags: Tag[] = [];
      for (const k of ["legal_name", "cvr", "phone", "description", "address_line"] as const) {
        const v = sug[k];
        if (!v) continue;
        tags.push({ key: `p-${k}`, label: `${PROFILE_TAG[k]}: ${v.length > 48 ? `${v.slice(0, 46)}…` : v}`, ok: true });
        if (!String((latest.current.p as Record<string, unknown>)[k] ?? "").trim() && k !== "legal_name") (fill as Record<string, string>)[k] = v;
        if (k === "legal_name" && !latest.current.p.legal_name.trim()) fill.legal_name = v;
      }
      for (const c of imp.created_items ?? []) tags.push({ key: c.version_id, label: `${KIND_LABEL[c.kind] ?? c.kind}: ${c.title}`, ok: OK_KINDS.has(c.kind), versionId: c.version_id });
      if (Object.keys(fill).length) { setP((cur) => ({ ...cur, ...fill })); later("profile", 300); }
      setSite({ busy: false, error: null, tags, approved: false });
      // Hours and area from the site become the field text (as drafts until approved).
      const list = await api<{ items: Fact[] }>(`/workspaces/${wsId}/knowledge/items?limit=200`);
      const h = list.items.find((i) => i.kind === "opening_hours"), z = list.items.find((i) => i.kind === "coverage_area");
      if (h && !latest.current.hours.trim()) { items.current.hours = h; setHours(hoursText(pick(h)?.content.weekly as WeeklyRange[] | undefined)); }
      if (z && !latest.current.zones.trim()) { items.current.zones = z; setZones(zonesText(pick(z)?.content.zones as string[] | undefined)); }
      void deriveCategory();
    } catch (e) {
      setSite({ busy: false, error: (e as ApiError).message ?? "Kunne ikke hente fra hjemmesiden.", tags: [], approved: false });
    }
  };
  const approveAll = async () => {
    if (!site) return;
    setSite({ ...site, busy: true });
    try {
      for (const t of site.tags) if (t.versionId && !t.ok) await api(`/workspaces/${wsId}/knowledge/versions/${t.versionId}/approve`, { method: "POST", body: "{}" }).catch(() => undefined);
      for (const t of site.tags) if (t.versionId && t.ok) await api(`/workspaces/${wsId}/knowledge/versions/${t.versionId}/approve`, { method: "POST", body: "{}" }).catch(() => undefined);
      setSite((s) => s && { ...s, busy: false, approved: true, tags: s.tags.map((t) => ({ ...t, ok: true })) });
    } catch (e) { setSite((s) => s && { ...s, busy: false, error: (e as ApiError).message }); }
  };
  const yellow = site?.tags.filter((t) => !t.ok).length ?? 0;
  const [cvrNote, setCvrNote] = useState<string | null>(null);
  const cvrLookup = async () => {
    const n = (p.cvr ?? "").replace(/\D/g, "");
    if (n.length !== 8 || !cvrReady) return;
    try {
      const r = await api<{ legal_name: string; address_line: string | null; postal_code: string | null; city: string | null }>(`/workspaces/${wsId}/cvr/${n}`);
      setP((cur) => ({ ...cur, address_line: cur.address_line || r.address_line, postal_code: cur.postal_code || r.postal_code, city: cur.city || r.city }));
      setCvrNote(`CVR ${n}: ${r.legal_name}`); later("profile", 300);
    } catch { /* CVR is a help, not a requirement */ }
  };
  useEffect(() => { if (cvrReady && /^\d{8}$/.test((profile.cvr ?? "").replace(/\s/g, "")) && !profile.address_line) void cvrLookup(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (k: keyof Cards) => { setCards((c) => ({ ...c, [k]: !c[k] })); later("goals", 400); };
  const toggleLang = (code: string) => { setLangs((cur) => { const next = cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code]; return next.includes("da") ? next : ["da", ...next]; }); later("langs", 400); };
  const ready = p.legal_name.trim() && (p.phone ?? "").trim() && p.description.trim();
  const next = cards.booking ? 2 : 3;
  const [going, setGoing] = useState(false);

  return (
    <div className="flex flex-col gap-6">
      {!canEdit && <p role="status" className="rounded-xl bg-highlight px-4 py-3 text-[14px] text-ink">Din rolle (læser) kan se, men ikke redigere.</p>}
      <Part letter="A" title="Hent det fra hjemmesiden" hint={aiReady ? "Dialogbot læser siden og foreslår navn, hvad I laver, åbningstider og priser." : "Adressen gemmes. Forslag fra hjemmesiden kræver, at AI er slået til."}>
        <div className="flex flex-col sm:flex-row gap-2">
          <input aria-label="Hjemmesidens adresse" className={`${inputCls} flex-1`} placeholder="firma.dk" inputMode="url" autoCapitalize="none" value={p.website_url ?? ""} onChange={field("website_url")} disabled={!canEdit} />
          {aiReady && canEdit && <button type="button" onClick={fetchSite} disabled={site?.busy || !(p.website_url ?? "").trim()} className="min-h-[46px] px-5 rounded-xl bg-ink text-paper font-semibold disabled:opacity-60 inline-flex items-center justify-center gap-1.5">{site?.busy && !site.tags.length ? "Læser siden …" : <>Hent<Icon name="arrow_forward" size={16} /></>}</button>}
        </div>
        {site?.error && <p role="alert" className="text-[14px] text-danger">{site.error}</p>}
        {site && site.tags.length > 0 && (
          <div className="rounded-2xl border-[1.5px] border-ink bg-panel p-4 flex flex-col gap-3" aria-live="polite">
            <span className="eyebrow">Fundet på {originOf(p.website_url)?.replace(/^https?:\/\//, "") ?? "siden"} · godkend eller ret</span>
            <ul className="flex flex-wrap gap-2">
              {site.tags.map((t) => <li key={t.key} className={`px-3 py-1.5 rounded-full text-[13px] font-semibold border-[1.5px] ${t.ok ? "bg-success-soft text-success border-success-soft" : "bg-highlight text-ink border-ink"}`}>{t.ok ? "✓ " : "? "}{t.label}</li>)}
            </ul>
            <div className="flex flex-wrap gap-2">
              {canApprove && !site.approved && site.tags.some((t) => t.versionId) && <button type="button" onClick={approveAll} disabled={site.busy} className="min-h-[44px] px-4 rounded-xl bg-paper border-2 border-ink font-semibold hover:bg-panel-deep">Godkend alle {site.tags.filter((t) => t.versionId).length}</button>}
              {yellow > 0 && !site.approved && <Link href="/app/viden?tab=k05" className="inline-flex items-center min-h-[44px] px-4 rounded-xl bg-paper border-2 border-ink font-semibold hover:bg-panel-deep">Ret det gule</Link>}
              {site.approved && <span className="inline-flex items-center min-h-[44px] text-[14px] text-success font-semibold">Alt er godkendt og bruges nu af Dialogbot.</span>}
            </div>
          </div>
        )}
      </Part>

      <Part letter="B" title="Om jer" hint="Det, Dialogbot siger først – og det, den bruger til at svare rigtigt.">
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="flex flex-col gap-1.5"><span className={labelCls}>Navn (som den siger det)</span><input className={inputCls} value={p.legal_name} onChange={field("legal_name")} disabled={!canEdit} autoComplete="organization" /></label>
          <label className="flex flex-col gap-1.5"><span className={labelCls}>Telefonnummer, kunderne ringer til</span><input className={inputCls} value={p.phone ?? ""} onChange={field("phone")} disabled={!canEdit} inputMode="tel" autoComplete="tel" placeholder="+45 12 34 56 78" /></label>
        </div>
        <label className="flex flex-col gap-1.5"><span className={labelCls}>Hvad I laver – én sætning</span><input className={inputCls} value={p.description} maxLength={400} onChange={(e) => { field("description")(e); catDone.current = false; }} onBlur={() => void deriveCategory()} disabled={!canEdit} placeholder="Fx Vinduer, døre og terrasser i Aarhus og omegn" /></label>
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="flex flex-col gap-1.5"><span className={labelCls}>Åbningstider</span><input className={inputCls} value={hours} onChange={(e) => { setHours(e.target.value); later("hours"); }} disabled={!canEdit} placeholder="Man–fre 07–16" aria-describedby="hours-hint" /></label>
          <label className="flex flex-col gap-1.5"><span className={labelCls}>Hvor I kører</span><input className={inputCls} value={zones} onChange={(e) => { setZones(e.target.value); later("zones"); }} disabled={!canEdit} placeholder="Aarhus Kommune + 30 km" /></label>
        </div>
        <p id="hours-hint" className={`text-[13px] ${hint ? "text-danger" : "text-muted"}`} role={hint ? "alert" : undefined}>{hint ?? (canApprove ? "Åbningstider og område bruges af Dialogbot, så snart de er gemt." : "Dine ændringer gemmes som kladder, som en administrator godkender.")}</p>
        <details className="rounded-xl border-[1.5px] border-ink px-4 py-2">
          <summary className="cursor-pointer min-h-[36px] flex items-center text-[14px] font-semibold text-ink">CVR og adresse (valgfrit)</summary>
          <div className="grid sm:grid-cols-2 gap-4 pt-3 pb-2">
            <label className="flex flex-col gap-1.5"><span className={labelCls}>CVR</span><input className={inputCls} value={p.cvr ?? ""} onChange={field("cvr")} onBlur={() => void cvrLookup()} disabled={!canEdit} inputMode="numeric" /></label>
            <label className="flex flex-col gap-1.5"><span className={labelCls}>Adresse</span><input className={inputCls} value={p.address_line ?? ""} onChange={field("address_line")} disabled={!canEdit} autoComplete="street-address" /></label>
            <label className="flex flex-col gap-1.5"><span className={labelCls}>Postnummer</span><input className={inputCls} value={p.postal_code ?? ""} onChange={field("postal_code")} disabled={!canEdit} inputMode="numeric" /></label>
            <label className="flex flex-col gap-1.5"><span className={labelCls}>By</span><input className={inputCls} value={p.city ?? ""} onChange={field("city")} disabled={!canEdit} /></label>
          </div>
          {cvrNote && <p className="text-[13px] text-muted pb-2">Slået op: {cvrNote}</p>}
        </details>
      </Part>

      <Part letter="C" title="Hvad skal den gøre for jer?" hint="Vælg det, der passer. Det bestemmer, hvad trin 2 og 3 spørger om.">
        <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {([["phone", "Tage telefonen", "når I ikke kan – eller altid"], ["booking", "Booke aftaler", "direkte i jeres kalender"], ["web", "Svare på hjemmesiden", "webchat – én kodelinje"], ["outbound", "Ringe kunder op", "kampagner · 4 kr. pr. opkald ekskl. moms"]] as [keyof Cards, string, string][]).map(([k, title, sub]) => (
            <li key={k}>
              <label className={`flex items-start gap-3 rounded-2xl border-2 border-ink p-4 min-h-[76px] h-full cursor-pointer ${cards[k] ? "bg-highlight" : "bg-paper hover:bg-panel"}`}>
                <input type="checkbox" className="mt-1 w-5 h-5 accent-ink shrink-0" checked={cards[k]} onChange={() => toggle(k)} disabled={!canEdit} />
                <span className="flex flex-col"><span className="font-display font-bold text-[17px] text-ink">{title}</span><span className="text-[13px] text-ink-soft">{sub}</span></span>
              </label>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Sprog">
          <span className={labelCls}>Den taler</span>
          {LANGS.map(([c, l]) => {
            const on = langs.includes(c);
            return <button key={c} type="button" aria-pressed={on} disabled={!canEdit || c === "da"} onClick={() => toggleLang(c)} className={`min-h-[44px] px-4 rounded-full border-2 border-ink text-[14px] font-semibold ${on ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`}>{on ? l : `+ ${l}`}</button>;
          })}
          <span className="text-[13px] text-muted">Rapporter og denne side er altid på dansk.</span>
        </div>
      </Part>

      <div className="fixed sm:static inset-x-0 bottom-0 z-20 bg-paper sm:bg-transparent border-t-2 sm:border-0 border-ink px-4 py-3 sm:p-0 pb-safe flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3">
        <p className="text-[13px] text-muted" role="status" aria-live="polite">
          {save === "saving" ? "Gemmer …" : save === "saved" ? "Gemt" : save === "error" ? "" : "Gemmes løbende"} · du kan altid komme tilbage hertil
          {!ready && <span className="block">Udfyld navn, telefonnummer og hvad I laver for at gå videre.</span>}
          {problem && <span className="block text-danger" role="alert">{problem} {problem.startsWith("Siden er ændret") && <button type="button" className="underline" onClick={() => router.refresh()}>Genindlæs</button>}</span>}
        </p>
        <button type="button" disabled={!ready || going} onClick={async () => {
          setGoing(true); await flush();
          if (pending.current > 0) await new Promise((r) => setTimeout(r, 400));
          router.push(`/opsaetning/${next}`);
        }} className={`inline-flex items-center justify-center gap-2 min-h-[52px] px-6 rounded-xl font-semibold text-[16px] ${ready ? "bg-accent text-white hover:bg-accent-deep" : "bg-line text-muted"} disabled:opacity-70`}>
          {next === 2 ? "Videre til trin 2: kalender & systemer" : "Videre til trin 3: test & tænd"}<Icon name="arrow_forward" size={18} />
        </button>
      </div>
    </div>
  );
}

/** First visit: no workspace yet. The name creates it; the rest of the page opens straight after. */
export function CreateWorkspace({ verified, defaultIntent, referralLink }: { verified: boolean; defaultIntent: string; referralLink: string | null }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const go = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const ws = await api<{ id: string }>("/workspaces", { method: "POST", body: JSON.stringify({ name: name.trim(), product_intent: defaultIntent, referral_code: null, referral_link: referralLink }) });
      await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: ws.id }) });
      router.refresh();
    } catch (err) { setError((err as ApiError).message ?? "Kunne ikke oprette. Prøv igen."); setBusy(false); }
  };
  return (
    <form onSubmit={go} className="rounded-[20px] bg-paper border-2 border-ink p-5 md:p-6 flex flex-col gap-4 max-w-[640px]">
      {!verified && <p role="alert" className="rounded-xl bg-highlight px-4 py-3 text-[14px] text-ink">Bekræft din e-mail først. <Link className="underline font-semibold" href="/verify-email">Gå til bekræftelse</Link></p>}
      {referralLink && <p className="flex items-center gap-2 text-[14px] text-ink-soft"><Icon name="loyalty" size={18} />Du kom via en ambassadørs link – velkomstrabatten følger med.</p>}
      <label className="flex flex-col gap-1.5"><span className={labelCls}>Navn (som den siger det)</span>
        <input required minLength={2} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Fx Nørgaard Tømrer" autoComplete="organization" /></label>
      {error && <p role="alert" className="text-[14px] text-danger">{error}</p>}
      <button disabled={busy || !verified || name.trim().length < 2} className="min-h-[52px] px-6 rounded-xl bg-accent text-white font-semibold text-[16px] hover:bg-accent-deep disabled:opacity-60 inline-flex items-center justify-center gap-2">{busy ? "Opretter …" : <>Videre<Icon name="arrow_forward" size={18} /></>}</button>
    </form>
  );
}
