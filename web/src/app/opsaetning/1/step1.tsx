"use client";
import Link from "@/i18n/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Part } from "@/components/setup-parts";
import { Icon, inputCls } from "@/components/ui";
import { api, type ApiError } from "@/lib/client";
import { useRaw, useT } from "@/i18n/client";
import { LOCALES, LOCALE_NAMES, isLocale } from "@/i18n/config";
import { cardsFromGoals, goalsFromCards, hoursText, originOf, parseHours, parseZones, zonesText, type Cards, type DayVocab, type WeeklyRange } from "@/lib/setup";
import { MobileActionBar } from "@/components/mobile-action-bar";

export type Profile = { version: number; legal_name: string; description: string; website_url: string | null; manual_setup: boolean; cvr: string | null; address_line: string | null; postal_code: string | null; city: string | null; country: string; timezone: string; phone: string | null };
export type Goals = { version: number; product_intent: string; guidance_mode: string; inbound_phone: boolean; webchat: boolean; callback: boolean; booking: boolean; conversation_goals: string[] };
export type Languages = { version: number; interface_language: string; default_conversation_language: string; enabled_conversation_languages: string[]; report_language: string };
type Version = { id: string; status: string; title: string; content: Record<string, unknown>; edit_version: number };
export type Fact = { id: string; kind: string; approved_version: Version | null; open_draft: Version | null };
type Created = { kind: string; title: string; item_id: string; version_id: string };
type ImportState = { status: "running" | "done" | "failed"; error: string | null; created_items: Created[]; profile_suggestion: Partial<Record<"description" | "cvr" | "phone" | "address_line" | "postal_code" | "city" | "legal_name", string>> };
type Tag = { key: string; label: string; ok: boolean; versionId?: string };

const OK_KINDS = new Set(["opening_hours", "coverage_area", "fact"]);
const LANGS = ["da", "en", "de"];
const KINDS = new Set(["opening_hours", "coverage_area", "service", "fact", "known_answer", "offer", "unknown_answer"]);
const labelCls = "text-[13px] font-semibold text-ink";

type Save = "idle" | "saving" | "saved" | "error";

/** Trin 1 – Virksomhed. One page, three parts, saved as you type. */
export function Step1({ wsId, canEdit, canApprove, aiReady, cvrReady, profile, goals, languages, facts }: { wsId: string; canEdit: boolean; canApprove: boolean; aiReady: boolean; cvrReady: boolean; profile: Profile; goals: Goals; languages: Languages; facts: Fact[] }) {
  const router = useRouter();
  const t = useT("setup.step1");
  const raw = useRaw();
  const vocab = raw<DayVocab>("setup.hours");
  const kindLabel = (k: string) => (KINDS.has(k) ? t(`kind.${k}`) : k);
  const hoursItem = facts.find((f) => f.kind === "opening_hours");
  const zonesItem = facts.find((f) => f.kind === "coverage_area");
  const pick = (f?: Fact) => f?.approved_version ?? f?.open_draft ?? null;

  const [p, setP] = useState(profile);
  const [cards, setCards] = useState<Cards>(cardsFromGoals(goals));
  // The language Peter speaks to the customers (default_conversation_language): always the stored one. The UI language
  // of whoever opens the page is never used – opening a page must not change data (F-E2B-05-O04); only a tap saves.
  const storedPrimary = languages.default_conversation_language;
  const [primary, setPrimary] = useState<string>(storedPrimary);
  // Extra languages it also speaks (the chips); the primary is always enabled and sent first.
  const [langs, setLangs] = useState<string[]>(languages.enabled_conversation_languages.filter((c) => c !== storedPrimary));
  const [hours, setHours] = useState(hoursText(pick(hoursItem)?.content.weekly as WeeklyRange[] | undefined, vocab));
  const [zones, setZones] = useState(zonesText(pick(zonesItem)?.content.zones as string[] | undefined));
  const [save, setSave] = useState<Save>("idle");
  const [problem, setProblem] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);

  // Versions move on after every save; keep the latest in refs so a quick second edit never sends an old one.
  const ver = useRef({ profile: profile.version, goals: goals.version, languages: languages.version });
  const items = useRef<{ hours?: Fact; zones?: Fact }>({ hours: hoursItem, zones: zonesItem });
  const latest = useRef({ p, cards, langs, primary, hours, zones });
  latest.current = { p, cards, langs, primary, hours, zones };
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const pending = useRef(0);
  const dirty = useRef(new Set<string>());

  const run = useCallback(async (fn: () => Promise<void>) => {
    pending.current += 1; setSave("saving"); setProblem(null);
    try { await fn(); pending.current -= 1; if (pending.current === 0 && dirty.current.size === 0) setSave("saved"); }
    catch (e) {
      pending.current -= 1; setSave("error");
      const err = e as ApiError;
      setProblem(err.code === "version_conflict" ? t("versionConflict") : err.message ?? t("saveFailed"));
    }
  }, [t]);

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
    const main = latest.current.primary;
    const enabled = [main, ...latest.current.langs.filter((c) => c !== main)];
    const next = await api<Languages>(`/workspaces/${wsId}/languages`, { method: "PUT", body: JSON.stringify({ interface_language: languages.interface_language, default_conversation_language: main, report_language: languages.report_language, enabled_conversation_languages: enabled, expected_version: ver.current.languages }) });
    ver.current.languages = next.version;
  }), [run, wsId, languages.interface_language, languages.report_language]);

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
      const w = parseHours(latest.current.hours, vocab);
      if (!latest.current.hours.trim()) { setHint(null); return; }
      if (!w) { setHint(t("hoursHint")); return; }
      setHint(null); await saveFact("hours", "opening_hours", t("hoursTitle"), { weekly: w });
    }
    if (group === "zones") { const z = parseZones(latest.current.zones); if (z.length) await saveFact("zones", "coverage_area", t("zonesTitle"), { zones: z }); }
  }, [saveProfile, saveGoals, saveLangs, saveFact, t, vocab]);
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
      if (imp.status === "failed") throw { message: imp.error ?? t("siteUnreadable") };
      if (imp.status === "running") throw { message: t("siteSlow") };
      // Fill only empty fields: what the owner already wrote is never overwritten.
      const sug = imp.profile_suggestion ?? {};
      const fill: Partial<Profile> = {};
      const tags: Tag[] = [];
      for (const k of ["legal_name", "cvr", "phone", "description", "address_line"] as const) {
        const v = sug[k];
        if (!v) continue;
        tags.push({ key: `p-${k}`, label: `${t(`profileTag.${k}`)}: ${v.length > 48 ? `${v.slice(0, 46)}…` : v}`, ok: true });
        if (!String((latest.current.p as Record<string, unknown>)[k] ?? "").trim() && k !== "legal_name") (fill as Record<string, string>)[k] = v;
        if (k === "legal_name" && !latest.current.p.legal_name.trim()) fill.legal_name = v;
      }
      for (const c of imp.created_items ?? []) tags.push({ key: c.version_id, label: `${kindLabel(c.kind)}: ${c.title}`, ok: OK_KINDS.has(c.kind), versionId: c.version_id });
      if (Object.keys(fill).length) { setP((cur) => ({ ...cur, ...fill })); later("profile", 300); }
      setSite({ busy: false, error: null, tags, approved: false });
      // Hours and area from the site become the field text (as drafts until approved).
      const list = await api<{ items: Fact[] }>(`/workspaces/${wsId}/knowledge/items?limit=200`);
      const h = list.items.find((i) => i.kind === "opening_hours"), z = list.items.find((i) => i.kind === "coverage_area");
      if (h && !latest.current.hours.trim()) { items.current.hours = h; setHours(hoursText(pick(h)?.content.weekly as WeeklyRange[] | undefined, vocab)); }
      if (z && !latest.current.zones.trim()) { items.current.zones = z; setZones(zonesText(pick(z)?.content.zones as string[] | undefined)); }
      void deriveCategory();
    } catch (e) {
      setSite({ busy: false, error: (e as ApiError).message ?? t("siteFailed"), tags: [], approved: false });
    }
  };
  const approveAll = async () => {
    if (!site) return;
    setSite({ ...site, busy: true });
    try {
      for (const tg of site.tags) if (tg.versionId && !tg.ok) await api(`/workspaces/${wsId}/knowledge/versions/${tg.versionId}/approve`, { method: "POST", body: "{}" }).catch(() => undefined);
      for (const tg of site.tags) if (tg.versionId && tg.ok) await api(`/workspaces/${wsId}/knowledge/versions/${tg.versionId}/approve`, { method: "POST", body: "{}" }).catch(() => undefined);
      setSite((s) => s && { ...s, busy: false, approved: true, tags: s.tags.map((tg) => ({ ...tg, ok: true })) });
    } catch (e) { setSite((s) => s && { ...s, busy: false, error: (e as ApiError).message }); }
  };
  const yellow = site?.tags.filter((tg) => !tg.ok).length ?? 0;
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
  const toggleLang = (code: string) => { if (code === primary) return; setLangs((cur) => (cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code])); later("langs", 400); };
  const choosePrimary = (code: string) => { setLangs((cur) => cur.filter((c) => c !== code && c !== primary)); setPrimary(code); later("langs", 400); };
  const ready = p.legal_name.trim() && (p.phone ?? "").trim() && p.description.trim();
  const next = cards.booking ? 2 : 3;
  const [going, setGoing] = useState(false);

  return (
    <div className="flex flex-col gap-6">
      {!canEdit && <p role="status" className="rounded-xl bg-highlight px-4 py-3 text-[14px] text-ink">{t("readOnly")}</p>}
      <Part letter="A" title={t("a.title")} hint={aiReady ? t("a.hintAi") : t("a.hintNoAi")}>
        <div className="flex flex-col sm:flex-row gap-2">
          <input aria-label={t("a.urlAria")} className={`${inputCls} flex-1`} placeholder={t("a.urlPlaceholder")} inputMode="url" autoCapitalize="none" value={p.website_url ?? ""} onChange={field("website_url")} disabled={!canEdit} />
          {aiReady && canEdit && <button type="button" onClick={fetchSite} disabled={site?.busy || !(p.website_url ?? "").trim()} className="min-h-[46px] px-5 rounded-xl bg-ink text-paper font-semibold disabled:opacity-60 inline-flex items-center justify-center gap-1.5">{site?.busy && !site.tags.length ? t("a.reading") : <>{t("a.fetch")}<Icon name="arrow_forward" size={16} /></>}</button>}
        </div>
        {site?.error && <p role="alert" className="text-[14px] text-danger">{site.error}</p>}
        {site && site.tags.length > 0 && (
          <div className="rounded-2xl border-[1.5px] border-ink bg-panel p-4 flex flex-col gap-3" aria-live="polite">
            <span className="eyebrow">{t("a.foundOn", { site: originOf(p.website_url)?.replace(/^https?:\/\//, "") ?? t("a.theSite") })}</span>
            <ul className="flex flex-wrap gap-2">
              {site.tags.map((tg) => <li key={tg.key} className={`px-3 py-1.5 rounded-full text-[13px] font-semibold border-[1.5px] ${tg.ok ? "bg-success-soft text-success border-success-soft" : "bg-highlight text-ink border-ink"}`}>{tg.ok ? "✓ " : "? "}{tg.label}</li>)}
            </ul>
            <div className="flex flex-wrap gap-2">
              {canApprove && !site.approved && site.tags.some((tg) => tg.versionId) && <button type="button" onClick={approveAll} disabled={site.busy} className="min-h-[44px] px-4 rounded-xl bg-paper border-2 border-ink font-semibold hover:bg-panel-deep">{t("a.approveAll", { n: site.tags.filter((tg) => tg.versionId).length })}</button>}
              {yellow > 0 && !site.approved && <Link href="/app/viden?tab=k05" className="inline-flex items-center min-h-[44px] px-4 rounded-xl bg-paper border-2 border-ink font-semibold hover:bg-panel-deep">{t("a.fixYellow")}</Link>}
              {site.approved && <span className="inline-flex items-center min-h-[44px] text-[14px] text-success font-semibold">{t("a.allApproved")}</span>}
            </div>
          </div>
        )}
      </Part>

      <Part letter="B" title={t("b.title")} hint={t("b.hint")}>
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("b.name")}</span><input className={inputCls} value={p.legal_name} onChange={field("legal_name")} disabled={!canEdit} autoComplete="organization" /></label>
          <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("b.phone")}</span><input className={inputCls} value={p.phone ?? ""} onChange={field("phone")} disabled={!canEdit} inputMode="tel" autoComplete="tel" placeholder={t("b.phonePlaceholder")} /></label>
        </div>
        <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("b.description")}</span><input className={inputCls} value={p.description} maxLength={400} onChange={(e) => { field("description")(e); catDone.current = false; }} onBlur={() => void deriveCategory()} disabled={!canEdit} placeholder={t("b.descriptionPlaceholder")} /></label>
        <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("b.customerLanguage")}</span>
          <select className={inputCls} value={primary} onChange={(e) => choosePrimary(e.target.value)} disabled={!canEdit}>
            {!isLocale(primary) && <option value={primary}>{primary}</option>}
            {LOCALES.map((l) => <option key={l} value={l}>{LOCALE_NAMES[l]}</option>)}
          </select></label>
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("b.hours")}</span><input className={inputCls} value={hours} onChange={(e) => { setHours(e.target.value); later("hours"); }} disabled={!canEdit} placeholder={t("b.hoursPlaceholder")} aria-describedby="hours-hint" /></label>
          <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("b.zones")}</span><input className={inputCls} value={zones} onChange={(e) => { setZones(e.target.value); later("zones"); }} disabled={!canEdit} placeholder={t("b.zonesPlaceholder")} /></label>
        </div>
        <p id="hours-hint" className={`text-[13px] ${hint ? "text-danger" : "text-muted"}`} role={hint ? "alert" : undefined}>{hint ?? (canApprove ? t("b.factsLive") : t("b.factsDraft"))}</p>
        <details className="rounded-xl border-[1.5px] border-ink px-4 py-2">
          <summary className="cursor-pointer min-h-[36px] flex items-center text-[14px] font-semibold text-ink">{t("b.cvrSummary")}</summary>
          <div className="grid sm:grid-cols-2 gap-4 pt-3 pb-2">
            <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("b.cvr")}</span><input className={inputCls} value={p.cvr ?? ""} onChange={field("cvr")} onBlur={() => void cvrLookup()} disabled={!canEdit} inputMode="numeric" /></label>
            <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("b.address")}</span><input className={inputCls} value={p.address_line ?? ""} onChange={field("address_line")} disabled={!canEdit} autoComplete="street-address" /></label>
            <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("b.postalCode")}</span><input className={inputCls} value={p.postal_code ?? ""} onChange={field("postal_code")} disabled={!canEdit} inputMode="numeric" /></label>
            <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("b.city")}</span><input className={inputCls} value={p.city ?? ""} onChange={field("city")} disabled={!canEdit} /></label>
          </div>
          {cvrNote && <p className="text-[13px] text-muted pb-2">{t("b.cvrLooked", { note: cvrNote })}</p>}
        </details>
      </Part>

      <Part letter="C" title={t("c.title")} hint={t("c.hint")}>
        <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(["phone", "booking", "web", "outbound"] as (keyof Cards)[]).map((k) => [k, t(`c.cards.${k}.title`), t(`c.cards.${k}.sub`)] as const).map(([k, title, sub]) => (
            <li key={k}>
              <label className={`flex items-start gap-3 rounded-2xl border-2 border-ink p-4 min-h-[76px] h-full cursor-pointer ${cards[k] ? "bg-highlight" : "bg-paper hover:bg-panel"}`}>
                <input type="checkbox" className="mt-1 w-5 h-5 accent-ink shrink-0" checked={cards[k]} onChange={() => toggle(k)} disabled={!canEdit} />
                <span className="flex flex-col"><span className="font-display font-bold text-[17px] text-ink">{title}</span><span className="text-[13px] text-ink-soft">{sub}</span></span>
              </label>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("c.langAria")}>
          <span className={labelCls}>{t("c.speaks")}</span>
          {LANGS.map((c) => {
            const on = c === primary || langs.includes(c);
            const l = t(`langNames.${c}`);
            return <button key={c} type="button" aria-pressed={on} disabled={!canEdit || c === primary} onClick={() => toggleLang(c)} className={`min-h-[44px] px-4 rounded-full border-2 border-ink text-[14px] font-semibold ${on ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`}>{on ? l : `+ ${l}`}</button>;
          })}
          <span className="text-[13px] text-muted">{t("c.alwaysDanish")}</span>
        </div>
      </Part>

      <MobileActionBar className="flex-col-reverse sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[13px] leading-snug text-muted" role="status" aria-live="polite">
          {save === "saving" ? t("status.saving") : save === "saved" ? t("status.saved") : save === "error" ? "" : t("status.idle")}{t("status.comeBack")}
          {!ready && <span className="block">{t("status.fillIn")}</span>}
          {problem && <span className="block text-danger" role="alert">{problem} {problem === t("versionConflict") && <button type="button" className="underline" onClick={() => router.refresh()}>{t("status.reload")}</button>}</span>}
        </p>
        <button type="button" disabled={!ready || going} onClick={async () => {
          setGoing(true); await flush();
          if (pending.current > 0) await new Promise((r) => setTimeout(r, 400));
          router.push(`/opsaetning/${next}`);
        }} className={`inline-flex items-center justify-center gap-2 min-h-[52px] px-6 rounded-xl font-semibold text-[16px] ${ready ? "bg-accent text-white hover:bg-accent-deep" : "bg-line text-muted"} disabled:opacity-70`}>
          {next === 2 ? t("nextTo2") : t("nextTo3")}<Icon name="arrow_forward" size={18} />
        </button>
      </MobileActionBar>
    </div>
  );
}

/** First visit: no workspace yet. The name creates it; the rest of the page opens straight after. */
export function CreateWorkspace({ verified, defaultIntent, referralLink }: { verified: boolean; defaultIntent: string; referralLink: string | null }) {
  const router = useRouter();
  const t = useT("setup.create");
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
    } catch (err) { setError((err as ApiError).message ?? t("failed")); setBusy(false); }
  };
  return (
    <form onSubmit={go} className="rounded-[20px] bg-paper border-2 border-ink p-5 md:p-6 flex flex-col gap-4 max-w-[640px]">
      {!verified && <p role="alert" className="rounded-xl bg-highlight px-4 py-3 text-[14px] text-ink">{t("verifyFirst")} <Link className="underline font-semibold" href="/verify-email">{t("verifyLink")}</Link></p>}
      {referralLink && <p className="flex items-center gap-2 text-[14px] text-ink-soft"><Icon name="loyalty" size={18} />{t("referral")}</p>}
      <label className="flex flex-col gap-1.5"><span className={labelCls}>{t("name")}</span>
        <input required minLength={2} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("namePlaceholder")} autoComplete="organization" /></label>
      {error && <p role="alert" className="text-[14px] text-danger">{error}</p>}
      <button disabled={busy || !verified || name.trim().length < 2} className="min-h-[52px] px-6 rounded-xl bg-accent text-white font-semibold text-[16px] hover:bg-accent-deep disabled:opacity-60 inline-flex items-center justify-center gap-2">{busy ? t("creating") : <>{t("next")}<Icon name="arrow_forward" size={18} /></>}</button>
    </form>
  );
}
