"use client";
/** Apps (the «Apps» tab): Mine apps (/privat/apps), Butikken (/privat/butik), an app in the shop (/privat/butik/<key>)
 *  and an app's own page (/privat/apps/<key>). Pages, not sheets – they can be linked to and the back button works.
 *  Sheets are only confirmations: «Slå til?» (consent to the permissions) → «slået til», «kræver plan» (plan choice;
 *  the app comes on with the plan) and «Slå fra?» (what stops, what is kept) with Fortryd afterwards.
 *  Design: apps-review/design (Mine apps, Butikken, app-side, Slå til/fra). */
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import { ADDON, CONFLICT, type Addon, type PlanKey } from "@/lib/privat/api";
import type { ApiError } from "@/lib/client";
import { BIG, CHIP, Eyebrow, LINK, Pill } from "./bits";
import { BillsPanel } from "./bills";
import { BirthdaysPanel } from "./birthdays";
import { CalendarPanel } from "./calendar";
import { CarPanel, HealthPanel, MealsPanel, ParcelsPanel } from "./more-apps";
import { HOUSEHOLD_APPS, HouseholdPanel } from "./household";
import { TravelPanel } from "./travel";
import { Ico, Tile, iconFor } from "./icons";
import { Sheet } from "./sheets";
import { useFmt, usePlan, usePrivat } from "./store";
import { addonIncluded, addonText } from "./addons";

const CATEGORIES = ["hverdag", "lister", "aftaler", "opkald"] as const;
/** The apps every account gets switched on (no «Dine apps» strip on Min dag for those alone). */
const DEFAULT_APPS = new Set<string>([ADDON.call, ADDON.sharedLists, ADDON.wishlists]);
const PAGE = "w-full max-w-[1240px] mx-auto px-4 pt-5 pb-28 xl:pb-10 flex flex-col gap-5";
const PRIMARY = "inline-flex items-center justify-center gap-2 rounded-full font-semibold border-2 border-ink min-h-[52px] px-5 text-[16px] bg-accent text-white hover:bg-accent-deep disabled:opacity-60";
const OUTLINE = "inline-flex items-center justify-center gap-2 rounded-full font-semibold border-2 border-ink min-h-[44px] px-4 text-[15px] bg-paper text-ink hover:bg-panel disabled:opacity-60";

export const appHref = (a: Addon) => (a.enabled || a.disabled_at ? `/privat/apps/${encodeURIComponent(a.key)}` : `/privat/butik/${encodeURIComponent(a.key)}`);
const setupLeft = (a: Addon) => !!a.setup && a.setup.total > 0 && a.setup.done < a.setup.total;

/** One tile for every app: white icon on the accent (brand.md «ikoner: hvide på accent-flise»; ux-audit #9). The icon
 *  tells the apps apart, not a colour – yellow stays «her er du». */
export function appTile(_key: string): string {
  return "bg-accent text-white";
}
export function AppTile({ a, size = 48 }: { a: Addon; size?: number }) {
  const soon = a.status === "coming_soon";
  return <Tile name={iconFor(a.icon)} size={size} className={`${soon ? "bg-panel text-ink border-dashed" : appTile(a.key)} rounded-[14px] border-2 border-ink`} />;
}

/** The one label per app: Slået til · Gratis · Med i alle planer · Plus · Familie · Kommer snart. */
export function AppBadge({ a }: { a: Addon }) {
  const t = useT("privat");
  if (a.status === "coming_soon") return <Pill tone="soon">{t("apps.badge.soon")}</Pill>;
  if (a.enabled) return <Pill tone="ok"><Ico name="check" size={12} stroke={3} className="mr-1" />{t("apps.badge.on")}</Pill>;
  const plans = a.included_in ?? (a.requires_plan ? ["plus", "familie"] : []);
  if (plans.length === 0) return <Pill>{t("apps.badge.free")}</Pill>;
  if (plans.includes("basis")) return <Pill>{t("apps.badge.allPlans")}</Pill>;
  return <Pill tone="beta">{t("apps.badge.plan")}</Pill>;
}

/** Mine apps · Butikken – the switch on top of both pages. */
function AppsSwitch({ active, count }: { active: "mine" | "shop"; count: number }) {
  const t = useT("privat");
  const tab = (on: boolean) => `flex-1 inline-flex items-center justify-center gap-2 min-h-[44px] rounded-full text-[15px] font-semibold ${on ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`;
  return (
    <nav aria-label={t("apps.switchLabel")} className="flex p-1 rounded-full border-2 border-ink bg-paper max-w-[440px] w-full">
      <Link href="/privat/apps" aria-current={active === "mine" ? "page" : undefined} className={tab(active === "mine")}>
        {t("apps.mine")}{count > 0 && <span className="min-w-6 h-6 px-1.5 rounded-full bg-highlight text-ink text-[13px] font-bold inline-flex items-center justify-center border-[1.5px] border-ink">{count}</span>}
      </Link>
      <Link href="/privat/butik" aria-current={active === "shop" ? "page" : undefined} className={tab(active === "shop")}>{t("apps.shop")}</Link>
    </nav>
  );
}

function Loading() {
  const t = useT("privat");
  return (
    <div className="flex flex-col gap-2" role="status" aria-live="polite">
      <span className="text-[14px] text-muted">{t("apps.loading")}</span>
      {[0, 1, 2].map((i) => <div key={i} className="h-[76px] rounded-[18px] border-2 border-line bg-panel" aria-hidden />)}
    </div>
  );
}

function LoadError() {
  const t = useT("privat");
  const { refresh } = usePrivat();
  return (
    <div role="alert" className="rounded-[18px] border-2 border-danger bg-danger-soft p-4 flex flex-col gap-2">
      <p className="m-0 text-[15px] font-semibold">{t("apps.error")}</p>
      <Button variant="outline" className="self-start border-2 rounded-full" onClick={() => void refresh().catch(() => {})}>{t("apps.retry")}</Button>
    </div>
  );
}

/** One app as a row (phone) / card (desktop): tile, name, the line (tagline or what it holds), badge. */
function AppRow({ a, line, variant = "shop" }: { a: Addon; line?: string | null; variant?: "shop" | "mine" | "kept" }) {
  const t = useT("privat");
  const name = addonText(t, a, "name");
  const kept = variant === "kept";
  // In the shop the plan badge only shows when the plan does NOT cover the app – «Plus · Familie» on every row of a
  // Plus trial was noise (ux-audit #9).
  const included = addonIncluded(a, usePlan().entitled);
  return (
    <li className="min-w-0">
      <Link href={appHref(a)} data-testid={`app-row-${a.key}`}
        className={`h-full w-full flex items-center gap-3 rounded-[18px] border-2 ${kept ? "border-dashed border-ink-soft bg-panel" : "border-ink bg-paper hover:bg-panel"} px-3.5 py-3 text-ink no-underline`}>
        <AppTile a={a} />
        <span className="flex-1 min-w-0 flex flex-col gap-1">
          <span className="font-semibold text-[16px] leading-tight [overflow-wrap:anywhere]">{name}</span>
          <span className="text-[14px] text-ink-soft leading-snug line-clamp-2 [overflow-wrap:anywhere]">{line ?? addonText(t, a, "tagline")}</span>
          {variant === "shop" && (a.status === "coming_soon" || !included) && <span className="flex gap-1.5 flex-wrap"><AppBadge a={a} /></span>}
          {kept && <span><Pill tone="soon">{t("apps.keptPill")}</Pill></span>}
        </span>
        <Ico name="chevron" size={18} className="text-ink-soft" />
      </Link>
    </li>
  );
}

/** The plan line on top of Butikken: what the user's rights include. */
function PlanLine({ all }: { all: Addon[] }) {
  const t = useT("privat");
  const p = usePlan();
  const { startTrial, choosePlan } = usePrivat();
  const planApps = all.filter((a) => a.requires_plan && a.status !== "coming_soon").length;
  if (p.status === "trial") return <p className="m-0 rounded-[14px] bg-accent-soft border-[1.5px] border-ink px-3.5 py-2.5 text-[14px]">{t("apps.planLine.trial", { n: p.trialDays })}</p>;
  if (p.entitled) return <p className="m-0 rounded-[14px] bg-accent-soft border-[1.5px] border-ink px-3.5 py-2.5 text-[14px]">{t("apps.planLine.plan", { plan: p.rightsName })}</p>;
  return (
    <div className="rounded-[14px] bg-accent-soft border-[1.5px] border-ink px-3.5 py-2.5 flex flex-wrap items-center gap-2">
      <p className="m-0 flex-1 min-w-[200px] text-[14px]">{t(p.status === "none" ? "apps.planLine.none" : "apps.planLine.expired", { n: planApps })}</p>
      <button type="button" className={`${LINK} min-h-[36px]`} onClick={() => (p.status === "none" ? void startTrial() : choosePlan())}>{p.status === "none" ? t("apps.tryFree") : t("apps.choosePlan")}</button>
    </div>
  );
}

// ---------------------------------------------------------------- Butikken

export function ShopPage() {
  const t = useT("privat");
  const { addons, mode } = usePrivat();
  const [cat, setCat] = useState<string>("alle");
  const all = addons ?? [];
  const on = all.filter((a) => a.enabled).length;
  // Butikken shows what you do not have yet; what is on (or switched off with data kept) lives in Mine apps.
  const avail = all.filter((a) => !a.enabled && !a.disabled_at);
  const groups = CATEGORIES.map((c) => ({ c, apps: avail.filter((a) => a.category === c).sort((x, y) => Number(x.status === "coming_soon") - Number(y.status === "coming_soon")) }))
    .filter((g) => g.apps.length > 0 && (cat === "alle" || g.c === cat));
  const others = avail.filter((a) => !CATEGORIES.includes(a.category as (typeof CATEGORIES)[number]));
  const pick = all.find((a) => !a.enabled && !a.disabled_at && a.status !== "coming_soon" && a.requires_plan);
  return (
    <div className={PAGE} aria-labelledby="shop-h">
      <AppsSwitch active="shop" count={on} />
      <div className="flex flex-col gap-1">
        <h1 id="shop-h" className="m-0 font-display font-extrabold text-[30px] xl:text-[36px] tracking-[-0.5px]">{t("store.title")}</h1>
        <p className="m-0 text-[16px] text-ink-soft max-w-[640px]">{t("apps.shopLead")}</p>
      </div>
      {mode === "demo" && <p className="m-0 text-[14px] text-muted">{t("addons.demoNote")}</p>}
      {addons === null && mode !== "loading" ? <LoadError /> : mode === "loading" && all.length === 0 ? <Loading /> : (
        <>
          <PlanLine all={all} />
          <div className="flex gap-2 overflow-x-auto -mx-4 px-4 pb-1" role="group" aria-label={t("apps.filterLabel")}>
            {["alle", ...CATEGORIES.filter((c) => avail.some((a) => a.category === c))].map((c) => (
              <button key={c} type="button" aria-pressed={cat === c} onClick={() => setCat(c)}
                className={`${CHIP} shrink-0 ${cat === c ? "!bg-ink !text-paper" : ""}`}>
                {t(`apps.cat.${c}`)}{c === "alle" && <span className="text-[12px] opacity-80">{avail.length}</span>}
              </button>
            ))}
          </div>
          {pick && cat === "alle" && (
            <Link href={appHref(pick)} className="rounded-[20px] border-2 border-ink bg-paper shadow-block p-4 flex flex-col gap-2 no-underline text-ink" data-testid="shop-pick">
              <span className="flex items-center gap-3"><AppTile a={pick} size={52} /><span className="flex flex-col"><Eyebrow>{t("apps.pickEyebrow")}</Eyebrow><span className="font-display font-extrabold text-[20px]">{addonText(t, pick, "name")}</span></span></span>
              <span className="text-[15px] text-ink-soft">{pick.what || addonText(t, pick, "description")}</span>
              {pick.example && <span className="text-[15px] font-semibold">«{pick.example.replace(/^«|»$/g, "")}»</span>}
              <span className="flex items-center justify-between gap-2 flex-wrap"><span className={OUTLINE}>{t("apps.seeApp")}</span><AppBadge a={pick} /></span>
            </Link>
          )}
          {groups.map((g) => (
            <section key={g.c} className="flex flex-col gap-2.5" aria-labelledby={`cat-${g.c}`}>
              <h2 id={`cat-${g.c}`} className="m-0 text-[17px] font-display font-bold flex items-baseline gap-2">{t(`apps.cat.${g.c}`)} <span className="text-[13px] font-body font-semibold text-muted">{t("apps.count", { n: g.apps.length })}</span></h2>
              <ul className="m-0 p-0 list-none grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2.5">
                {g.apps.map((a) => <AppRow key={a.key} a={a} />)}
              </ul>
            </section>
          ))}
          {avail.length === 0 && mode !== "loading" && <p className="m-0 text-[15px] text-ink-soft" data-testid="shop-all-on">{t("apps.allOn")}</p>}
          {others.length > 0 && cat === "alle" && (
            <ul className="m-0 p-0 list-none grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2.5">{others.map((a) => <AppRow key={a.key} a={a} />)}</ul>
          )}
        </>
      )}
      <div className="rounded-[20px] border-[1.5px] border-dashed border-ink bg-panel p-4 flex items-start gap-3">
        <Tile name="sparkle" size={40} className="bg-paper text-ink rounded-[12px] border-2 border-ink" />
        <div className="flex flex-col gap-0.5"><span className="font-semibold text-[15px]">{t("store.missing")}</span><span className="text-[14px] text-ink-soft">{t("store.missingText")}</span></div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Mine apps

export function MyAppsPage() {
  const t = useT("privat");
  const { addons, mode } = usePrivat();
  const all = addons ?? [];
  const on = all.filter((a) => a.enabled);
  const kept = all.filter((a) => !a.enabled && a.disabled_at);
  const setup = on.find(setupLeft);
  const more = all.filter((a) => !a.enabled && !a.disabled_at && a.status !== "coming_soon").length;
  return (
    <div className={PAGE} aria-labelledby="mine-h">
      <AppsSwitch active="mine" count={on.length} />
      <div className="flex flex-col gap-1">
        <h1 id="mine-h" className="m-0 font-display font-extrabold text-[30px] xl:text-[36px] tracking-[-0.5px]">{t("apps.mine")}</h1>
        {on.length > 0 && <p className="m-0 text-[16px] text-ink-soft max-w-[640px]">{t("apps.mineLead", { n: on.length })}</p>}
      </div>
      {addons === null && mode !== "loading" ? <LoadError /> : mode === "loading" && all.length === 0 ? <Loading /> : on.length === 0 && kept.length === 0 ? (
        <div className="rounded-[20px] border-2 border-ink bg-paper p-5 flex flex-col gap-3 items-start" data-testid="mine-empty">
          <StepSquare n={1} size={56} />
          <h2 className="m-0 font-display font-extrabold text-[22px]">{t("apps.emptyTitle")}</h2>
          <p className="m-0 text-[15px] text-ink-soft">{t("apps.emptyText")}</p>
          <Link href="/privat/butik" className={PRIMARY}>{t("apps.toShop")}</Link>
        </div>
      ) : (
        <>
          {setup && <SetupCard a={setup} />}
          {on.length > 0 && (
            <section className="flex flex-col gap-2.5" aria-labelledby="mine-on">
              <h2 id="mine-on" className="m-0 eyebrow">{t("apps.onSection", { n: on.length })}</h2>
              <ul className="m-0 p-0 list-none grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2.5">
                {on.map((a) => <AppRow key={a.key} a={a} line={a.summary_line} variant="mine" />)}
              </ul>
            </section>
          )}
          {kept.length > 0 && (
            <section className="flex flex-col gap-2.5" aria-labelledby="mine-kept">
              <h2 id="mine-kept" className="m-0 eyebrow">{t("apps.keptSection")}</h2>
              <ul className="m-0 p-0 list-none grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2.5">
                {kept.map((a) => <AppRow key={a.key} a={a} line={t("apps.keptLine")} variant="kept" />)}
              </ul>
            </section>
          )}
        </>
      )}
      {more > 0 && (
        <Link href="/privat/butik" className="rounded-[20px] border-[1.5px] border-dashed border-ink bg-panel p-4 flex items-center gap-3 no-underline text-ink">
          <Tile name="shop" size={44} className="bg-paper text-ink rounded-[12px] border-2 border-ink" />
          <span className="flex-1 min-w-0 flex flex-col"><span className="font-semibold text-[16px]">{t("apps.findMore")}</span><span className="text-[14px] text-ink-soft">{t("apps.findMoreText", { n: more })}</span></span>
          <Ico name="chevron" size={18} />
        </Link>
      )}
    </div>
  );
}

function StepSquare({ n, size = 40, done = false }: { n: number; size?: number; done?: boolean }) {
  return (
    <span aria-hidden className={`inline-flex shrink-0 items-center justify-center font-display font-extrabold border-2 border-ink ${done ? "bg-success-soft" : "bg-highlight"} text-ink`}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.22), fontSize: Math.round(size * 0.45) }}>{done ? <Ico name="check" size={Math.round(size * 0.5)} stroke={3} /> : n}</span>
  );
}

/** The app that still has a setup step: the one primary button on Mine apps. */
function SetupCard({ a }: { a: Addon }) {
  const t = useT("privat");
  const done = a.setup?.done ?? 0;
  const step = (a.steps ?? [])[done];
  return (
    <div className="rounded-[20px] border-2 border-ink bg-paper shadow-block p-4 flex flex-col gap-2.5" data-testid="setup-card">
      <StepSquare n={done + 1} size={48} />
      <Eyebrow>{t("apps.setupEyebrow", { name: addonText(t, a, "name"), n: done + 1, total: a.setup?.total ?? 0 })}</Eyebrow>
      {step && <p className="m-0 font-display font-bold text-[19px] leading-snug">{step}</p>}
      <Link href={appHref(a)} className={PRIMARY}>{t("apps.continue")}</Link>
    </div>
  );
}

// ---------------------------------------------------------------- an app in the shop

function useApp(key: string | null): Addon | undefined {
  const { addons } = usePrivat();
  return key ? addons?.find((a) => a.key === key) : undefined;
}

export function ShopItemPage({ appKey }: { appKey: string }) {
  const t = useT("privat");
  const router = useRouter();
  const { addons, mode } = usePrivat();
  const a = useApp(appKey);
  // An app that is (or was) on opens its own page – also when you come from the shop. Only as the page opens: when
  // the user switches it on here, the «slået til» sheet leads on.
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    if (!a || checked) return;
    setChecked(true);
    if (a.enabled || a.disabled_at) router.replace(appHref(a));
  }, [a, checked, router]);
  if (!a) return <Missing loading={mode === "loading" || addons === undefined} back="/privat/butik" backLabel={t("store.title")} />;
  const name = addonText(t, a, "name");
  return (
    <div className={`${PAGE} xl:grid xl:grid-cols-[minmax(0,1fr)_360px] xl:gap-8 xl:items-start`}>
      <div className="flex flex-col gap-5 min-w-0">
        <Link href="/privat/butik" className={`${LINK} gap-1`}><Ico name="chevron" size={16} className="rotate-180" />{t("store.title")}</Link>
        <header className="flex items-start gap-4">
          <AppTile a={a} size={72} />
          <div className="flex flex-col gap-1.5 min-w-0">
            <h1 className="m-0 font-display font-extrabold text-[30px] leading-tight [overflow-wrap:anywhere]">{name}</h1>
            <p className="m-0 text-[16px] text-ink-soft">{addonText(t, a, "tagline")}</p>
            <span className="flex gap-1.5 flex-wrap"><AppBadge a={a} />{CATEGORIES.includes(a.category as (typeof CATEGORIES)[number]) && <Pill>{t(`apps.cat.${a.category}`)}</Pill>}</span>
          </div>
        </header>
        <AboutApp a={a} />
      </div>
      <ShopAction a={a} />
    </div>
  );
}

/** Byggevejledning order: Hvad den gør (one short paragraph) → Du skal bruge → Sådan virker den (3 steps) → «Hvad må
 *  den?» folded (permissions + what is kept). The example sentence for Peter lives on the app's own page. */
function AboutApp({ a, compact = false }: { a: Addon; compact?: boolean }) {
  const t = useT("privat");
  const name = addonText(t, a, "name");
  const steps = a.steps ?? [];
  return (
    <>
      <section className="flex flex-col gap-1" aria-label={t("store.what")}>
        <Eyebrow>{t("store.what")}</Eyebrow>
        <p className="m-0 text-[17px] leading-normal text-ink-soft max-w-[40rem]">{a.what || addonText(t, a, "description")}</p>
      </section>
      {(a.needs?.length ?? 0) > 0 && !compact && <Needs a={a} />}
      {steps.length > 0 && !compact && (
        <section className="flex flex-col gap-2.5" aria-labelledby={`how-${a.key}`}>
          <h2 id={`how-${a.key}`} className="m-0 eyebrow">{t("apps.how")}</h2>
          <ol className="m-0 p-0 list-none flex flex-col gap-2.5">
            {steps.map((s, i) => <li key={i} className="flex items-center gap-3"><StepSquare n={i + 1} /><span className="text-[16px] [overflow-wrap:anywhere]">{s}</span></li>)}
          </ol>
        </section>
      )}
      {a.permissions.length > 0 && <Permissions a={a} name={name} />}
    </>
  );
}

/** «Hvad må den?» – folded; a chevron shows it opens. Permissions plus the data note (an icon, never a glyph). */
function Permissions({ a, name }: { a: Addon; name: string }) {
  const t = useT("privat");
  return (
    <details className="group rounded-[18px] border-[1.5px] border-ink bg-paper px-4">
      <summary className="cursor-pointer list-none font-semibold text-[15px] min-h-[52px] flex items-center gap-2 [&::-webkit-details-marker]:hidden">
        <span className="flex-1">{t("apps.permissions")}</span><Ico name="chevron" size={18} className="rotate-90 group-open:-rotate-90 transition-transform motion-reduce:transition-none" />
      </summary>
      <ul className="m-0 pb-4 p-0 list-none flex flex-col gap-2">
        {a.permissions.map((x) => <li key={x} className="flex gap-2.5 text-[15px]"><span className="text-accent mt-0.5"><Ico name="check" size={18} stroke={2.6} /></span><span className="min-w-0">{x}</span></li>)}
        <li className="flex gap-2.5 text-[15px] text-ink-soft"><span className="mt-0.5"><Ico name="shield" size={18} /></span><span className="min-w-0">{t("apps.dataKept", { name })}</span></li>
      </ul>
    </details>
  );
}

function Needs({ a }: { a: Addon }) {
  const t = useT("privat");
  return (
    <div className="rounded-[18px] border-[1.5px] border-ink bg-paper p-4 flex flex-col gap-2">
      <Eyebrow>{t("apps.needs")}</Eyebrow>
      <ul className="m-0 p-0 list-none flex flex-wrap gap-2">
        {(a.needs ?? []).map((n) => <li key={n} className="inline-flex items-center gap-1.5 min-h-[36px] px-3 rounded-full bg-panel text-[14px]"><strong className="font-display">1×</strong>{n}</li>)}
      </ul>
    </div>
  );
}

/** The fixed bottom (phone) / sticky card (desktop): price line + «Slå X til», the plan offer, or «Kommer snart». */
function ShopAction({ a }: { a: Addon }) {
  const t = useT("privat");
  const p = usePlan();
  const { mode, api, refresh, openSheet } = usePrivat();
  const [on, setOn] = useState(false);
  const [plan, setPlan] = useState(false);
  const [notified, setNotified] = useState(!!a.notify_requested);
  const name = addonText(t, a, "name");
  const included = addonIncluded(a, p.entitled);
  const priceLine = !a.requires_plan ? t("apps.price.free")
    : p.status === "trial" ? t("apps.price.trial", { plan: p.rightsName }) : p.entitled ? t("apps.price.plan", { plan: p.rightsName }) : t("apps.price.needsPlan");
  let body: React.ReactNode;
  if (a.status === "coming_soon") {
    body = (
      <>
        <p className="m-0 text-[14px] text-ink-soft text-center">{t("apps.soonText")}</p>
        <Button variant="outline" className={`${BIG} rounded-full`} disabled={notified} data-testid="notify-me"
          onClick={async () => { try { await api.addonNotify(a.key); setNotified(true); await refresh(); } catch { setNotified(true); } }}>
          {notified ? <><Ico name="check" size={18} />{t("addons.notified")}</> : t("addons.notify")}</Button>
      </>
    );
  } else if (mode === "demo") {
    body = <><p className="m-0 text-[14px] text-ink-soft text-center">{t("store.demoInstall")}</p><button type="button" className={PRIMARY} onClick={() => openSheet({ kind: "login" })}>{t("apps.loginToEnable")}</button></>;
  } else if (!included) {
    body = <><p className="m-0 text-[14px] text-center"><strong>{t("apps.planIncluded")}</strong> {p.status === "none" ? t("apps.trialDays") : ""}</p><button type="button" className={PRIMARY} onClick={() => setPlan(true)} data-testid="needs-plan">{p.status === "none" ? t("apps.tryFree") : t("apps.choosePlan")}</button></>;
  } else {
    body = <><p className="m-0 text-[14px] text-ink-soft text-center">{priceLine}</p><button type="button" className={PRIMARY} onClick={() => setOn(true)} data-testid="enable-app">{t("apps.enableName", { name })}</button></>;
  }
  return (
    <>
      <div className="fixed xl:sticky inset-x-0 bottom-[calc(64px+env(safe-area-inset-bottom))] xl:bottom-auto xl:top-5 z-30 border-t-2 xl:border-2 border-ink bg-paper px-4 py-3 xl:p-5 xl:rounded-[20px] xl:shadow-block flex flex-col gap-2">
        {(a.needs?.length ?? 0) > 0 && <div className="hidden xl:block"><Needs a={a} /></div>}
        {body}
      </div>
      {on && <EnableSheet a={a} onClose={() => setOn(false)} />}
      {plan && <PlanSheet a={a} onClose={() => setPlan(false)} />}
    </>
  );
}

// ---------------------------------------------------------------- sheets

/** «Slå X til?» – consent to what it may do – then «X er slået til» with step 1 (or straight to the app). */
export function EnableSheet({ a, onClose }: { a: Addon; onClose: () => void }) {
  const t = useT("privat");
  const router = useRouter();
  const p = usePlan();
  const { api, refresh } = usePrivat();
  const [state, setState] = useState<"ask" | "busy" | "done">("ask");
  const [err, setErr] = useState<string | null>(null);
  const [needPlan, setNeedPlan] = useState(false);
  const name = addonText(t, a, "name");
  const steps = a.steps ?? [];
  const go = () => { onClose(); router.push(`/privat/apps/${encodeURIComponent(a.key)}`); };
  const enable = async () => {
    setState("busy"); setErr(null);
    try { await api.enableAddon(a.key); await refresh(); setState("done"); }
    catch (e) {
      const x = e as ApiError;
      setState("ask");
      if (x.code === CONFLICT.needsPlan) setNeedPlan(true); else setErr(x.message);
    }
  };
  if (needPlan) return <PlanSheet a={a} onClose={onClose} />;
  if (state === "done") {
    const kept = !!a.disabled_at;
    return (
      <Sheet title={t("apps.enabledTitle", { name })} onClose={go}>
        <div className="flex items-start gap-3" role="status">
          <span className="w-12 h-12 shrink-0 rounded-full bg-success-soft border-2 border-success text-success inline-flex items-center justify-center"><Ico name="check" size={24} stroke={3} /></span>
          <p className="m-0 text-[16px]">{kept ? t("apps.enabledKept") : t("apps.enabledText")}</p>
        </div>
        {steps.length > 0 && !kept && (
          <div className="rounded-[18px] border-2 border-ink p-3.5 flex flex-col gap-3">
            <div className="flex items-start gap-3"><StepSquare n={1} /><span className="flex flex-col"><Eyebrow>{t("apps.stepOf", { n: 1, total: steps.length })}</Eyebrow><span className="font-semibold text-[16px]">{steps[0]}</span></span></div>
            {(a.needs?.length ?? 0) > 0 && <Needs a={a} />}
          </div>
        )}
        <button type="button" className={PRIMARY} onClick={go} data-autofocus>{steps.length > 0 && !kept ? t("apps.startStep") : t("apps.openApp")}</button>
        <button type="button" className={`${LINK} self-center`} onClick={go}>{t("apps.later")}</button>
      </Sheet>
    );
  }
  return (
    <Sheet title={t("apps.enableAsk", { name })} onClose={onClose}>
      {a.permissions.length > 0 && (
        <div className="flex flex-col gap-2">
          <Eyebrow>{t("apps.permissions")}</Eyebrow>
          <ul className="m-0 p-0 list-none flex flex-col gap-2">{a.permissions.map((x) => <li key={x} className="flex gap-2.5 text-[15px]"><span className="text-accent mt-0.5"><Ico name="check" size={18} stroke={2.6} /></span>{x}</li>)}</ul>
        </div>
      )}
      <p className="m-0 text-[14px] text-ink-soft">{!a.requires_plan ? t("apps.price.free") : p.status === "trial" ? t("apps.price.trialNoExtra") : t("apps.price.plan", { plan: p.rightsName })}</p>
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      <button type="button" className={PRIMARY} onClick={() => void enable()} disabled={state === "busy"} data-testid="enable-confirm" data-autofocus>{state === "busy" ? t("apps.enabling") : t("apps.enable")}</button>
      <button type="button" className={`${LINK} self-center`} onClick={onClose}>{t("apps.notNow")}</button>
    </Sheet>
  );
}

/** «X kræver Plus»: choose Plus or Familie; the checkout carries the app, which comes on once the plan is there. */
export function PlanSheet({ a, onClose, call = false }: { a?: Addon; onClose: () => void; call?: boolean }) {
  const t = useT("privat");
  const locale = useLocale();
  const p = usePlan();
  const { api, mode } = usePrivat();
  const [plan, setPlan] = useState<PlanKey>("plus");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const name = a ? addonText(t, a, "name") : "";
  const choices = p.plans.filter((x) => x.key !== "basis" || (a?.included_in ?? []).includes("basis") || call);
  const go = async () => {
    setBusy(true); setErr(null);
    try { const r = await api.subscriptionCheckout({ plan, interval: "month", locale, app: a?.key }); window.location.href = r.url; }
    catch (e) { setErr((e as ApiError).message); setBusy(false); }
  };
  return (
    <Sheet title={a ? t("apps.planTitle", { name }) : t("store.needsPlan.callTitle")} onClose={onClose}>
      <Eyebrow>{t("apps.planEyebrow")}</Eyebrow>
      <p className="m-0 text-[15px] leading-normal">{p.status === "none" ? t("apps.planTextTrial", { name: name || t("apps.calls") }) : t("apps.planTextEnded", { name: name || t("apps.calls") })}</p>
      <div role="radiogroup" aria-label={t("apps.planChoice")} className="flex flex-col gap-2.5">
        {choices.map((x) => (
          <button key={x.key} type="button" role="radio" aria-checked={plan === x.key} onClick={() => setPlan(x.key)}
            className={`w-full flex items-center gap-3 text-left rounded-[18px] border-2 border-ink bg-paper p-3.5 ${plan === x.key ? "shadow-block-highlight" : ""}`}>
            <span className={`w-6 h-6 rounded-full border-2 border-ink inline-flex items-center justify-center shrink-0`} aria-hidden>{plan === x.key && <span className="w-3 h-3 rounded-full bg-accent" />}</span>
            <span className="flex-1 min-w-0 flex flex-col"><span className="font-semibold text-[16px] flex items-center gap-2">{x.name}{x.recommended && <Pill tone="highlight">{t("apps.recommended")}</Pill>}</span>
              <span className="text-[13px] text-ink-soft">{t("apps.planFacts", { calls: x.calls, people: x.people })}</span></span>
            <span className="font-display font-extrabold text-[18px] whitespace-nowrap">{p.fmt(x.monthly_minor)}<span className="font-body font-normal text-[13px] text-ink-soft">{t("apps.perMonth")}</span></span>
          </button>
        ))}
      </div>
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      <button type="button" className={PRIMARY} onClick={() => void go()} disabled={busy || mode === "demo"} data-testid="plan-go">{p.status === "none" ? t("apps.startTrial") : t("apps.choosePlan")}</button>
      {a && <p className="m-0 text-[13px] text-ink-soft text-center">{t("apps.planAfter", { name })}</p>}
      <button type="button" className={`${LINK} self-center`} onClick={onClose}>{t("apps.notNow")}</button>
    </Sheet>
  );
}

/** «Slå X fra?» – what stops, what is kept, which apps go off with it. Primary = Slå fra (the user asked for it);
 *  afterwards a Fortryd toast for 8 s. The sheet stays open when the request fails. */
export function DisableSheet({ a, onClose }: { a: Addon; onClose: () => void }) {
  const t = useT("privat");
  const router = useRouter();
  const { api, refresh, addons, showToast } = usePrivat();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const name = addonText(t, a, "name");
  const alsoOff = (addons ?? []).filter((x) => x.enabled && x.requires.includes(a.key));
  const sharing = a.key === ADDON.sharedLists || a.key === ADDON.wishlists;
  const stops = [sharing ? t("apps.off.stopsSharing") : t("apps.off.stopsReminders", { name }), t("apps.off.stopsPeter", { app: name }),
    ...alsoOff.map((x) => t("apps.off.alsoOff", { name: addonText(t, x, "name") }))];
  const kept = [sharing ? t("apps.off.keptLists") : t("apps.off.keptData", { name }), t("apps.off.keptBack")];
  const off = async () => {
    setBusy(true); setErr(null);
    try {
      await api.disableAddon(a.key);
      await refresh();
      onClose();
      router.push("/privat/apps");
      showToast({ text: t("apps.off.toast", { name }), actionLabel: t("apps.off.undo"), action: async () => { await api.enableAddon(a.key); for (const x of alsoOff) await api.enableAddon(x.key); await refresh(); showToast(null); } });
    } catch (e) { setErr((e as ApiError).message); setBusy(false); }
  };
  return (
    <Sheet title={t("apps.off.title", { name })} onClose={onClose}>
      <Eyebrow>{t("apps.off.stops")}</Eyebrow>
      <ul className="m-0 p-0 list-none flex flex-col gap-2">{stops.map((x) => <li key={x} className="flex gap-2.5 text-[15px]"><span className="text-danger mt-0.5"><Ico name="close" size={18} stroke={2.6} /></span>{x}</li>)}</ul>
      <Eyebrow>{t("apps.off.kept")}</Eyebrow>
      <ul className="m-0 p-0 list-none flex flex-col gap-2">{kept.map((x) => <li key={x} className="flex gap-2.5 text-[15px]"><span className="text-success mt-0.5"><Ico name="check" size={18} stroke={2.6} /></span>{x}</li>)}</ul>
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      <button type="button" className={PRIMARY} onClick={() => void off()} disabled={busy} data-testid="disable-confirm">{busy ? t("apps.off.busy") : t("apps.off.confirm", { name })}</button>
      <button type="button" className={`${LINK} self-center`} onClick={onClose} data-autofocus>{t("apps.off.keep")}</button>
      {a.data_deletable && <p className="m-0 text-[13px] text-ink-soft text-center">{t("apps.off.deleteHint")}</p>}
    </Sheet>
  );
}

/** The 8-second message at the bottom («X er slået fra. Dine data er gemt.» + Fortryd). */
export function Toast() {
  const { toast, showToast } = usePrivat();
  if (!toast) return null;
  return (
    <div role="status" aria-live="polite" className="fixed inset-x-4 bottom-[calc(80px+env(safe-area-inset-bottom))] xl:bottom-6 xl:left-auto xl:right-6 xl:w-[420px] z-[60] rounded-[16px] bg-ink text-paper px-4 py-3 flex items-center gap-3 shadow-block-sm" data-testid="toast">
      <span className="flex-1 min-w-0 text-[15px]">{toast.text}</span>
      {toast.action && <button type="button" className="min-h-[44px] px-3 rounded-full border-2 border-paper font-semibold text-[14px] hover:bg-paper hover:text-ink" onClick={() => void toast.action?.()}>{toast.actionLabel}</button>}
      <button type="button" aria-label="Luk" className="w-9 h-9 inline-flex items-center justify-center" onClick={() => showToast(null)}><Ico name="close" size={16} /></button>
    </div>
  );
}

// ---------------------------------------------------------------- an app's own page

const PANELS: Record<string, () => React.ReactNode> = {
  kalender: () => <CalendarPanel />, foedselsdage: () => <BirthdaysPanel />, regninger: () => <BillsPanel />, madplan: () => <MealsPanel />,
  "laege-og-tandlaege": () => <HealthPanel />, "bil-og-syn": () => <CarPanel />, pakker: () => <ParcelsPanel />, rejser: () => <TravelPanel />,
};

function Missing({ loading, back, backLabel }: { loading: boolean; back: string; backLabel: string }) {
  const t = useT("privat");
  return (
    <div className={PAGE}>
      <Link href={back} className={`${LINK} gap-1`}><Ico name="chevron" size={16} className="rotate-180" />{backLabel}</Link>
      {loading ? <Loading /> : <p role="alert" className="m-0 text-[15px]">{t("apps.unknown")}</p>}
    </div>
  );
}

export function AppPage({ appKey }: { appKey: string }) {
  const t = useT("privat");
  const f = useFmt();
  const router = useRouter();
  const { addons, mode, api, refresh, setDraft, go } = usePrivat();
  const p = usePlan();
  const a = useApp(appKey);
  const [off, setOff] = useState(false);
  const [enable, setEnable] = useState(false);
  const [plan, setPlan] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [del, setDel] = useState(false);
  // Never on and nothing kept: this app belongs in the shop (checked as the page opens).
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    if (!a || checked) return;
    setChecked(true);
    if (!a.enabled && !a.disabled_at) router.replace(`/privat/butik/${encodeURIComponent(a.key)}`);
  }, [a, checked, router]);
  const name = a ? addonText(t, a, "name") : "";
  const ask = (text?: string) => { if (text) setDraft(text.replace(/^«|»$/g, "")); go("chat"); setTimeout(() => document.getElementById("privat-ask")?.focus(), 80); };
  const panel = useMemo(() => (a ? (PANELS[a.key] ?? (HOUSEHOLD_APPS.has(a.key) ? () => <HouseholdPanel appKey={a.key} name={a.name} /> : null)) : null), [a]);
  if (!a) return <Missing loading={mode === "loading" || addons === undefined} back="/privat/apps" backLabel={t("apps.mine")} />;
  const step = async (done: number) => {
    setBusy(true); setErr(null);
    try { await api.addonSetup(a.key, done); await refresh(); } catch (e) { setErr((e as ApiError).message); } finally { setBusy(false); }
  };
  const deleteData = async () => {
    setBusy(true); setErr(null);
    try { await api.deleteAddonData(a.key); await refresh(); router.push("/privat/butik"); } catch (e) { setErr((e as ApiError).message); } finally { setBusy(false); setDel(false); }
  };
  const back = <Link href="/privat/apps" className={`${LINK} gap-1`}><Ico name="chevron" size={16} className="rotate-180" />{t("apps.mine")}</Link>;
  const head = (
    <header className="flex items-center gap-4">
      <AppTile a={a} size={64} />
      <div className="flex flex-col gap-1 min-w-0">
        <h1 className="m-0 font-display font-extrabold text-[30px] leading-tight [overflow-wrap:anywhere]">{name}</h1>
        <span className="flex items-center gap-2 flex-wrap text-[14px] text-ink-soft">
          {a.enabled ? <AppBadge a={a} /> : <Pill tone="soon">{t("apps.keptPill")}</Pill>}
        </span>
      </div>
    </header>
  );
  if (!a.enabled) {
    // Switched off, data kept: read what is there, switch on again (or the plan offer), or delete the data.
    const included = addonIncluded(a, p.entitled);
    return (
      <div className={PAGE} data-testid="app-kept">
        {back}{head}
        <div className="rounded-[20px] border-2 border-dashed border-ink bg-panel p-4 flex flex-col gap-2.5">
          <p className="m-0 font-display font-bold text-[19px]">{t("apps.keptTitle")}</p>
          <p className="m-0 text-[15px] text-ink-soft">{t("apps.keptText", { name, date: a.disabled_at ? f.date(a.disabled_at) : "" })}</p>
          {mode === "demo" ? null : included
            ? <button type="button" className={PRIMARY} onClick={() => setEnable(true)} data-testid="enable-again">{t("apps.enableAgain")}</button>
            : <button type="button" className={PRIMARY} onClick={() => setPlan(true)}>{p.status === "none" ? t("apps.tryFree") : t("apps.choosePlan")}</button>}
        </div>
        <AboutApp a={a} compact />
        {a.data_deletable && mode !== "demo" && (
          <section className="flex flex-col gap-2 border-t-[1.5px] border-line pt-4">
            <h2 className="m-0 text-[16px] font-semibold">{t("apps.deleteTitle")}</h2>
            <p className="m-0 text-[14px] text-ink-soft">{t("apps.deleteText", { name })}</p>
            {!del ? <Button variant="outline" className="self-start border-2 rounded-full" onClick={() => setDel(true)}>{t("apps.deleteData")}</Button> : (
              <div role="alert" className="rounded-[14px] border-2 border-danger p-3 flex flex-col gap-2">
                <p className="m-0 text-[14px] font-semibold">{t("apps.deleteConfirm", { name })}</p>
                <div className="flex gap-2 flex-wrap">
                  <button type="button" className="inline-flex items-center min-h-[44px] px-4 rounded-full border-2 border-danger bg-danger text-white font-semibold" onClick={() => void deleteData()} disabled={busy}>{t("apps.deleteYes")}</button>
                  <Button variant="outline" className="border-2 rounded-full" onClick={() => setDel(false)}>{t("wish.cancel")}</Button>
                </div>
              </div>
            )}
          </section>
        )}
        {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
        {enable && <EnableSheet a={a} onClose={() => setEnable(false)} />}
        {plan && <PlanSheet a={a} onClose={() => setPlan(false)} />}
      </div>
    );
  }
  const steps = a.steps ?? [];
  const done = a.setup?.done ?? steps.length;
  const hasPanel = !!panel && mode !== "demo";
  const setupLeftNow = done < steps.length;
  const stepActions = (
    <div className="flex items-center gap-x-4 gap-y-1 flex-wrap">
      <button type="button" className={LINK} disabled={busy} onClick={() => void step(done + 1)} data-testid="step-done">{done + 1 === steps.length ? t("apps.stepFinish") : t("apps.stepDone")}</button>
      <button type="button" className={`${LINK} !text-ink-soft`} onClick={() => void step(steps.length)} disabled={busy}>{t("apps.skipSetup")}</button>
    </div>
  );
  // ux-audit #7: an app with a panel shows YOUR things first and the setup as one yellow line; an app without a panel
  // keeps the step card. One orange button per screen: «Spørg Peter» on the step card, otherwise the panel's own.
  return (
    <div className="w-full max-w-[760px] mx-auto px-4 pt-5 pb-28 xl:pb-10 flex flex-col gap-5" data-testid="app-page">
      {back}{head}
      {hasPanel ? (
        <>
          {setupLeftNow && (
            <section className="rounded-[14px] border-[1.5px] border-ink bg-highlight px-3.5 py-2.5 flex flex-col gap-1" aria-labelledby="setup-h" data-testid="app-setup">
              <p id="setup-h" className="m-0 text-[15px] leading-snug"><b>{t("apps.stepOf", { n: done + 1, total: steps.length })}:</b> {steps[done]}</p>
              {stepActions}
            </section>
          )}
          <section className="flex flex-col gap-3" aria-labelledby="settings-h">
            <h2 id="settings-h" className="sr-only">{t("apps.settings")}</h2>
            {panel!()}
          </section>
          <Button variant="outline" className="rounded-full self-start" onClick={() => ask(a.example)}>{t("apps.ask")}</Button>
        </>
      ) : setupLeftNow ? (
        <section className="rounded-[20px] border-2 border-ink bg-paper shadow-block p-4 flex flex-col gap-3" aria-labelledby="setup-h" data-testid="app-setup">
          <div className="flex items-start gap-3"><StepSquare n={done + 1} size={48} /><span className="flex flex-col"><Eyebrow>{t("apps.stepOf", { n: done + 1, total: steps.length })}</Eyebrow><span id="setup-h" className="font-display font-bold text-[19px] leading-snug">{steps[done]}</span></span></div>
          {done === 0 && (a.needs?.length ?? 0) > 0 && <Needs a={a} />}
          <Button className={`${BIG} rounded-full`} onClick={() => ask(a.example)}>{t("apps.ask")}</Button>
          {a.example && <p className="m-0 text-[14px] text-ink-soft">{t("apps.sayLike", { example: a.example.replace(/^«|»$/g, "") })}</p>}
          {stepActions}
        </section>
      ) : (
        <section className="rounded-[20px] border-2 border-ink bg-paper shadow-block p-4 flex flex-col gap-2.5" aria-labelledby="next-h" data-testid="app-next">
          <Eyebrow>{t("apps.next")}</Eyebrow>
          <p id="next-h" className="m-0 font-display font-extrabold text-[24px] leading-tight [overflow-wrap:anywhere]">{a.summary_line ?? addonText(t, a, "tagline")}</p>
          <Button className={`${BIG} rounded-full`} onClick={() => ask(a.example)}>{t("apps.ask")}</Button>
          {a.example && <p className="m-0 text-[14px] text-ink-soft">{t("apps.sayLike", { example: a.example.replace(/^«|»$/g, "") })}</p>}
        </section>
      )}
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      {a.permissions.length > 0 && <Permissions a={a} name={name} />}
      {mode !== "demo" && (
        <div className="flex items-center gap-3 flex-wrap border-t-[1.5px] border-line pt-4">
          <p className="m-0 flex-1 min-w-[12rem] text-[14px] text-ink-soft">{t("apps.offText")}</p>
          <Button variant="outline" className="border-2 rounded-full" onClick={() => setOff(true)} data-testid="disable-app">{t("addons.disable")}</Button>
        </div>
      )}
      {off && <DisableSheet a={a} onClose={() => setOff(false)} />}
    </div>
  );
}

// ---------------------------------------------------------------- Min dag

/** «Dine apps» on Min dag: the app with a setup step first (yellow), then what the apps hold. Only when the user has
 *  switched on more than the default apps. */
export function AppsStrip() {
  const t = useT("privat");
  const { addons } = usePrivat();
  const on = (addons ?? []).filter((a) => a.enabled);
  if (!on.some((a) => !DEFAULT_APPS.has(a.key))) return null;
  const sorted = [...on.filter(setupLeft), ...on.filter((a) => !setupLeft(a))];
  return (
    <section className="flex flex-col gap-3" aria-labelledby="day-apps" data-testid="day-apps">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="day-apps" className="m-0 font-display font-extrabold text-[24px]">{t("apps.yourApps")}</h2>
        <Link href="/privat/apps" className={LINK}>{t("apps.all", { n: on.length })}</Link>
      </div>
      <ul className="m-0 p-0 list-none flex gap-3 overflow-x-auto -mx-4 px-4 pb-2 snap-x">
        {sorted.map((a) => {
          const s = setupLeft(a);
          return (
            <li key={a.key} className="snap-start shrink-0 w-[168px]">
              <Link href={appHref(a)} className={`h-full flex flex-col gap-2 rounded-[18px] border-2 border-ink p-3 no-underline text-ink ${s ? "bg-highlight" : "bg-paper hover:bg-panel"}`}>
                <AppTile a={a} size={36} />
                <span className="font-semibold text-[15px] leading-tight">{addonText(t, a, "name")}</span>
                <span className="text-[13px] text-ink-soft leading-snug line-clamp-3">{s ? t("apps.stripStep", { n: (a.setup?.done ?? 0) + 1, total: a.setup?.total ?? 0 }) : a.summary_line ?? addonText(t, a, "tagline")}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
