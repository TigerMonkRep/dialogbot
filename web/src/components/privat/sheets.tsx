"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import { priceVars } from "@/lib/markets";
import { ADDON, type ShareGroupResult, type ShareMode, type ShareResult, type SmsQueueItem } from "@/lib/privat/api";
import type { ApiError } from "@/lib/client";
import { SMS_LIMIT, bareLink, contactPickerAvailable, hasEmoji, pickContacts, platformOf, smsHref, whatsappHref, type Platform } from "@/lib/privat/sms";
import { FAKE_ME } from "@/lib/privat/fake";
import { Avatars, BIG, Eyebrow, LINK, SR, Sim } from "./bits";
import { Ico } from "./icons";
import { AddonDetail, NeedsPlanOffer, addonText } from "./addons";
import { useFmt, usePlan, usePrivat } from "./store";

/** Bottom sheet on a phone, centred dialog on a wide screen. Escape and the X close it; focus moves in and back. */
export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const t = useT("privat");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>("[data-autofocus], input, textarea, button:not([aria-label]), a[href]");
    first?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && ref.current) {
        const f = [...ref.current.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], input, textarea, [tabindex]:not([tabindex='-1'])")];
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); prev?.focus?.(); };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 bg-ink/55 flex items-end sm:items-center sm:justify-center" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title}
        className="bg-paper border-2 border-ink flex flex-col gap-3 px-[18px] pt-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] max-h-[92dvh] overflow-y-auto w-full rounded-t-[20px] sm:w-[480px] sm:rounded-[20px] sm:shadow-block">
        <div className="flex items-start gap-2">
          <h2 className="m-0 flex-1 min-w-0 font-display font-extrabold text-[22px] [overflow-wrap:anywhere]">{title}</h2>
          <button type="button" onClick={onClose} aria-label={t("sheet.close")} className="w-11 h-11 -mt-2 -mr-2 inline-flex items-center justify-center rounded-xl hover:bg-panel"><Ico name="close" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Sheets() {
  const { sheet, closeSheet } = usePrivat();
  if (!sheet) return null;
  const k = sheet.kind;
  return k === "login" ? <LoginSheet onClose={closeSheet} />
    : k === "mic" ? <MicSheet onClose={closeSheet} />
    : k === "paywall" ? <PaywallSheet onClose={closeSheet} />
    : k === "buy" ? <BuySheet onClose={closeSheet} />
    : k === "sponsor" ? <SponsorSheet onClose={closeSheet} />
    : k === "share" ? <ShareSheet onClose={closeSheet} />
    : k === "addon" ? <AddonSheet onClose={closeSheet} />
    : k === "addonOff" ? <AddonOffSheet onClose={closeSheet} />
    : k === "needsPlan" ? <NeedsPlanSheet onClose={closeSheet} /> : null;
}

function LoginSheet({ onClose }: { onClose: () => void }) {
  const t = useT("privat");
  const { mode, simulatedLogin, screen } = usePrivat();
  // Back to where the login was asked for: Konto keeps its query (?plan=… starts the checkout after login).
  const next = encodeURIComponent(screen === "account" && typeof window !== "undefined" ? `${window.location.pathname}${window.location.search}` : "/privat/samtale");
  return (
    <Sheet title={t("login.title")} onClose={onClose}>
      <p className="m-0 text-[15px] leading-normal text-ink-soft">{t("login.text")}</p>
      {mode === "fake" && <Button className={BIG} onClick={simulatedLogin}>{t("login.simulated")} <Sim /></Button>}
      <Link href={`/signup?next=${next}`} className={`inline-flex items-center justify-center rounded-xl font-semibold ${BIG} ${mode === "fake" ? "bg-paper text-ink hover:bg-panel" : "bg-accent text-white hover:bg-accent-deep"}`}>{t("login.signup")}</Link>
      <Link href={`/login?next=${next}`} className="inline-flex items-center justify-center rounded-xl min-h-[44px] border-2 border-ink font-semibold text-[15px] hover:bg-panel">{t("login.login")}</Link>
      <button type="button" className={`${LINK} self-center`} onClick={onClose}>{t("login.notNow")}</button>
    </Sheet>
  );
}

function MicSheet({ onClose }: { onClose: () => void }) {
  const t = useT("privat");
  const [state, setState] = useState<"ask" | "ok" | "denied" | "unsupported">("ask");
  const allow = async () => {
    if (!navigator.mediaDevices?.getUserMedia) { setState("unsupported"); return; }
    try {
      // Only after the tap: the browser asks for permission now. Nothing is recorded or sent yet.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((tr) => tr.stop());
      // TODO(stt): start dictation here when a speech-to-text endpoint for Privat exists; fill the composer with the text.
      setState("ok");
    } catch { setState("denied"); }
  };
  return (
    <Sheet title={t("mic.title")} onClose={onClose}>
      <p className="m-0 text-[15px] leading-normal text-ink-soft">{t("mic.text")}</p>
      {state === "ask" && <Button className={BIG} onClick={allow}>{t("mic.allow")}</Button>}
      {state !== "ask" && <p role="status" className="m-0 rounded-xl border-[1.5px] border-ink bg-panel p-3 text-[15px]">{t(`mic.${state === "ok" ? "soon" : state}`)}</p>}
      <button type="button" className={`${LINK} self-center`} onClick={onClose}>{t("mic.typeInstead")}</button>
    </Sheet>
  );
}

/** Without a trial yet (status «none»): the trial first – one tap to the checkout, card first, no credits or sponsor
 *  spots on the way round it. After the trial: the plan path («Vælg plan»), then credits as «ekstra opkald». With a
 *  plan whose month is used up: buy extra calls or change plan. */
function PaywallSheet({ onClose }: { onClose: () => void }) {
  const t = useT("privat");
  const { sheet, task, balance, run, openSheet, setNote, choosePlan: toPlans, startTrial, busy } = usePrivat();
  const p = usePlan();
  const tk = task(sheet?.taskId);
  const call = tk?.kind === "call";
  const credits = balance?.credits ?? 0;
  const later = () => { onClose(); if (tk?.status === "draft") setNote(t("paywall.laterNote")); };
  const choosePlan = () => { onClose(); toPlans(); };
  const trialFirst = !p.entitled && p.status === "none";
  const quotaUsed = call && p.entitled && p.callsQuota > 0;
  const title = trialFirst ? t("paywall.titleTrial") : call ? (quotaUsed ? t("plan.paywallCallTitlePlan") : t("paywall.titleCall")) : t("paywall.titleDigital");
  const text = trialFirst ? t("paywall.textTrial") : call
    ? (quotaUsed ? t("plan.paywallCallTextPlan", { used: p.callsUsed, quota: p.callsQuota, plan: p.rightsName }) : `${t("plan.paywallCallTextNone")} ${t("paywall.textCall", { n: tk?.call?.max_credits ?? 3, have: credits })}`)
    : `${t("paywall.textDigital")} ${t("plan.paywallDigitalPlan")}`;
  if (trialFirst) {
    return (
      <Sheet title={title} onClose={onClose}>
        {tk && <div className="rounded-[18px] border-2 border-dashed border-ink px-3.5 py-3"><span className="eyebrow text-[11px]">{t("paywall.draft")}</span><div className="font-semibold text-[16px] [overflow-wrap:anywhere]">{tk.title}</div></div>}
        <p className="m-0 text-[15px] leading-normal text-ink-soft">{text}</p>
        <Button className={`${BIG} rounded-full`} disabled={busy} onClick={() => void startTrial()} data-testid="paywall-trial">{t("store.needsPlan.trial")}</Button>
        <p className="m-0 text-[13px] text-muted text-center">{t("paywall.trialNote")}</p>
        <button type="button" className={`${LINK} self-center`} onClick={later}>{t("paywall.later")}</button>
      </Sheet>
    );
  }
  return (
    <Sheet title={title} onClose={onClose}>
      {tk && <div className="rounded-[18px] border-2 border-dashed border-ink px-3.5 py-3"><span className="eyebrow text-[11px]">{t("paywall.draft")}</span><div className="font-semibold text-[16px] [overflow-wrap:anywhere]">{tk.title}</div></div>}
      <p className="m-0 text-[15px] leading-normal text-ink-soft">{text}</p>
      {!p.entitled && <Button className={`${BIG} rounded-full`} onClick={choosePlan}>{t("plan.paywallChoose")}</Button>}
      {!call && <Button className={`${p.entitled ? BIG : "border-2 border-ink"} rounded-full`} variant={p.entitled ? "primary" : "outline"} disabled={credits < 1} onClick={async () => { const r = await run((a) => a.activate(tk!.id, "credit")); if (r) onClose(); }}>{t("paywall.useCredit", { n: credits })}</Button>}
      <Button variant={quotaUsed ? "primary" : "outline"} className={`${quotaUsed ? BIG : "border-2"} rounded-full`} onClick={() => openSheet({ kind: "buy", taskId: sheet?.taskId })}>{t("plan.paywallBuy")} · {t("paywall.buy")}</Button>
      {quotaUsed && <Button variant="outline" className="border-2 rounded-full" onClick={choosePlan}>{t("plan.change")}</Button>}
      {!call && <Button variant="outline" className="border-2 rounded-full" disabled={(balance?.sponsor_left_today ?? 0) < 1} onClick={() => openSheet({ kind: "sponsor", taskId: sheet?.taskId })}>{t("paywall.sponsor", { n: balance?.sponsor_left_today ?? 0 })}</Button>}
      <button type="button" className={`${LINK} self-center`} onClick={later}>{t("paywall.later")}</button>
    </Sheet>
  );
}

function BuySheet({ onClose }: { onClose: () => void }) {
  const t = useT("privat");
  const { sheet, simulated, mode, fake, run, api, openSheet, setNote, setError, go, isDesk } = usePrivat();
  const [busy, setBusy] = useState(false);
  const locale = useLocale();
  const pack = priceVars(locale);
  const pay = async () => {
    setBusy(true);
    if (simulated && fake) {
      const r = await run(() => fake.completePurchase(sheet?.taskId ?? null));
      if (r) { setNote(t("account.purchased", { ref: r.ref })); onClose(); }
      setBusy(false);
      return;
    }
    try { const { url } = await api.checkout({ locale }); window.location.href = url; }
    catch (e) { setError(e as ApiError); setBusy(false); }
  };
  void go; void isDesk;
  return (
    <Sheet title={t("buy.title")} onClose={onClose}>
      <div className="rounded-[18px] border-2 border-ink p-4 flex flex-col gap-1.5">
        <div className="flex justify-between text-[16px]"><span>{t("buy.item")}</span><b>{pack.pCredits}</b></div>
        <div className="flex justify-between text-[13px] text-muted"><span>{t("buy.vat")}</span><span>{pack.pCreditsVat}</span></div>
        <p className="m-0 mt-1 text-[13px] text-muted">{t("buy.note")}</p>
      </div>
      <Button className={BIG} onClick={pay} disabled={busy || mode === "demo"}>{simulated ? <>{t("buy.pay")} <Sim label={t("buy.simulatedBuy")} /></> : busy ? t("buy.redirecting") : t("buy.payReal")}</Button>
      <button type="button" className={`${LINK} self-center`} onClick={() => (sheet?.taskId ? openSheet({ kind: "paywall", taskId: sheet.taskId }) : onClose())}>{t("buy.back")}</button>
    </Sheet>
  );
}

function SponsorSheet({ onClose }: { onClose: () => void }) {
  const t = useT("privat");
  const { sheet, run, openSheet } = usePrivat();
  return (
    <Sheet title={t("sponsor.title")} onClose={onClose}>
      <div className="border-2 border-ink rounded-2xl overflow-hidden">
        <div className="bg-panel px-3 py-2 flex justify-between items-center"><span className="eyebrow text-[11px]">{t("sponsor.label")}</span><Sim /></div>
        <div className="px-3.5 py-[18px] flex flex-col gap-1.5 min-h-[120px] justify-center text-center">
          <span className="font-display font-bold text-[20px]">{t("sponsor.placeholder")}</span>
          <span className="text-[13px] text-muted">{t("sponsor.fictive")}</span>
        </div>
      </div>
      <p className="m-0 text-[14px] text-ink-soft">{t("sponsor.text")}</p>
      <Button className={BIG} onClick={async () => { const r = await run((a) => a.sponsorClaim(sheet!.taskId!)); if (r) onClose(); }}>{t("sponsor.watched")}</Button>
      <button type="button" className={`${LINK} self-center`} onClick={() => openSheet({ kind: "paywall", taskId: sheet?.taskId })}>{t("sponsor.later")}</button>
    </Sheet>
  );
}

const SIGN_KEY = "dialogbot-privat-sign";

/** Sharing a list. The primary path is the user's OWN Messages app with the text filled in («Send som SMS»), so the
 *  invite comes from a number friends know. Dialogbot never sends invites itself, and picked contacts stay on the phone. */
function ShareSheet({ onClose }: { onClose: () => void }) {
  const t = useT("privat");
  const { sheet, task, addonOn, run, session, mode } = usePrivat();
  const tk = task(sheet?.taskId);
  const wish = tk?.list_type === "wishlist";
  const kinds: ShareMode[] = [...(addonOn(ADDON.sharedLists) ? ["group" as const] : []), ...(addonOn(ADDON.wishlists) ? ["wishlist" as const] : [])];
  const [kind, setKind] = useState<ShareMode | null>(tk?.share_mode ?? (wish && kinds.includes("wishlist") ? "wishlist" : kinds[0] ?? null));
  const [res, setRes] = useState<ShareResult | null>(null);
  const [platform, setPlatform] = useState<Platform>("other");
  const [picker, setPicker] = useState(false);
  const [canNative, setCanNative] = useState(false);
  const [to, setTo] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [sign, setSign] = useState("");
  const [text, setText] = useState("");
  const [edited, setEdited] = useState(false);
  const [groupActive, setGroupActive] = useState(false);
  useEffect(() => {
    setPlatform(platformOf(navigator.userAgent));
    setPicker(contactPickerAvailable());
    setCanNative(typeof navigator.share === "function");
    let s = "";
    try { s = localStorage.getItem(SIGN_KEY) ?? ""; } catch { /* ignore */ }
    setSign(s || (session.name ?? "").split(" ")[0] || (mode === "fake" ? FAKE_ME : ""));
  }, [session.name, mode]);
  const link = res ? bareLink(res.short_url ?? res.invite_url) : "";
  const suggested = res ? `${t(kind === "wishlist" ? "share.smsWishlist" : "share.smsGroup", { link })}${sign.trim() ? ` – ${sign.trim()}` : ""}` : "";
  useEffect(() => { if (!edited) setText(suggested); }, [suggested, edited]);
  if (!tk) return null;
  const create = async () => { if (!kind) return; const r = await run((a) => a.share(tk.id, { mode: kind, role: "editor" })); if (r) { setRes(r); setEdited(false); } };
  const saveSign = (v: string) => { setSign(v); try { localStorage.setItem(SIGN_KEY, v); } catch { /* ignore */ } };
  const body = text || suggested;
  const copy = async () => { try { await navigator.clipboard.writeText(res!.short_url ?? res!.invite_url); setCopied(true); setTimeout(() => setCopied(false), 2500); } catch { /* ignore */ } };
  const native = async () => { try { await navigator.share({ title: tk.title, text: body }); } catch { /* cancelled */ } };
  const choose = async () => { try { setTo(await pickContacts()); } catch { /* cancelled */ } };
  const owner = !tk.my_role || tk.my_role === "owner";
  const btn = `inline-flex items-center justify-center gap-2 rounded-xl font-semibold`;
  return (
    <Sheet title={t("share.title", { title: tk.title })} onClose={onClose}>
      {!res && owner && kinds.length > 0 && kind && <GroupShare taskId={tk.id} mode={kind} onActive={setGroupActive} />}
      {!res && !groupActive && (
        <>
          {kinds.length > 0 && owner && <Eyebrow className="pt-1">{t("share.orLink")}</Eyebrow>}
          {kinds.length === 0 ? <p className="m-0 text-[15px] text-ink-soft">{t("share.noKinds")}</p> : (
            <fieldset className="m-0 p-0 border-0 flex flex-col gap-2">
              <legend className="text-[15px] font-semibold mb-2">{t("share.chooseKind")}</legend>
              {kinds.map((k) => (
                <label key={k} className={`flex items-start gap-3 rounded-[14px] border-2 p-3 cursor-pointer ${kind === k ? "border-ink bg-panel" : "border-line"}`}>
                  <input type="radio" name="share-kind" className="mt-1 w-5 h-5 accent-[var(--color-accent)]" checked={kind === k} onChange={() => setKind(k)} />
                  <span className="flex flex-col"><span className="font-semibold text-[16px]">{t(`share.${k}`)}</span><span className="text-[14px] text-ink-soft">{t(`share.${k}Sub`)}</span></span>
                </label>
              ))}
            </fieldset>
          )}
          {kinds.length > 0 && <Button className={BIG} onClick={create}>{tk.shared ? t("share.newLink") : t("share.create")}</Button>}
        </>
      )}
      {res && (
        <>
          <label className="flex items-center gap-2 text-[14px] font-semibold">{t("share.signWith")}
            <input value={sign} onChange={(e) => saveSign(e.target.value)} maxLength={20} autoComplete="given-name"
              className="flex-1 min-w-0 min-h-[44px] rounded-xl border-2 border-ink px-3 text-[16px] font-normal" />
          </label>
          <label htmlFor="share-text" className="text-[14px] font-semibold">{t("share.message")}</label>
          <textarea id="share-text" rows={3} value={body} onChange={(e) => { setText(e.target.value); setEdited(true); }}
            className="w-full rounded-[14px] border-2 border-ink p-3 text-[16px] leading-snug resize-y" />
          <span className={`text-[12px] ${body.length > SMS_LIMIT || hasEmoji(body) ? "text-danger font-semibold" : "text-muted"}`} aria-live="polite">
            {t("share.chars", { n: body.length, max: SMS_LIMIT })}{hasEmoji(body) ? ` · ${t("share.noEmoji")}` : ""}
          </span>
          <a href={smsHref(body, to, platform)} data-testid="share-sms" className={`${btn} ${BIG} bg-accent text-white hover:bg-accent-deep`}><Ico name="send" size={18} />{t("share.sms")}</a>
          {to.length > 0 && <p className="m-0 text-[13px] text-ink-soft">{t("share.recipients", { n: to.length })}</p>}
          {picker && platform !== "ios" && (
            <>
              <Button variant="outline" className="border-2" onClick={choose} data-testid="share-contacts"><Ico name="users" size={18} />{t("share.contacts")}</Button>
              <p className="m-0 -mt-1 text-[12px] text-muted">{t("share.contactsLocal")}</p>
            </>
          )}
          <div className="grid grid-cols-2 gap-2">
            <a href={whatsappHref(body)} target="_blank" rel="noopener noreferrer" className={`${btn} min-h-[44px] border-2 border-ink hover:bg-panel text-[15px]`}>{t("share.whatsapp")}</a>
            {canNative
              ? <Button variant="outline" className="border-2" onClick={native}><Ico name="share" size={18} />{t("share.other")}</Button>
              : <Button variant="outline" className="border-2" onClick={copy}><Ico name="copy" size={18} />{copied ? t("share.copied") : t("share.copy")}</Button>}
          </div>
          <div className="flex items-center gap-2 rounded-xl bg-panel px-3 py-2">
            <Ico name="link" size={18} />
            <span className="flex-1 min-w-0 text-[14px] font-semibold [overflow-wrap:anywhere]" data-testid="share-link">{link}</span>
            {canNative && <button type="button" onClick={copy} className="min-h-[44px] px-2 text-[14px] font-semibold text-accent underline">{copied ? t("share.copied") : t("share.copy")}</button>}
          </div>
          <span role="status" className={SR}>{copied ? t("share.copied") : ""}</span>
          <p className="m-0 text-[12px] text-muted">{t("share.ownPhone")}</p>
        </>
      )}
      {(tk.members?.length ?? 0) > 0 && tk.shared && <Members onClose={onClose} />}
      {tk.shared && owner && (
        <Button variant="outline" className="border-2 border-danger text-danger" onClick={async () => { await run((a) => a.revokeShare(tk.id)); setRes(null); }}>{t("share.stop")}</Button>
      )}
    </Sheet>
  );
}

function Members({ onClose }: { onClose: () => void }) {
  const t = useT("privat");
  const { sheet, task, run, go } = usePrivat();
  const tk = task(sheet?.taskId)!;
  const owner = !tk.my_role || tk.my_role === "owner";
  return (
    <div className="flex flex-col gap-1.5 border-t-[1.5px] border-line pt-3">
      <Eyebrow>{t("share.members")}</Eyebrow>
      <ul className="m-0 p-0 list-none flex flex-col">
        {(tk.members ?? []).map((m) => (
          <li key={m.id} className="flex items-center gap-3 min-h-[48px]">
            <Avatars names={[m.name]} size={30} />
            <span className="flex-1 min-w-0 text-[15px]">{m.name}{m.is_me ? ` ${t("share.you")}` : ""}<span className="text-muted text-[13px]"> · {t(`share.role.${m.role}`)}</span></span>
            {owner && !m.is_me && <button type="button" className="min-h-[44px] px-2 text-[14px] font-semibold text-accent underline" aria-label={t("share.removeAria", { name: m.name })} onClick={() => run((a) => a.removeMember(tk.id, m.id))}>{t("share.remove")}</button>}
            {!owner && m.is_me && <button type="button" className="min-h-[44px] px-2 text-[14px] font-semibold text-accent underline" onClick={async () => { await run((a) => a.removeMember(tk.id, m.id)); onClose(); go("tasks"); }}>{t("share.leave")}</button>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function AddonSheet({ onClose }: { onClose: () => void }) {
  const t = useT("privat");
  const { sheet, addons } = usePrivat();
  const a = addons?.find((x) => x.key === sheet?.addonKey);
  if (!a) return null;
  return <Sheet title={addonText(t, a, "name")} onClose={onClose}><AddonDetail a={a} /></Sheet>;
}

/** «Med i Plus – start 14 dage gratis / Vælg plan» for an app (addonKey) or a call (taskId). */
function NeedsPlanSheet({ onClose }: { onClose: () => void }) {
  const t = useT("privat");
  const { sheet, addons } = usePrivat();
  const a = addons?.find((x) => x.key === sheet?.addonKey);
  return (
    <Sheet title={a ? addonText(t, a, "name") : t("store.needsPlan.callTitle")} onClose={onClose}>
      <NeedsPlanOffer name={a ? addonText(t, a, "name") : undefined} call={!a} />
      <button type="button" className={`${LINK} self-center`} onClick={onClose}>{t("store.needsPlan.later")}</button>
    </Sheet>
  );
}

function AddonOffSheet({ onClose }: { onClose: () => void }) {
  const t = useT("privat");
  const { sheet, addons, run } = usePrivat();
  const a = addons?.find((x) => x.key === sheet?.addonKey);
  if (!a) return null;
  const name = addonText(t, a, "name");
  return (
    <Sheet title={t("addons.confirmDisableTitle", { name })} onClose={onClose}>
      <p className="m-0 text-[15px] leading-normal text-ink-soft">{t("addons.confirmDisableText")}</p>
      <Button className={`${BIG} bg-paper !text-ink hover:!bg-panel`} variant="outline" onClick={async () => { await run((x) => x.disableAddon(a.key)); onClose(); }}>{t("addons.disable")}</Button>
      <Button className={BIG} onClick={onClose}>{t("addons.keep")}</Button>
    </Sheet>
  );
}

const QUEUE_KEY = "dialogbot-privat-queue";
type Queue = { taskId: string; items: SmsQueueItem[]; index: number };
const readQueue = (taskId: string): Queue | null => {
  try { const q = JSON.parse(sessionStorage.getItem(QUEUE_KEY) ?? "null") as Queue | null; return q && q.taskId === taskId ? q : null; } catch { return null; }
};
const writeQueue = (q: Queue | null) => { try { if (q) sessionStorage.setItem(QUEUE_KEY, JSON.stringify(q)); else sessionStorage.removeItem(QUEUE_KEY); } catch { /* ignore */ } };

/** «Del med en gruppe»: people who have Dialogbot are added in the app; the rest get an SMS from the user's own phone –
 *  one group SMS, or one at a time with a personal text and link (the queue survives switching to Messages and back). */
function GroupShare({ taskId, mode, onActive }: { taskId: string; mode: ShareMode; onActive: (on: boolean) => void }) {
  const t = useT("privat");
  const { groups, sheet, run, go, closeSheet } = usePrivat();
  const [gid, setGid] = useState<string | null>(sheet?.groupId ?? null);
  const [result, setResult] = useState<ShareGroupResult | null>(null);
  const [queue, setQueue] = useState<Queue | null>(null);
  const [platform, setPlatform] = useState<Platform>("other");
  const [back, setBack] = useState(false);
  useEffect(() => { setPlatform(platformOf(navigator.userAgent)); setQueue(readQueue(taskId)); }, [taskId]);
  useEffect(() => {
    const onVis = () => { if (document.visibilityState === "visible") setBack(true); };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);
  useEffect(() => { onActive(!!queue || !!result); }, [queue, result, onActive]);
  const g = groups.find((x) => x.id === gid);
  const inApp = g ? g.members.filter((m) => m.has_dialogbot).length : 0;
  const bySms = g ? g.members.filter((m) => !m.has_dialogbot && m.phone_e164).length : 0;
  const go1 = async (style: "group_sms" | "one_by_one") => {
    const r = await run((a) => a.shareGroup(taskId, { group_id: gid!, mode, role: "editor", style }));
    if (!r) return;
    setResult(r);
    if (r.sms_queue?.length) { const q = { taskId, items: r.sms_queue, index: 0 }; setQueue(q); writeQueue(q); }
  };
  const advance = () => { if (!queue) return; const q = { ...queue, index: queue.index + 1 }; setQueue(q); writeQueue(q); setBack(false); };
  const btn = "inline-flex items-center justify-center gap-2 rounded-xl font-semibold";

  if (queue) {
    const cur = queue.items[queue.index];
    const total = queue.items.length;
    return (
      <section className="flex flex-col gap-2.5 rounded-[18px] border-2 border-ink p-4 bg-panel" aria-label={t("share.queueTitle")} data-testid="sms-queue">
        <Eyebrow>{t("share.queueTitle")}</Eyebrow>
        {result && result.added_in_app.length > 0 && <p className="m-0 text-[14px] text-success font-semibold">{t("share.addedInApp", { names: result.added_in_app.map((x) => x.name).join(", ") })}</p>}
        {cur ? (
          <>
            <p className="m-0 text-[14px] text-ink-soft [overflow-wrap:anywhere]">«{cur.body}»</p>
            <a href={smsHref(cur.body, [cur.phone_e164], platform)} onClick={advance} data-testid="queue-next"
              className={`${btn} ${BIG} bg-accent text-white hover:bg-accent-deep`}>
              <Ico name="send" size={18} />{queue.index === 0 ? t("share.queueFirst", { name: cur.name, i: 1, n: total }) : t("share.queueNext", { name: cur.name, i: queue.index + 1, n: total })}
            </a>
            {back && queue.index > 0 && <p className="m-0 text-[13px] text-muted" role="status">{t("share.queueBack")}</p>}
          </>
        ) : (
          <>
            <p className="m-0 text-[15px] font-semibold text-success" role="status">{t("share.queueDone", { n: total })}</p>
            <Button className={BIG} onClick={() => { writeQueue(null); setQueue(null); closeSheet(); }}>{t("share.done")}</Button>
          </>
        )}
      </section>
    );
  }
  if (result?.sms_group || (result && !result.sms_queue)) {
    return (
      <section className="flex flex-col gap-2.5 rounded-[18px] border-2 border-ink p-4 bg-panel">
        {result.added_in_app.length > 0 && <p className="m-0 text-[14px] text-success font-semibold">{t("share.addedInApp", { names: result.added_in_app.map((x) => x.name).join(", ") })}</p>}
        {result.sms_group && (
          <>
            <p className="m-0 text-[14px] text-ink-soft [overflow-wrap:anywhere]">«{result.sms_group.body}»</p>
            <a href={smsHref(result.sms_group.body, result.sms_group.recipients, platform)} data-testid="group-sms" className={`${btn} ${BIG} bg-accent text-white hover:bg-accent-deep`}>
              <Ico name="send" size={18} />{t("share.groupSmsSend", { n: result.sms_group.recipients.length })}</a>
          </>
        )}
        <Button variant="outline" className="border-2" onClick={closeSheet}>{t("share.done")}</Button>
      </section>
    );
  }
  return (
    <section className="flex flex-col gap-2.5" aria-label={t("share.withGroup")}>
      <Eyebrow>{t("share.withGroup")}</Eyebrow>
      {groups.length === 0 ? (
        <button type="button" className={LINK} onClick={() => { closeSheet(); go("people"); }}>{t("share.makeGroup")}</button>
      ) : (
        <div className="flex flex-col gap-2" role="radiogroup" aria-label={t("share.withGroup")}>
          {groups.map((x) => (
            <label key={x.id} className={`flex items-center gap-3 rounded-[14px] border-2 p-3 cursor-pointer ${gid === x.id ? "border-ink bg-panel" : "border-line"}`}>
              <input type="radio" name="share-group" className="w-5 h-5 accent-[var(--color-accent)]" checked={gid === x.id} onChange={() => setGid(x.id)} />
              <span className="flex-1 min-w-0 font-semibold text-[16px] [overflow-wrap:anywhere]">{t("people.groupCard", { name: x.name, n: x.members.length })}</span>
              <Avatars names={x.members.map((m) => m.name)} size={26} />
            </label>
          ))}
        </div>
      )}
      {g && (
        <div className="rounded-[14px] border-[1.5px] border-ink bg-paper p-3 flex flex-col gap-2" data-testid="group-summary">
          {inApp > 0 && <p className="m-0 text-[15px] flex gap-2 items-start"><span className="text-success mt-0.5"><Ico name="check" size={18} /></span>{t("share.summaryInApp", { n: inApp })}</p>}
          {bySms > 0 && <p className="m-0 text-[15px] flex gap-2 items-start"><span className="text-accent mt-0.5"><Ico name="send" size={18} /></span>{t("share.summarySms", { n: bySms })}</p>}
          {bySms > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <Button variant="outline" className="border-2" onClick={() => go1("group_sms")}>{t("share.groupSms")}</Button>
              <Button className="border-2 border-ink" onClick={() => go1("one_by_one")}>{t("share.oneByOne")}</Button>
            </div>
          ) : <Button className={BIG} onClick={() => go1("one_by_one")}>{t("share.addAll")}</Button>}
          {bySms > 0 && <p className="m-0 text-[12px] text-muted">{t("share.oneByOneHint")}</p>}
        </div>
      )}
    </section>
  );
}
