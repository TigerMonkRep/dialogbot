"use client";
import { useState } from "react";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { T } from "@/i18n/translate";
import type { Addon } from "@/lib/privat/api";
import { BIG, Eyebrow, Pill } from "./bits";
import { Ico, Tile, iconFor } from "./icons";
import { usePrivat } from "./store";

/** Name/tagline/description of an add-on: i18n `privat.addons.<key>.<field>` when we have it, else the API's own text
 *  (which the backend already writes in the user's language). A new add-on in the catalog needs no web change. */
export function addonText(t: T, a: Addon, field: "name" | "tagline" | "description"): string {
  const k = `addons.${a.key}.${field}`;
  const v = t(k);
  return v === `privat.${k}` ? a[field] : v;
}

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

export function StatusPill({ a }: { a: Addon }) {
  const t = useT("privat");
  if (a.status === "coming_soon") return <Pill tone="soon">{t("addons.soon")}</Pill>;
  if (a.enabled) return <Pill tone="ok">{t("addons.on")}</Pill>;
  if (a.status === "beta") return <Pill tone="beta">{t("addons.beta")}</Pill>;
  return null;
}

/** The action on a card or in the detail sheet: «Slå til», «Slå fra» (asks first) or «Giv mig besked». */
export function AddonAction({ a, big = false }: { a: Addon; big?: boolean }) {
  const t = useT("privat");
  const { run, openSheet } = usePrivat();
  const [notified, notify] = useNotify();
  const name = addonText(t, a, "name");
  if (a.status === "coming_soon") {
    const done = notified.includes(a.key);
    return <Button variant="outline" disabled={done} onClick={() => notify(a.key)} aria-label={`${t("addons.notify")}: ${name}`}>{done ? t("addons.notified") : t("addons.notify")}</Button>;
  }
  if (a.enabled) return <Button variant="outline" onClick={() => openSheet({ kind: "addonOff", addonKey: a.key })} aria-label={`${t("addons.disable")}: ${name}`}>{t("addons.disable")}</Button>;
  return <Button className={big ? BIG : "border-2 border-ink"} onClick={() => run((x) => x.enableAddon(a.key))} aria-label={`${t("addons.enable")}: ${name}`}>{t("addons.enable")}</Button>;
}

export function AddonsPage() {
  const t = useT("privat");
  const { addons, openSheet, mode } = usePrivat();
  const cats = new Map<string, Addon[]>();
  for (const a of addons ?? []) cats.set(a.category, [...(cats.get(a.category) ?? []), a]);
  return (
    <div className="px-4 pt-5 pb-7 flex flex-col gap-5" aria-label={t("addons.title")}>
      <h2 className="m-0 font-display font-extrabold text-[28px] tracking-[-0.5px]">{t("addons.title")}</h2>
      <p className="m-0 text-[15px] text-ink-soft">{t("addons.lead")}</p>
      {mode === "demo" && <p className="m-0 text-[14px] text-muted">{t("addons.demoNote")}</p>}
      {addons === null && mode !== "loading" && <p className="m-0 text-[14px] text-muted">{t("addons.unavailable")}</p>}
      {[...cats.entries()].map(([cat, list]) => (
        <section key={cat} className="flex flex-col gap-3">
          <h3 className="m-0 text-[15px] font-semibold font-body">{cat}</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-1 gap-3">
            {list.map((a) => {
              const name = addonText(t, a, "name");
              return (
                <article key={a.key} className={`rounded-[18px] border-2 ${a.status === "coming_soon" ? "border-dashed" : ""} border-ink bg-paper p-4 flex flex-col gap-3`}>
                  <button type="button" onClick={() => openSheet({ kind: "addon", addonKey: a.key })} aria-label={t("addons.openAria", { name })}
                    className="flex items-start gap-3 text-left rounded-xl -m-1 p-1 hover:bg-panel">
                    <Tile name={iconFor(a.icon)} />
                    <span className="flex-1 min-w-0 flex flex-col gap-1">
                      <span className="flex items-center gap-2 flex-wrap"><span className="font-display font-bold text-[19px]">{name}</span><StatusPill a={a} /></span>
                      <span className="text-[14px] text-ink-soft">{addonText(t, a, "tagline")}</span>
                      <span className="text-[13px] font-semibold text-ink">{a.price_text}</span>
                    </span>
                    <Ico name="chevron" size={20} className="mt-1" />
                  </button>
                  <div className="flex gap-2 flex-wrap"><AddonAction a={a} /></div>
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

/** Body of the add-on detail sheet: what it does and what it is allowed to do, before it is switched on. */
export function AddonDetail({ a }: { a: Addon }) {
  const t = useT("privat");
  const { addons } = usePrivat();
  const req = a.requires.map((k) => addons?.find((x) => x.key === k)).filter((x): x is Addon => !!x);
  return (
    <>
      <div className="flex items-center gap-3"><Tile name={iconFor(a.icon)} size={48} /><span className="flex flex-col gap-1"><StatusPill a={a} /><span className="text-[14px] font-semibold">{t("addons.price")}: {a.price_text}</span></span></div>
      <Eyebrow>{t("addons.canDo")}</Eyebrow>
      <p className="m-0 text-[15px] leading-normal text-ink-soft">{addonText(t, a, "description")}</p>
      {a.permissions.length > 0 && (
        <>
          <Eyebrow>{t("addons.permissions")}</Eyebrow>
          <ul className="m-0 p-0 list-none flex flex-col gap-1.5">
            {a.permissions.map((p) => <li key={p} className="flex gap-2 text-[15px]"><span className="text-accent mt-0.5"><Ico name="check" size={18} /></span><span className="min-w-0">{p}</span></li>)}
          </ul>
        </>
      )}
      {req.length > 0 && <p className="m-0 text-[13px] text-muted">{t("addons.requires", { names: req.map((r) => addonText(t, r, "name")).join(", ") })}</p>}
      <AddonAction a={a} big />
    </>
  );
}
