"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import { currencyFor } from "@/lib/markets";
import { BIG, Eyebrow, LINK, Pill, Sim } from "./bits";
import { PhoneVerify } from "./cards";
import { PushPrompt } from "./push";
import { InstallApp } from "@/components/install-app";
import { LanguageSwitcher } from "@/components/language-switcher";
import { enablePush } from "@/lib/privat/push";
import { Ico, Tile } from "./icons";
import { useFmt, usePlan, usePrivat } from "./store";
import { bareLink, smsHref, platformOf } from "@/lib/privat/sms";
import { CONFLICT, type BillingInterval, type PlanKey, type ShareResult } from "@/lib/privat/api";
import type { ApiError } from "@/lib/client";

const PLAN_KEYS: PlanKey[] = ["basis", "plus", "familie"];
const isPlanKey = (v: string | null): v is PlanKey => !!v && (PLAN_KEYS as string[]).includes(v);

export function AccountPane() {
  const t = useT("privat");
  const f = useFmt();
  const { balance, ledger, session, mode, simulated, fake, run, note, setNote, openSheet, go, loggedIn, api, refresh, setSubscription, setError, addons } = usePrivat();
  const p = usePlan();
  const locale = useLocale();
  const params = useSearchParams();
  const router = useRouter();
  const [changing, setChanging] = useState(false);
  const [picker, setPicker] = useState(false);
  const [redirecting, setRedirecting] = useState(false);
  const handled = useRef<string | null>(null);
  // Credits checkout return (unchanged) and the subscription flows: ?abonnement=ok&session_id= (synchronise, then
  // «Dit abonnement er aktivt»), ?abonnement=annulleret, ?portal=simuleret, and ?plan=&interval= (start the checkout).
  useEffect(() => {
    const c = params.get("checkout");
    if (c === "success") setNote(t("account.purchasedReal"));
    if (c === "cancel") setNote(t("account.purchaseCancelled"));
  }, [params, setNote, t]);
  useEffect(() => {
    if (mode === "loading") return;
    if (mode === "demo") {
      // An anonymous visitor (demo account) who came to pay (?plan= from «Prøv gratis i 14 dage» or a plan card):
      // sign up first, then back here to the checkout. Without ?plan= the demo stays as it is (QA F-PQ-02-X07).
      const key = params.toString();
      if (isPlanKey(params.get("plan")) && handled.current !== `signup:${key}`) {
        handled.current = `signup:${key}`;
        window.location.assign(`/signup?next=${encodeURIComponent(`/privat/konto?${key}`)}`);
      }
      return;
    }
    const key = params.toString();
    if (!key || handled.current === key) return;
    const ab = params.get("abonnement");
    const sid = params.get("session_id");
    const plan = params.get("plan");
    const interval = params.get("interval") === "year" ? "year" : "month";
    const clean = () => router.replace("/privat/konto");
    if (ab === "ok") {
      handled.current = key;
      (async () => {
        const app = params.get("app");
        // «aktivt» only when the backend says the plan's rights are there (it read the session from Stripe): a declined
        // card, an abandoned checkout or a bookmarked success link lands here too
        try { const sb = await api.subscription(sid ?? undefined, currencyFor(locale)); setSubscription(sb); await refresh(); setNote(sb.entitled ? t("plan.activated") : t("plan.notCompleted")); }
        catch (e) { setError(e as ApiError); }
        // «Kræver plan» from an app: the backend switched that app on with the plan – land on it.
        if (app && /^[a-z0-9-]{2,40}$/.test(app)) router.replace(`/privat/apps/${app}`); else clean();
      })();
    } else if (ab === "annulleret") { handled.current = key; setNote(t("plan.cancelled")); clean(); }
    else if (params.get("portal") === "simuleret") { handled.current = key; setNote(t("plan.portalSimulated")); clean(); }
    else if (isPlanKey(plan)) {
      // From the landing page's plan cards: straight on to the payment once logged in. Without a login the real site
      // goes directly to the Privat sign-up (no sheet in between), which comes back here with the same query and
      // starts the checkout; fake mode keeps the sheet with its simulated login.
      if (!loggedIn) {
        if (handled.current === `login:${key}`) return;
        handled.current = `login:${key}`;
        if (mode === "fake") openSheet({ kind: "login" });
        else window.location.assign(`/signup?next=${encodeURIComponent(`/privat/konto?${key}`)}`);
        return;
      }
      handled.current = key;
      void startCheckout(plan, interval);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, mode, loggedIn]);
  const startCheckout = async (plan: PlanKey, interval: BillingInterval, code?: string) => {
    if (!loggedIn) { openSheet({ kind: "login" }); return; }
    setRedirecting(true); setError(null);
    const kode = (code ?? params.get("kode") ?? "").trim();
    try { const { url } = await api.subscriptionCheckout({ plan, interval, locale, ...(kode ? { code: kode } : {}) }); window.location.href = url; }
    catch (e) { setError(e as ApiError); setRedirecting(false); }
  };
  // Without a plan (the trial included) the three plans are open from the start – one tap to the payment; the button
  // folds them away. With a plan they open on «Skift plan», ?planer=1 or ?plan=….
  const [hidden, setHidden] = useState(false);
  const pickerOpen = (p.plan === "none" && !hidden && mode !== "demo") || picker || params.get("planer") === "1" || isPlanKey(params.get("plan"));
  const togglePicker = () => {
    if (pickerOpen && params.get("planer") === "1") router.replace("/privat/konto");
    if (p.plan === "none") setHidden(pickerOpen); else setPicker(!pickerOpen);
  };
  const portal = async () => {
    setError(null);
    try { const { url } = await api.subscriptionPortal(); if (simulated) setNote(t("plan.portalSimulated")); else window.location.href = url; }
    catch (e) { const x = e as ApiError; if (x.code === CONFLICT.notConfigured || x.status === 501) setNote(t("plan.portalMissing")); else setError(x); }
  };
  const line = mode === "demo" ? t("account.exampleLine") : loggedIn ? t("account.privateLine", { email: session.email ?? (simulated ? "mette@eksempel.dk" : "") }) : t("account.exampleLine");
  const amount = (kind: string, n: number) => kind === "sponsor" ? t("account.oneTask") : `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)}${kind === "reserve" ? ` ${t("account.reservedSuffix")}` : ""}`;
  // Before the data is in (the server-rendered copy and the first client frame) only the heading: no «Ingen plan»
  // card that is wrong for a second and, on a slow machine, sits next to the real one while hydration settles.
  if (mode === "loading") {
    return (
      <div className="px-4 pt-5 pb-7 flex flex-col gap-[18px]" aria-label={t("account.title")} aria-busy="true">
        <h2 className="m-0 font-display font-extrabold text-[28px] tracking-[-0.5px]">{t("account.title")}</h2>
        <p className="m-0 text-[14px] text-muted" role="status">{t("common.loading")}</p>
      </div>
    );
  }
  return (
    <div className="px-4 pt-5 pb-7 flex flex-col gap-[18px]" aria-label={t("account.title")}>
      <h2 className="m-0 font-display font-extrabold text-[28px] tracking-[-0.5px]">{t("account.title")}</h2>
      <p className="m-0 text-[14px] text-ink-soft [overflow-wrap:anywhere]">{line}</p>
      {simulated && <p className="m-0 text-[13px] flex gap-2 items-center flex-wrap"><Sim />{t("account.simulatedLine")}</p>}
      {note && <p className="m-0 rounded-[18px] border-2 border-success bg-success-soft px-4 py-3 text-[15px] font-semibold text-success" role="status" data-testid="account-note">{note}</p>}

      {/* Subscription */}
      <section className="rounded-[24px] border-2 border-ink bg-paper p-5 shadow-block flex flex-col gap-3" aria-labelledby="sub-h" data-testid="subscription-card">
        <div className="flex items-start gap-2 flex-wrap">
          <div className="flex-1 min-w-0 flex flex-col gap-1">
            <Eyebrow>{t("plan.title")}</Eyebrow>
            <h3 id="sub-h" className="m-0 font-display font-extrabold text-[26px] leading-tight">{p.entitled ? p.rightsName : t(`plan.status.${p.status}`)}</h3>
          </div>
          <Pill tone={p.status === "active" ? "ok" : p.status === "trial" ? "highlight" : p.status === "past_due" ? "beta" : "plain"}>{t(`plan.status.${p.status}`)}</Pill>
        </div>
        {p.status === "trial" && <p className="m-0 text-[15px]">{t("plan.trialLine", { n: p.trialDays })} <span className="text-ink-soft">{p.plan === "none" ? t("plan.trialThenNone") : t("plan.trialThen", { plan: p.rightsName, price: p.monthlyText(p.rightsKey) })}</span></p>}
        {p.status === "expired" && <p className="m-0 text-[15px] text-ink-soft">{t("plan.expiredLine")}</p>}
        {p.status === "none" && <p className="m-0 text-[15px] text-ink-soft">{t("plan.noneLine")}</p>}
        {p.status === "past_due" && <p className="m-0 text-[15px] text-danger font-semibold">{t("plan.pastDue")}</p>}
        {p.status === "active" && p.periodEnd && <p className="m-0 text-[14px] text-ink-soft" suppressHydrationWarning>{p.cancelAtPeriodEnd ? t("plan.cancelAtEnd", { date: f.date(p.periodEnd) }) : t("plan.renews", { date: f.date(p.periodEnd) })}</p>}
        {p.entitled && (
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between text-[14px]"><span>{t("plan.calls")}</span><strong data-testid="calls-used">{t("plan.callsUsed", { used: p.callsUsed, quota: p.callsQuota })}</strong></div>
            <div className="h-3 border-2 border-ink rounded-full overflow-hidden bg-paper" role="progressbar" aria-valuemin={0} aria-valuemax={p.callsQuota} aria-valuenow={p.callsUsed} aria-label={t("plan.callsBarAria", { used: p.callsUsed, quota: p.callsQuota })}>
              <div className="h-full bg-accent" style={{ width: `${p.callsQuota ? Math.min(100, (p.callsUsed / p.callsQuota) * 100) : 0}%` }} />
            </div>
            <p className="m-0 text-[13px] text-muted">{t("plan.unlimited")}</p>
          </div>
        )}
        <div className="flex gap-2 flex-wrap">
          {p.plan === "none"
            ? <Button className={`${BIG} rounded-full`} onClick={togglePicker} aria-expanded={pickerOpen} disabled={mode === "demo"}>{pickerOpen ? t("plan.hidePicker") : t("plan.choose")}</Button>
            : <>
              <Button variant="outline" className="border-2 rounded-full" onClick={togglePicker} aria-expanded={pickerOpen}>{pickerOpen ? t("plan.hidePicker") : t("plan.change")}</Button>
              <Button variant="outline" className="border-2 rounded-full" onClick={portal}>{t("plan.manage")}</Button>
            </>}
        </div>
        {pickerOpen && <PlanPicker onPick={startCheckout} busy={redirecting} />}
      </section>

      {!p.entitled && (
        <div className="rounded-[20px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5" data-testid="free-tier">
          <Eyebrow>{t("account.free")}</Eyebrow>
          <p className="m-0 text-[15px] text-ink-soft">{t("account.freeNote")}</p>
        </div>
      )}

      {/* Credits = «Ekstra opkald» */}
      <div className="rounded-[20px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5">
        <Eyebrow>{t("plan.extra")}</Eyebrow>
        <div className="flex items-baseline gap-2.5 flex-wrap">
          <span className="font-display font-extrabold text-[36px]" data-testid="credits">{balance?.credits ?? 0}</span><span className="text-[15px] text-ink-soft">{t("plan.extraWord")}</span>
          {(balance?.reserved ?? 0) > 0 && <Pill tone="progress">{t("account.reserved", { n: balance!.reserved })}</Pill>}
        </div>
        <p className="m-0 text-[13px] text-muted">{t("plan.extraNote")}</p>
        <Button variant={p.entitled ? "outline" : "primary"} className={`${BIG} rounded-full self-start`} onClick={() => openSheet({ kind: "buy" })} disabled={mode === "demo"}>{t("account.buy")}</Button>
      </div>

      <section className="flex flex-col gap-1.5" aria-labelledby="ledger-h">
        <h3 id="ledger-h" className="m-0 font-body text-[15px] font-semibold">{t("account.ledger")}</h3>
        {ledger.length === 0 && <p className="m-0 text-[14px] text-muted">{t("account.ledgerEmpty")}</p>}
        <ul className="m-0 p-0 list-none" data-testid="ledger">
          {[...ledger].reverse().map((l) => (
            <li key={l.id} className="flex gap-2.5 justify-between border-b-[1.5px] border-line py-2 text-[14px]"><span className="[overflow-wrap:anywhere] min-w-0">{l.text}</span><span className="font-bold whitespace-nowrap">{amount(l.kind, l.amount)}</span></li>
          ))}
        </ul>
      </section>

      {mode !== "demo" && (
        <section className="rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5" aria-labelledby="phone-h">
          <h3 id="phone-h" className="m-0 font-display font-bold text-[19px]">{t("account.phone")}</h3>
          {balance?.phone_verified && !changing ? (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[17px] font-semibold">{balance.phone_display}</span><Pill tone="ok">{t("account.verified")}</Pill>
              <button type="button" className={LINK} onClick={() => setChanging(true)}>{t("account.changePhone")}</button>
            </div>
          ) : (
            <>
              {!balance?.phone_verified && <p className="m-0 text-[14px] text-ink-soft">{t("account.phoneNone")}</p>}
              <PhoneVerify onDone={() => setChanging(false)} />
            </>
          )}
        </section>
      )}

      <section className="rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5" aria-labelledby="lang-h">
        <h3 id="lang-h" className="m-0 font-display font-bold text-[19px]">{t("account.languageTitle")}</h3>
        <p className="m-0 text-[14px] text-ink-soft">{t("account.languageText")}</p>
        <LanguageSwitcher className="self-start" onSaved={(l) => { if (mode === "real") api.setLocale(l).catch(() => {}); }} />
      </section>

      <section className="rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5" aria-labelledby="install-h">
        <h3 id="install-h" className="m-0 font-display font-bold text-[19px]">{t("account.installTitle")}</h3>
        <InstallApp audience="privat" enableNotifications={() => enablePush(api).then(() => refresh())} />
      </section>

      <section className="rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5" aria-labelledby="notif-h">
        <h3 id="notif-h" className="m-0 font-display font-bold text-[19px]">{t("push.title")}</h3>
        <PushPrompt moment="account" />
      </section>

      {mode !== "demo" && <><CityRow /><AssistantNameRow /></>}

      <InviteFriends />

      <Link href="/privat/apps" className="rounded-[20px] border-2 border-ink bg-paper p-4 flex items-center gap-3 no-underline text-ink hover:bg-panel" data-testid="account-apps">
        <Tile name="grid" className="bg-accent text-white rounded-[12px] border-2 border-ink" />
        <span className="flex-1 min-w-0 text-[16px] font-semibold">{t("apps.accountLine", { n: (addons ?? []).filter((a) => a.enabled).length })}</span>
        <span className="text-[15px] font-semibold text-accent whitespace-nowrap">{t("apps.mine")} →</span>
      </Link>

      {simulated && fake && (
        <div className="rounded-[14px] border-[1.5px] border-dashed border-ink bg-panel p-3 flex flex-col gap-2">
          <Eyebrow>{t("account.tools")}</Eyebrow>
          <div className="flex gap-2 flex-wrap">
            <Button variant="outline" onClick={() => run(() => fake.startFree())}>{t("account.startFree")}</Button>
            <Button variant="outline" onClick={() => run(() => fake.endTrial())}>{t("plan.endTrial")}</Button>
            <Button variant="outline" onClick={async () => { const r = await run(() => fake.repeatPayment()); if (r) setNote(r.ref ? t("account.repeatNote", { ref: r.ref }) : t("account.repeatNone")); }}>{t("account.repeatPay")}</Button>
            <Button variant="outline" onClick={() => run(() => fake.emptyDay())}>{t("account.emptyDay")}</Button>
            <Button variant="outline" onClick={async () => { await run(() => fake.reset()); setNote(""); }}>{t("account.reset")}</Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Plan picker: Månedligt / Årligt · spar 20 % and the three plan cards (Plus = Anbefalet). A pick starts Stripe Checkout. */
/** Plan features arrive as i18n keys from the local catalogue (landing.pricing.features.*) or as finished Danish text
 *  from the API; keys are translated, text is shown as it is. */
function featureText(t: (k: string, p?: Record<string, string | number>) => string, x: string, pl: { calls: number; people: number }): string {
  if (/\s/.test(x)) return x;
  if (x === "calls") return t("landing.pricing.features.calls", { n: pl.calls });
  if (x === "people") return t("landing.pricing.features.people", { n: pl.people });
  return t(`landing.pricing.features.${x}`);
}

function PlanPicker({ onPick, busy }: { onPick: (plan: PlanKey, interval: BillingInterval, code?: string) => void; busy: boolean }) {
  const t = useT("privat");
  const params = useSearchParams();
  const p = usePlan();
  const { error } = usePrivat();
  const [interval, setInterval] = useState<BillingInterval>(params.get("interval") === "year" ? "year" : "month");
  // A discount code (operator-made): from ?kode= in a campaign link, or typed here. Applied on the Stripe page.
  const [code, setCode] = useState(params.get("kode") ?? "");
  const [codeOpen, setCodeOpen] = useState(!!params.get("kode"));
  const codeError = error?.field_errors?.find((f) => f.field === "code") ? error.message : null;
  return (
    <div className="flex flex-col gap-3 pt-2 border-t-[1.5px] border-line" data-testid="plan-picker">
      <p className="m-0 font-display font-bold text-[18px]">{t("plan.pickerTitle")}</p>
      <div role="group" aria-label={t("plan.monthly")} className="grid grid-cols-2 gap-1 p-1 rounded-full border-2 border-ink self-start">
        {(["month", "year"] as BillingInterval[]).map((iv) => (
          <button key={iv} type="button" aria-pressed={interval === iv} onClick={() => setInterval(iv)}
            className={`min-h-[38px] px-4 rounded-full text-[14px] font-semibold whitespace-nowrap ${interval === iv ? "bg-ink text-paper" : "hover:bg-panel"}`}>{t(iv === "month" ? "plan.monthly" : "plan.yearly")}</button>
        ))}
      </div>
      <ul className="m-0 p-0 list-none grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
        {p.plans.map((pl) => {
          const current = p.plan === pl.key;
          const price = interval === "year" ? pl.yearly_monthly_minor : pl.monthly_minor;
          return (
            <li key={pl.key} className={`relative rounded-[20px] border-2 p-4 flex flex-col gap-2 ${pl.recommended ? "border-accent bg-accent-soft shadow-block-sm" : "border-ink bg-paper"}`} data-testid={`plan-${pl.key}`}>
              {pl.recommended && <span className="absolute -top-3 left-4 inline-flex items-center min-h-6 px-2.5 rounded-full border-[1.5px] border-ink bg-accent text-white text-[11px] font-bold uppercase tracking-[0.06em]">{t("plan.recommended")}</span>}
              <div className="flex items-baseline gap-2 flex-wrap mt-1">
                <span className="font-display font-extrabold text-[20px]">{pl.name}</span>
                {current && <Pill tone="ok">{t("plan.currentPlan")}</Pill>}
              </div>
              <div className="flex flex-col"><span className="font-display font-extrabold text-[28px] leading-none">{t("plan.perMonth", { price: p.fmt(price) })}</span>
                <span className="text-[12px] text-muted">{interval === "year" ? t("plan.yearlyNote", { total: p.fmt(pl.yearly_total_minor) }) : t("plan.monthlyNote")}</span></div>
              <ul className="m-0 p-0 list-none flex flex-col gap-1">
                {pl.features.map((x) => <li key={x} className="flex gap-2 text-[14px]"><span className="text-accent mt-0.5"><Ico name="check" size={16} /></span><span>{featureText(t, x, pl)}</span></li>)}
              </ul>
              <Button className={`mt-1 rounded-full border-2 border-ink ${pl.recommended ? "" : "!bg-paper !text-ink hover:!bg-panel"}`} disabled={busy || (current && p.status === "active")} onClick={() => onPick(pl.key, interval, code.trim() || undefined)}>
                {busy ? t("plan.redirecting") : p.status === "none" ? t("plan.startTrial") : t("plan.select", { plan: pl.name })}
              </Button>
            </li>
          );
        })}
      </ul>
      {codeOpen ? (
        <div className="flex flex-col gap-1" data-testid="discount-code">
          <label htmlFor="privat-kode" className="text-[13px] font-semibold">{t("plan.codeLabel")}</label>
          <input id="privat-kode" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder={t("plan.codePlaceholder")} autoCapitalize="characters" spellCheck={false}
            className="min-h-[46px] max-w-[260px] rounded-[14px] border-2 border-ink px-3.5 text-[16px] font-semibold tracking-[0.06em] uppercase bg-paper" />
          <p className={`m-0 text-[13px] ${codeError ? "text-danger font-semibold" : "text-muted"}`} role={codeError ? "alert" : undefined}>{codeError ?? t("plan.codeHint")}</p>
        </div>
      ) : (
        <button type="button" className={`${LINK} self-start`} onClick={() => setCodeOpen(true)}>{t("plan.codeAsk")}</button>
      )}
      <p className="m-0 text-[13px] text-muted">{t("plan.pickerNote")}</p>
    </div>
  );
}

/** «Inviter venner»: a general Dialogbot link, the referral numbers and the reward. Shared from the user's own phone. */
function InviteFriends() {
  const t = useT("privat");
  const { referrals, mode, api } = usePrivat();
  const [ref, setRef] = useState<ShareResult | null>(null);
  const [ua, setUa] = useState("");
  useEffect(() => { setUa(navigator.userAgent); }, []);
  // The general link with the user's referral token (POST /privat/referrals/link).
  useEffect(() => { if (mode === "real" || mode === "fake") api.referralLink().then(setRef).catch(() => setRef(null)); }, [api, mode]);
  if (mode === "demo" || !ref) return null;
  const link = ref.short_url ?? ref.invite_url;
  const body = t("invite.smsText", { link: bareLink(link) });
  const stats: [string, number | string][] = referrals
    ? [[t("invite.stats.invited"), referrals.invited], [t("invite.stats.joined"), referrals.joined], [t("invite.stats.activated"), referrals.activated], [t("invite.stats.earned"), referrals.credits_earned]]
    : [];
  return (
    <section className="rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-3" aria-labelledby="invite-h">
      <div className="flex items-center gap-3"><Tile name="users" /><h3 id="invite-h" className="m-0 font-display font-bold text-[19px]">{t("invite.title")}</h3></div>
      <p className="m-0 text-[15px] text-ink-soft">{t("invite.text")}</p>
      {stats.length > 0 && (
        <dl className="grid grid-cols-4 gap-2 m-0">
          {stats.map(([k, v]) => <div key={k} className="rounded-xl bg-panel p-2 text-center"><dt className="text-[11px] font-semibold text-muted uppercase tracking-[0.06em] [overflow-wrap:anywhere]">{k}</dt><dd className="m-0 font-display font-extrabold text-[22px]">{v}</dd></div>)}
        </dl>
      )}
      {referrals && <p className="m-0 text-[13px] text-muted">{t("invite.monthlyLeft", { n: referrals.monthly_left })}</p>}
      <div className="flex items-center gap-2 rounded-xl bg-panel px-3 py-2"><Ico name="link" size={18} /><span className="flex-1 min-w-0 text-[14px] font-semibold [overflow-wrap:anywhere]">{bareLink(link)}</span></div>
      <div className="flex gap-2 flex-wrap">
        <a href={smsHref(body, [], platformOf(ua))} className="inline-flex items-center justify-center gap-2 rounded-xl min-h-[44px] px-4 border-2 border-ink bg-accent text-white font-semibold text-[15px] hover:bg-accent-deep"><Ico name="send" size={18} />{t("share.sms")}</a>
        <Button variant="outline" className="border-2" onClick={() => navigator.clipboard?.writeText(link).catch(() => {})}><Ico name="copy" size={18} />{t("share.copy")}</Button>
      </div>
      <p className="m-0 text-[12px] text-muted">{t("invite.noMarketing")}</p>
    </section>
  );
}

/** «Din by: Aarhus C · Ret» – only what the user gave us (PATCH /privat/me/location). */
function CityRow() {
  const t = useT("privat");
  const { balance, run } = usePrivat();
  const [edit, setEdit] = useState(false);
  const [v, setV] = useState("");
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const x = v.trim(); if (!x) return;
    const r = await run((a) => a.setLocation(/^\d{4}$/.test(x) ? { postcode: x } : { city: x }));
    if (r) setEdit(false);
  };
  return (
    <section className="flex flex-col gap-2" aria-label={t("location.cityLabel")}>
      {!edit ? (
        <p className="m-0 text-[15px] flex items-center gap-2 flex-wrap" data-testid="city-row">
          <span><span className="text-muted">{t("location.cityLabel")}:</span> <b>{balance?.location_city ?? t("location.none")}</b></span>
          <span aria-hidden>·</span>
          <button type="button" className={LINK} onClick={() => { setV(balance?.location_city ?? ""); setEdit(true); }}>{t("location.edit")}</button>
        </p>
      ) : (
        <form onSubmit={save} className="flex gap-2">
          <label htmlFor="city-input" className="sr-only">{t("location.label")}</label>
          <input id="city-input" autoFocus value={v} onChange={(e) => setV(e.target.value)} placeholder={t("location.placeholder")} className="flex-1 min-w-0 min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px]" />
          <Button type="submit" className="border-2 border-ink">{t("location.save")}</Button>
        </form>
      )}
    </section>
  );
}

/** «Assistentens navn: Peter · Ret» (PATCH /privat/me/assistant). Calls and e-mails still say «Dialogbot». */
function AssistantNameRow() {
  const t = useT("privat");
  const { balance, run } = usePrivat();
  const [edit, setEdit] = useState(false);
  const [v, setV] = useState("");
  const [pron, setPron] = useState<"han" | "hun" | "den">("den");
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const r = await run((a) => a.setAssistantName(v.trim(), v.trim() ? pron : undefined));
    if (r) setEdit(false);
  };
  // The field starts empty when the name is the default (testers typed «Ida» after the prefilled «Peter»).
  const startEdit = () => {
    const n = balance?.assistant_name;
    setV(n && n !== "Peter" ? n : "");
    setPron(balance?.assistant_pronoun && n !== "Peter" ? balance.assistant_pronoun : "den");
    setEdit(true);
  };
  return (
    <section className="flex flex-col gap-2" aria-label={t("assistantName.label")}>
      {!edit ? (
        <p className="m-0 text-[15px] flex items-center gap-2 flex-wrap" data-testid="assistant-name-row">
          <span><span className="text-muted">{t("assistantName.label")}:</span> <b>{balance?.assistant_name ?? "Peter"}</b></span>
          <span aria-hidden>·</span>
          <button type="button" className={LINK} onClick={startEdit}>{t("location.edit")}</button>
        </p>
      ) : (
        <form onSubmit={save} className="flex flex-col gap-1.5">
          <div className="flex gap-2">
            <label htmlFor="assistant-name-input" className="sr-only">{t("assistantName.label")}</label>
            <input id="assistant-name-input" autoFocus value={v} maxLength={20} onChange={(e) => setV(e.target.value)}
              placeholder="Peter" className="flex-1 min-w-0 min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px]" />
            <Button type="submit" className="border-2 border-ink">{t("location.save")}</Button>
          </div>
          <fieldset className="m-0 p-0 border-0 flex items-center gap-2 flex-wrap">
            <legend className="sr-only">{t("assistantName.pronoun")}</legend>
            <span className="text-[13px] text-muted">{t("assistantName.pronoun")}</span>
            {(["hun", "han", "den"] as const).map((x) => (
              <button key={x} type="button" aria-pressed={pron === x} onClick={() => setPron(x)}
                className={`min-h-[36px] px-3 rounded-full border-2 border-ink text-[14px] font-semibold ${pron === x ? "bg-ink text-paper" : "bg-paper text-ink"}`}>{x}</button>
            ))}
          </fieldset>
          <p className="m-0 text-[12px] text-muted">{t("assistantName.hint")}</p>
        </form>
      )}
    </section>
  );
}
