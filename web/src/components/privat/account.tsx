"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import { BIG, Eyebrow, LINK, Pill, Sim } from "./bits";
import { PhoneVerify } from "./cards";
import { PushPrompt } from "./push";
import { Ico, Tile } from "./icons";
import { useFmt, usePrivat } from "./store";
import { bareLink, smsHref, platformOf } from "@/lib/privat/sms";
import type { ShareResult } from "@/lib/privat/api";

export function AccountPane() {
  const t = useT("privat");
  const f = useFmt();
  const { balance, ledger, session, mode, simulated, fake, run, note, setNote, openSheet, go, loggedIn } = usePrivat();
  const params = useSearchParams();
  const [changing, setChanging] = useState(false);
  useEffect(() => {
    const c = params.get("checkout");
    if (c === "success") setNote(t("account.purchasedReal"));
    if (c === "cancel") setNote(t("account.purchaseCancelled"));
  }, [params, setNote, t]);
  const limit = balance?.free_limit ?? 10;
  const used = balance?.free_used ?? 0;
  const left = Math.max(0, limit - used);
  const line = mode === "demo" ? t("account.exampleLine") : loggedIn ? t("account.privateLine", { email: session.email ?? (simulated ? "mette@eksempel.dk" : "") }) : t("account.exampleLine");
  const amount = (kind: string, n: number) => kind === "sponsor" ? t("account.oneTask") : `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)}${kind === "reserve" ? ` ${t("account.reservedSuffix")}` : ""}`;
  return (
    <div className="px-4 pt-5 pb-7 flex flex-col gap-[18px]" aria-label={t("account.title")}>
      <h2 className="m-0 font-display font-extrabold text-[28px] tracking-[-0.5px]">{t("account.title")}</h2>
      <p className="m-0 text-[14px] text-ink-soft [overflow-wrap:anywhere]">{line}</p>
      {simulated && <p className="m-0 text-[13px] flex gap-2 items-center flex-wrap"><Sim />{t("account.simulatedLine")}</p>}

      <div className="rounded-[18px] border-2 border-ink bg-paper p-4 shadow-block flex flex-col gap-2.5">
        <Eyebrow><span suppressHydrationWarning>{t("account.free", { month: f.month() })}</span></Eyebrow>
        <div className="flex items-baseline gap-2"><span className="font-display font-extrabold text-[36px]" data-testid="free-left">{left}</span><span className="text-[15px] text-ink-soft">{t("account.freeLeft", { limit })}</span></div>
        <div className="h-3 border-2 border-ink rounded-full overflow-hidden bg-paper" role="progressbar" aria-valuemin={0} aria-valuemax={limit} aria-valuenow={used} aria-label={t("account.freeBarAria", { used, limit })}>
          <div className="h-full bg-accent" style={{ width: `${Math.min(100, (used / limit) * 100)}%` }} />
        </div>
        <p className="m-0 text-[13px] text-muted">{t("account.freeNote", { limit })}</p>
      </div>

      <div className="rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5">
        <Eyebrow>{t("account.credits")}</Eyebrow>
        <div className="flex items-baseline gap-2.5 flex-wrap">
          <span className="font-display font-extrabold text-[36px]" data-testid="credits">{balance?.credits ?? 0}</span><span className="text-[15px] text-ink-soft">{t("account.creditsWord")}</span>
          {(balance?.reserved ?? 0) > 0 && <Pill tone="progress">{t("account.reserved", { n: balance!.reserved })}</Pill>}
        </div>
        <p className="m-0 text-[13px] text-muted">{t("account.creditsNote")}</p>
        <Button className={`${BIG} self-start`} onClick={() => openSheet({ kind: "buy" })} disabled={mode === "demo"}>{t("account.buy")}</Button>
        {note && <p className="m-0 text-[14px] font-semibold text-success" role="status">{note}</p>}
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

      <section className="rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5" aria-labelledby="notif-h">
        <h3 id="notif-h" className="m-0 font-display font-bold text-[19px]">{t("push.title")}</h3>
        <PushPrompt moment="account" />
      </section>

      {mode !== "demo" && <CityRow />}

      <InviteFriends />

      <section className="rounded-[18px] border-2 border-ink bg-panel p-4 flex items-start gap-3">
        <Tile name="puzzle" />
        <div className="flex-1 min-w-0 flex flex-col gap-2">
          <h3 className="m-0 font-display font-bold text-[19px]">{t("account.addons")}</h3>
          <p className="m-0 text-[14px] text-ink-soft">{t("account.addonsText")}</p>
          <Button variant="outline" className="self-start border-2" onClick={() => go("addons")}>{t("account.addonsBtn")}</Button>
        </div>
      </section>

      {simulated && fake && (
        <div className="rounded-[14px] border-[1.5px] border-dashed border-ink bg-panel p-3 flex flex-col gap-2">
          <Eyebrow>{t("account.tools")}</Eyebrow>
          <div className="flex gap-2 flex-wrap">
            <Button variant="outline" onClick={() => run(() => fake.useUpFree())}>{t("account.useUp")}</Button>
            <Button variant="outline" onClick={async () => { const r = await run(() => fake.repeatPayment()); if (r) setNote(r.ref ? t("account.repeatNote", { ref: r.ref }) : t("account.repeatNone")); }}>{t("account.repeatPay")}</Button>
            <Button variant="outline" onClick={() => run(() => fake.emptyDay())}>{t("account.emptyDay")}</Button>
            <Button variant="outline" onClick={async () => { await run(() => fake.reset()); setNote(""); }}>{t("account.reset")}</Button>
          </div>
        </div>
      )}
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
