"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { T } from "@/i18n/translate";
import { CONFLICT, type Addon } from "@/lib/privat/api";
import type { ApiError } from "@/lib/client";
import { BIG, Eyebrow, Pill } from "./bits";
import { CalendarPanel } from "./calendar";
import { Ico, Tile, iconFor } from "./icons";
import { usePlan, usePrivat } from "./store";

/** Name/tagline/description of an add-on: i18n `privat.addons.<key>.<field>` when we have it, else the API's own text
 *  (which the backend already writes in the user's language). A new add-on in the catalog needs no web change. */
export function addonText(t: T, a: Addon, field: "name" | "tagline" | "description"): string {
  const k = `addons.${a.key}.${field}`;
  const v = t(k);
  return v === `privat.${k}` ? a[field] : v;
}

/** Can the app be switched on with the user's rights? Backends without the field: everything that is not
 *  «monthly» is included; monthly apps need the plan. */
export function addonIncluded(a: Addon, entitled: boolean): boolean {
  if (typeof a.included === "boolean") return a.included;
  if (typeof a.requires_plan === "boolean") return !a.requires_plan || entitled;
  return a.pricing !== "monthly" || entitled;
}
const needsPlan = (a: Addon) => a.requires_plan ?? a.pricing === "monthly";

const NOTIFY_KEY = "dialogbot-privat-addon-notify";
function useNotify(): [string[], (k: string) => void] {
  const read = () => { try { return JSON.parse(localStorage.getItem(NOTIFY_KEY) ?? "[]") as string[]; } catch { return []; } };
  const [list, setList] = useState<string[]>(() => (typeof window === "undefined" ? [] : read()));
  const add = (k: string) => {
    // TODO(backend): POST /privat/addons/{key}/notify when it exists. Until then it is remembered in this browser only.
    const next = Array.from(new Set([...list, k]));
    setList(next);
    try { localStorage.setItem(NOTIFY_KEY, JSON.stringify(next)); } catch { /* ignore */ }
  };
  return [list, add];
}

/** Tag under the name: Installeret · gratis / Plus · Familie / Kommer snart / Beta. */
export function StatusPill({ a }: { a: Addon }) {
  const t = useT("privat");
  if (a.status === "coming_soon") return <Pill tone="soon">{t("store.tag.soon")}</Pill>;
  if (a.enabled) return <Pill tone="ok">{needsPlan(a) ? t("store.tag.installed") : t("store.tag.installedFree")}</Pill>;
  if (needsPlan(a)) return <Pill tone="beta">{t("store.tag.plan")}</Pill>;
  if (a.status === "beta") return <Pill tone="beta">{t("store.tag.beta")}</Pill>;
  return <Pill>{t("store.tag.free")}</Pill>;
}

/** Tile colours per app (cycled by key) – orange, ink, mint, yellow, paper – all with the 2 px outline. */
const TILES = ["bg-accent text-white", "bg-ink text-paper", "bg-success-soft text-ink", "bg-highlight text-ink", "bg-panel-deep text-ink"];
export function appTile(key: string): string {
  let h = 0; for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return TILES[h % TILES.length];
}
export function AppTile({ a, size = 62 }: { a: Addon; size?: number }) {
  return <Tile name={iconFor(a.icon)} size={size} className={`${appTile(a.key)} rounded-[18px] border-2 border-ink ${a.status === "coming_soon" ? "opacity-60 border-dashed" : "shadow-block-sm"}`} />;
}

/** Butikken (/privat/butik): icon grid with «Installeret» and «Alle apps»; a tap opens the app sheet. */
export function StorePage() {
  const t = useT("privat");
  const { addons, openSheet, mode } = usePrivat();
  // /privat/kalender (also where Google/Microsoft send the user back): open the Kalender app straight away.
  const hasCalendar = !!addons?.some((a) => a.key === "kalender");
  useEffect(() => {
    if (hasCalendar && window.location.pathname.startsWith("/privat/kalender")) openSheet({ kind: "addon", addonKey: "kalender" });
  }, [hasCalendar, openSheet]);
  const p = usePlan();
  const all = addons ?? [];
  const installed = all.filter((a) => a.enabled);
  const rest = all.filter((a) => !a.enabled);
  const grid = (list: Addon[]) => (
    <ul className="m-0 p-0 list-none grid grid-cols-3 min-[420px]:grid-cols-4 sm:grid-cols-5 xl:grid-cols-4 gap-x-2 gap-y-4">
      {list.map((a) => {
        const name = addonText(t, a, "name");
        return (
          <li key={a.key} className="flex">
            <button type="button" onClick={() => openSheet({ kind: "addon", addonKey: a.key })} aria-label={t("store.openAria", { name })}
              className="flex-1 min-w-0 flex flex-col items-center gap-2 text-center rounded-[20px] p-1.5 hover:bg-panel">
              <AppTile a={a} />
              <span className="text-[13px] font-semibold leading-tight line-clamp-2 [overflow-wrap:anywhere]">{name}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
  return (
    <div className="px-4 pt-5 pb-7 flex flex-col gap-5" aria-label={t("store.title")}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0 flex flex-col gap-0.5">
          <h2 className="m-0 font-display font-extrabold text-[28px] tracking-[-0.5px]">{t("store.title")}</h2>
          <p className="m-0 text-[15px] text-ink-soft">{t("store.lead")}</p>
        </div>
        {p.entitled && <Pill tone="beta">{p.rightsName}</Pill>}
      </div>
      <p className="m-0 text-[14px] text-muted">{t("store.intro")}</p>
      {mode === "demo" && <p className="m-0 text-[14px] text-muted">{t("addons.demoNote")}</p>}
      {addons === null && mode !== "loading" && <p className="m-0 text-[14px] text-muted">{t("addons.unavailable")}</p>}
      {installed.length > 0 && (
        <section className="flex flex-col gap-3" aria-labelledby="store-installed">
          <h3 id="store-installed" className="m-0 text-[15px] font-semibold font-body">{t("store.installed")}</h3>
          {grid(installed)}
        </section>
      )}
      <section className="flex flex-col gap-3" aria-labelledby="store-all">
        <h3 id="store-all" className="m-0 text-[15px] font-semibold font-body">{t("store.all")}</h3>
        {rest.length === 0 && mode !== "loading" ? <p className="m-0 text-[14px] text-muted">{t("store.empty")}</p> : grid(rest)}
      </section>
      <div className="rounded-[20px] border-[1.5px] border-dashed border-ink bg-panel p-4 flex items-start gap-3">
        <Tile name="sparkle" size={40} className="bg-paper text-ink rounded-[12px] border-2 border-ink" />
        <div className="flex flex-col gap-0.5"><span className="font-semibold text-[15px]">{t("store.missing")}</span><span className="text-[14px] text-ink-soft">{t("store.missingText")}</span></div>
      </div>
    </div>
  );
}
/** Old name, kept for imports. */
export const AddonsPage = StorePage;

/** Body of the app sheet: icon, name, tag, «Hvad den gør», «Sådan siger du det til Peter», then Installér (→ the setup
 *  steps + «Start opsætningen» = enable) or Åbn. Without rights the «Med i Plus» offer replaces the button. */
export function AddonDetail({ a }: { a: Addon }) {
  const t = useT("privat");
  const { addons, openSheet, closeSheet, setDraft, go, mode, api, refresh } = usePrivat();
  const p = usePlan();
  const [notified, notify] = useNotify();
  const [setup, setSetup] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const name = addonText(t, a, "name");
  const req = a.requires.map((k) => addons?.find((x) => x.key === k)).filter((x): x is Addon => !!x);
  const steps = a.steps ?? [];
  const included = addonIncluded(a, p.entitled);
  const enable = async () => {
    setErr(null);
    try { await api.enableAddon(a.key); await refresh(); closeSheet(); }
    catch (e) {
      const x = e as ApiError;
      if (x.code === CONFLICT.needsPlan) openSheet({ kind: "needsPlan", addonKey: a.key });
      else setErr(x.message);
    }
  };
  const open = () => { closeSheet(); if (a.example) setDraft(a.example); go("day"); setTimeout(() => document.getElementById("privat-ask-day")?.focus(), 50); };
  return (
    <>
      <div className="flex items-center gap-3">
        <AppTile a={a} size={56} />
        <span className="flex flex-col gap-1 min-w-0"><span className="font-display font-bold text-[18px] leading-tight">{name}</span><span className="flex gap-1.5 flex-wrap"><StatusPill a={a} /></span></span>
      </div>
      <div className="rounded-[18px] border-[1.5px] border-ink bg-panel p-3.5 flex flex-col gap-1">
        <Eyebrow>{t("store.what")}</Eyebrow>
        <p className="m-0 text-[15px] leading-normal">{a.what ?? addonText(t, a, "description")}</p>
      </div>
      {a.example && (
        <div className="rounded-[18px] border-[1.5px] border-ink bg-paper p-3.5 flex flex-col gap-1">
          <Eyebrow>{t("store.say")}</Eyebrow>
          <p className="m-0 text-[16px] font-semibold leading-normal">«{a.example}»</p>
        </div>
      )}
      {a.permissions.length > 0 && (
        <details className="text-[14px]">
          <summary className="cursor-pointer font-semibold min-h-[44px] flex items-center">{t("addons.permissions")}</summary>
          <ul className="m-0 mt-1 p-0 list-none flex flex-col gap-1.5">
            {a.permissions.map((x) => <li key={x} className="flex gap-2 text-[14px]"><span className="text-accent mt-0.5"><Ico name="check" size={16} /></span><span className="min-w-0">{x}</span></li>)}
          </ul>
        </details>
      )}
      {req.length > 0 && <p className="m-0 text-[13px] text-muted">{t("addons.requires", { names: req.map((r) => addonText(t, r, "name")).join(", ") })}</p>}
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}

      {a.status === "coming_soon" ? (
        <>
          <Button className={`${BIG} rounded-full`} disabled aria-label={`${t("store.soon")}: ${name}`}>{t("store.soon")}</Button>
          <Button variant="outline" className="rounded-full border-2" disabled={notified.includes(a.key)} onClick={() => notify(a.key)} aria-label={`${t("addons.notify")}: ${name}`}>{notified.includes(a.key) ? t("addons.notified") : t("addons.notify")}</Button>
        </>
      ) : a.enabled ? (
        <>
          {a.key === "kalender" && mode !== "demo" && <CalendarPanel />}
          <Button className={`${BIG} rounded-full`} onClick={open} aria-label={`${t("store.open")}: ${name}`}>{t("store.open")}</Button>
          <Button variant="outline" className="rounded-full border-2" onClick={() => openSheet({ kind: "addonOff", addonKey: a.key })} aria-label={`${t("addons.disable")}: ${name}`}>{t("addons.disable")}</Button>
        </>
      ) : mode === "demo" ? (
        <p className="m-0 text-[14px] text-muted">{t("store.demoInstall")}</p>
      ) : !included ? (
        <NeedsPlanOffer name={name} />
      ) : !setup || steps.length === 0 ? (
        <Button className={`${BIG} rounded-full`} onClick={() => (steps.length ? setSetup(true) : void enable())} aria-label={`${t("store.install")}: ${name}`}>{t("store.install")}</Button>
      ) : (
        <div className="flex flex-col gap-3" data-testid="addon-setup">
          <div className="flex flex-col gap-0.5"><Eyebrow>{t("store.setup", { n: steps.length })}</Eyebrow><p className="m-0 text-[14px] text-ink-soft">{t("store.setupText")}</p></div>
          <ol className="m-0 p-0 list-none flex flex-col gap-2">
            {steps.map((st, i) => (
              <li key={i} className="flex items-center gap-3">
                <span className={`w-7 h-7 rounded-full border-2 border-ink inline-flex items-center justify-center font-display font-extrabold text-[13px] shrink-0 ${i === steps.length - 1 ? "bg-success-soft text-ink" : "bg-accent text-white"}`}>{i + 1}</span>
                <span className="text-[15px] [overflow-wrap:anywhere]">{st}</span>
              </li>
            ))}
          </ol>
          <Button className={`${BIG} rounded-full`} onClick={() => void enable()} aria-label={`${t("store.start")}: ${name}`}>{t("store.start")}</Button>
        </div>
      )}
    </>
  );
}

/** «Med i Plus – start 14 dage gratis / Vælg plan»: the app (or a call) needs trial, Plus or Familie. */
export function NeedsPlanOffer({ name, call = false }: { name?: string; call?: boolean }) {
  const t = useT("privat");
  const { choosePlan, closeSheet } = usePrivat();
  const p = usePlan();
  const choose = () => { closeSheet(); choosePlan(); };
  return (
    <div className="rounded-[20px] border-2 border-ink bg-accent-soft p-4 flex flex-col gap-2.5" data-testid="needs-plan">
      <Eyebrow>{call ? t("store.needsPlan.callTitle") : t("store.needsPlan.title")}</Eyebrow>
      <p className="m-0 text-[15px] leading-normal">{call ? t("store.needsPlan.callText") : t("store.needsPlan.text", { name: name ?? "" })}</p>
      <Button className={`${BIG} rounded-full`} onClick={choose}>{p.status === "none" ? t("store.needsPlan.trial") : t("store.needsPlan.choose")}</Button>
    </div>
  );
}
