"use client";
/** Wishlists: wish cards with a big product picture, the detail view, «Tilføj ønske» (search / link / by hand → ONE
 *  form and one data model) and «Deles om en gave» for the givers. Secrets are kept by the backend: the owner's
 *  browser never receives reservations or group-gift agreements (docs/privat-api.md «Ønsker, fællesgaver og design»). */
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import { isGiverGift, newKey, type GiverGroupGift, type OwnerGroupGift, type Task, type TaskItem, type WishBody, type WishImport, type WishOptions, type WishSearchResult } from "@/lib/privat/api";
import { CURRENCIES, amountInput, imgSrc, money, parseAmount } from "@/lib/privat/wish";
import { currencyFor } from "@/lib/markets";
import { BIG, CHIP, Pill, SR } from "./bits";
import { Ico } from "./icons";
import { Sheet } from "./sheets";
import { useFmt, usePrivat } from "./store";

const FIELD = "w-full min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px] bg-paper text-ink placeholder:text-muted";
const LABEL = "text-[14px] font-semibold";
/** The primary chip (accent fill) – CHIP's own bg-paper/text-ink must not compete with it. */
const PCHIP = "inline-flex items-center gap-2 min-h-[44px] px-3.5 rounded-full border-2 border-accent bg-accent text-white text-[14px] font-semibold whitespace-nowrap hover:bg-accent-deep no-underline";
const HINT = "m-0 text-[13px] text-ink-soft";

type Fmt = (minor: number, currency: string) => string;
function useMoney(): Fmt {
  const locale = useLocale();
  return useMemo(() => (minor: number, currency: string) => money(minor, currency, locale), [locale]);
}

/** Every error from the API arrives in Danish with a code; the field it belongs to is in field_errors. */
function errText(e: unknown): string { return (e as ApiError)?.message || "Noget gik galt. Prøv igen."; }

// ---------------------------------------------------------------- the list

export function WishList({ task, withAdd }: { task: Task; withAdd: boolean }) {
  const t = useT("privat");
  const owner = !task.my_role || task.my_role === "owner";
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<TaskItem | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [joining, setJoining] = useState<string | null>(null);
  const items = task.items;
  const open = items.find((i) => i.id === detail) ?? null;
  const join = items.find((i) => i.id === joining) ?? null;
  return (
    <div className="@container flex flex-col gap-3">
      {owner && withAdd && (
        <Button className={`${BIG} self-start gap-2`} onClick={() => setAdding(true)} data-testid="add-wish"><Ico name="plus" size={18} />{t("wish.add")}</Button>
      )}
      {items.length === 0 && <p className="m-0 text-[14px] text-muted">{t("list.emptyItems")}</p>}
      <ul className="list-none m-0 p-0 grid grid-cols-1 @lg:grid-cols-2 gap-3" data-testid="wish-grid">
        {items.map((it) => (
          <li key={it.id} className="min-w-0">
            <WishCard task={task} item={it} owner={owner} onDetails={() => setDetail(it.id)} onJoin={() => setJoining(it.id)} />
          </li>
        ))}
      </ul>
      {adding && <AddWishSheet task={task} onClose={() => setAdding(false)} />}
      {editing && <WishFormSheet task={task} item={editing} onClose={() => setEditing(null)} />}
      {open && <WishDetailSheet task={task} item={open} owner={owner} onClose={() => setDetail(null)}
        onEdit={() => { setDetail(null); setEditing(open); }} onJoin={() => { setDetail(null); setJoining(open.id); }} />}
      {join && isGiverGift(join.group_gift) && <PledgeSheet task={task} item={join} gift={join.group_gift} onClose={() => setJoining(null)} />}
    </div>
  );
}

/** The product picture: never cropped (object-contain on a calm panel), a neutral placeholder without a photo. */
function WishImage({ item, size = "sm", className = "" }: { item: TaskItem; size?: "sm" | "lg"; className?: string }) {
  const t = useT("privat");
  const src = imgSrc(size === "sm" ? item.image?.url_sm : item.image?.url);
  const [failed, setFailed] = useState(false);
  return (
    <div className={`relative w-full aspect-[4/3] rounded-[14px] bg-panel overflow-hidden flex items-center justify-center ${className}`}>
      {src && !failed ? (
        // eslint-disable-next-line @next/next/no-img-element -- signed, short-lived links from our own bucket
        <img src={src} alt={item.text} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(true)}
          className="absolute inset-0 w-full h-full object-contain p-2" />
      ) : (
        <span className="flex flex-col items-center gap-1 text-muted" role="img" aria-label={t("wish.noImage")}>
          <Ico name="gift" size={44} stroke={1.6} />
        </span>
      )}
    </div>
  );
}

function PriceLine({ item, className = "" }: { item: TaskItem; className?: string }) {
  const t = useT("privat");
  const fmt = useMoney();
  return item.price_minor != null && item.currency
    ? <span className={`font-display font-bold text-[18px] ${className}`}>{fmt(item.price_minor, item.currency)}</span>
    : <span className={`text-[14px] text-muted ${className}`}>{t("wish.noPrice")}</span>;
}

function facts(item: TaskItem, t: (k: string, v?: Record<string, string | number>) => string): string[] {
  return [item.size ? t("wish.sizeIs", { v: item.size }) : null, item.color ? t("wish.colorIs", { v: item.color }) : null,
    item.variant && item.variant !== item.text ? item.variant : null, (item.quantity ?? 1) > 1 ? t("wish.qtyIs", { n: item.quantity ?? 1 }) : null]
    .filter(Boolean) as string[];
}

function WishCard({ task, item, owner, onDetails, onJoin }: { task: Task; item: TaskItem; owner: boolean; onDetails: () => void; onJoin: () => void }) {
  const t = useT("privat");
  const { run } = usePrivat();
  const g = item.group_gift;
  const giverGift = isGiverGift(g) ? g : null;
  const ownerGift = !giverGift && g && (g as OwnerGroupGift).enabled;
  return (
    <article className="h-full rounded-[18px] border-2 border-ink bg-paper text-ink p-3 flex flex-col gap-2" data-testid="wish-card" aria-label={item.text}>
      <button type="button" onClick={onDetails} className="block w-full text-left rounded-[14px] focus-visible:outline-2" aria-label={t("wish.detailsOf", { title: item.text })}>
        <WishImage item={item} />
      </button>
      <div className="flex flex-wrap gap-1.5">
        {(giverGift || ownerGift) && <Pill tone="highlight">{t("wish.groupGift")}</Pill>}
        {item.archived && <Pill>{t("wish.removedByOwner")}</Pill>}
      </div>
      <h4 className="m-0 font-display font-bold text-[17px] leading-tight [overflow-wrap:anywhere]">{item.text}</h4>
      <PriceLine item={item} />
      {facts(item, t).length > 0 && <p className="m-0 text-[13px] text-ink-soft [overflow-wrap:anywhere]">{facts(item, t).join(" · ")}</p>}
      {item.note && <p className="m-0 text-[13px] text-ink-soft line-clamp-2 [overflow-wrap:anywhere]">{item.note}</p>}
      {giverGift && <GiftProgress gift={giverGift} compact />}
      <div className="mt-auto flex flex-wrap gap-2 pt-1">
        {item.link && (
          <a href={item.link} target="_blank" rel="noopener noreferrer nofollow" className={PCHIP}>
            <Ico name="external" size={16} />{t("wish.seeProduct")}
          </a>
        )}
        <button type="button" className={CHIP} onClick={onDetails}>{t("wish.details")}</button>
      </div>
      {!owner && !item.archived && (
        <div className="flex flex-wrap items-center gap-2 border-t-[1.5px] border-line pt-2">
          {giverGift ? <GiftActions task={task} item={item} gift={giverGift} onJoin={onJoin} /> : item.reserved_by_me ? (
            <><Pill tone="ok">{t("list.reservedByMe")}</Pill><button type="button" className={CHIP} onClick={() => run((a) => a.unreserve(task.id, item.id))}>{t("list.unreserve")}</button></>
          ) : item.reserved ? <Pill>{t("list.reserved")}</Pill> : (
            <button type="button" className={CHIP} onClick={() => run((a) => a.reserve(task.id, item.id))}>{t("list.reserve")}</button>
          )}
        </div>
      )}
    </article>
  );
}

// ---------------------------------------------------------------- detail view

function WishDetailSheet({ task, item, owner, onClose, onEdit, onJoin }: { task: Task; item: TaskItem; owner: boolean; onClose: () => void; onEdit: () => void; onJoin: () => void }) {
  const t = useT("privat");
  const f = useFmt();
  const fmt = useMoney();
  const { run } = usePrivat();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const d = item.details;
  const og = !isGiverGift(item.group_gift) ? (item.group_gift as OwnerGroupGift | null) : null;
  const rows: [string, React.ReactNode][] = [];
  if (item.shop) rows.push([t("wish.shop"), item.shop]);
  if (item.size) rows.push([t("wish.size"), item.size]);
  if (item.color) rows.push([t("wish.color"), item.color]);
  if (item.variant) rows.push([t("wish.variant"), item.variant]);
  rows.push([t("wish.quantity"), String(item.quantity ?? 1)]);
  if (d?.brand) rows.push([t("wish.brand"), d.brand]);
  if (d?.availability) rows.push([t("wish.availability"), t(`wish.avail.${d.availability}`)]);
  if (owner && og?.enabled && og.target_minor) rows.push([t("wish.groupGift"), t("wish.ownerTarget", { amount: fmt(og.target_minor, og.currency || "DKK") })]);
  return (
    <Sheet title={item.text} onClose={onClose}>
      <WishImage item={item} size="lg" />
      <PriceLine item={item} />
      {item.price_minor != null && item.price_source === "shop" && item.price_fetched_at && (
        <p className={HINT} data-testid="price-source">{t("wish.priceFrom", { shop: item.shop || t("wish.theShop"), date: f.date(item.price_fetched_at) })}</p>
      )}
      {d?.availability && <p className={HINT}>{t("wish.availabilityNote")}</p>}
      <dl className="grid grid-cols-[minmax(0,118px)_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[15px] m-0">
        {rows.map(([k, v]) => <div key={k} className="contents"><dt className="text-muted font-semibold text-[13px] pt-0.5">{k}</dt><dd className="m-0 [overflow-wrap:anywhere]">{v}</dd></div>)}
      </dl>
      {item.note && <div className="rounded-xl bg-panel p-3"><p className="m-0 text-[13px] font-semibold text-muted">{t("wish.note")}</p><p className="m-0 text-[15px] [overflow-wrap:anywhere]">{item.note}</p></div>}
      {d?.description && <p className="m-0 text-[14px] text-ink-soft [overflow-wrap:anywhere]">{d.description}</p>}
      {item.link && (
        <a href={item.link} target="_blank" rel="noopener noreferrer nofollow" className={`${BIG} inline-flex items-center justify-center gap-2 rounded-full bg-accent text-white border-accent font-semibold px-5 hover:bg-accent-deep`}>
          <Ico name="external" size={18} />{t("wish.seeProduct")}
        </a>
      )}
      {!owner && isGiverGift(item.group_gift) && <GiftPanel task={task} item={item} gift={item.group_gift} onJoin={onJoin} />}
      {owner && (
        <div className="flex flex-wrap gap-2 pt-1">
          <Button variant="outline" className="border-2 gap-2" onClick={onEdit}><Ico name="pencil" size={16} />{t("wish.edit")}</Button>
          {!confirmDelete ? (
            <Button variant="outline" className="border-2 gap-2" onClick={() => setConfirmDelete(true)}><Ico name="trash" size={16} />{t("wish.delete")}</Button>
          ) : (
            <div role="alert" className="w-full rounded-xl border-2 border-ink p-3 flex flex-col gap-2">
              <p className="m-0 text-[14px]">{og?.enabled ? t("wish.deleteGiftWarning") : t("wish.deleteConfirm")}</p>
              <div className="flex gap-2">
                <Button onClick={async () => { await run((a) => a.deleteItem(task.id, item.id)); onClose(); }}>{t("wish.deleteYes")}</Button>
                <Button variant="outline" className="border-2" onClick={() => setConfirmDelete(false)}>{t("wish.cancel")}</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
}

// ---------------------------------------------------------------- group gift (givers only)

function GiftProgress({ gift, compact = false }: { gift: GiverGroupGift; compact?: boolean }) {
  const t = useT("privat");
  const fmt = useMoney();
  const pct = Math.min(100, Math.round((gift.pledged_minor / Math.max(1, gift.target_minor)) * 100));
  const label = t("wish.giftAgreed", { pledged: fmt(gift.pledged_minor, gift.currency), target: fmt(gift.target_minor, gift.currency) });
  return (
    <div className="flex flex-col gap-1" data-testid="gift-progress">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2">
        <span className="text-[14px] font-semibold">{label}</span>
        <GiftState gift={gift} />
      </div>
      <div className="h-2.5 rounded-full bg-panel border-[1.5px] border-ink overflow-hidden" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      {!compact && (
        <span className="text-[13px] text-ink-soft">
          {gift.status === "open" ? t("wish.giftMissing", { amount: fmt(gift.remaining_minor, gift.currency) }) + " · " : ""}
          {t("wish.giftParticipants", { n: gift.participants })}
        </span>
      )}
      {compact && gift.status === "open" && <span className="text-[13px] text-ink-soft">{t("wish.giftMissing", { amount: fmt(gift.remaining_minor, gift.currency) })}</span>}
    </div>
  );
}

function GiftState({ gift }: { gift: GiverGroupGift }) {
  const t = useT("privat");
  const tone = gift.status === "bought" ? "ok" : gift.status === "full" ? "progress" : gift.status === "cancelled" ? "soon" : "plain";
  return <Pill tone={tone}>{t(`wish.giftStatus.${gift.status}`)}</Pill>;
}

function GiftActions({ task, item, gift, onJoin }: { task: Task; item: TaskItem; gift: GiverGroupGift; onJoin: () => void }) {
  const t = useT("privat");
  const fmt = useMoney();
  void task; void item;
  if (gift.status === "cancelled") return <span className="text-[13px] text-ink-soft">{t(gift.cancel_reason === "wish_removed" ? "wish.giftCancelledRemoved" : "wish.giftCancelledOff")}</span>;
  if (gift.my_pledge_minor != null) {
    return (
      <span className="flex flex-wrap items-center gap-2">
        <Pill tone="ok">{t("wish.yourPledge", { amount: fmt(gift.my_pledge_minor, gift.currency) })}</Pill>
        {gift.status !== "bought" && <button type="button" className={CHIP} onClick={onJoin}>{t("wish.changePledge")}</button>}
      </span>
    );
  }
  if (gift.reserved_by_me) return <span className="text-[13px] text-ink-soft">{t("wish.reservedByYouNoGift")}</span>;
  if (!gift.can_join) return <span className="text-[13px] text-ink-soft">{gift.status === "open" ? t("wish.giftReservedElsewhere") : t(`wish.giftStatus.${gift.status}`)}</span>;
  return <button type="button" className={PCHIP} onClick={onJoin} data-testid="join-gift"><Ico name="users" size={16} />{t("wish.joinGift")}</button>;
}

/** The whole agreement in the detail view: progress, own pledge, the coordinator and the actions it allows. */
function GiftPanel({ task, item, gift, onJoin }: { task: Task; item: TaskItem; gift: GiverGroupGift; onJoin: () => void }) {
  const t = useT("privat");
  const { api, refresh } = usePrivat();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [to, setTo] = useState("");
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await fn(); await refresh(); } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  const mine = gift.my_pledge_minor != null;
  return (
    <section className="rounded-[18px] border-2 border-ink p-3.5 flex flex-col gap-2.5 bg-paper" aria-label={t("wish.groupGift")} data-testid="gift-panel">
      <div className="flex items-center gap-2"><Ico name="users" size={18} /><h3 className="m-0 text-[16px] font-bold">{t("wish.groupGift")}</h3></div>
      <GiftProgress gift={gift} />
      <p className={HINT}>{t("wish.noMoneyMoves")}</p>
      <GiftActions task={task} item={item} gift={gift} onJoin={onJoin} />
      {mine && gift.status !== "bought" && gift.status !== "cancelled" && (
        <button type="button" disabled={busy} className="self-start min-h-[44px] text-[14px] font-semibold underline text-ink-soft" onClick={() => act(() => api.withdrawPledge(task.id, item.id))}>{t("wish.withdraw")}</button>
      )}
      {mine && gift.status !== "cancelled" && (
        <div className="flex flex-col gap-2 border-t-[1.5px] border-line pt-2.5">
          <p className="m-0 text-[14px]">
            {gift.coordinator ? (gift.coordinator.is_me ? t("wish.youCoordinate") : t("wish.coordinatorIs", { name: gift.coordinator.name ?? "" })) : t("wish.noCoordinator")}
          </p>
          {!gift.coordinator && <Button variant="outline" className="border-2 self-start" disabled={busy} onClick={() => act(() => api.giftCoordinator(task.id, item.id, "take"))}>{t("wish.takeCoordinator")}</Button>}
          {gift.pending_coordinator_is_me && (
            <div className="rounded-xl bg-highlight border-[1.5px] border-ink p-3 flex flex-col gap-2">
              <p className="m-0 text-[14px] font-semibold">{t("wish.handoverToYou")}</p>
              <div className="flex gap-2">
                <Button disabled={busy} onClick={() => act(() => api.giftCoordinator(task.id, item.id, "accept"))}>{t("wish.acceptRole")}</Button>
                <Button variant="outline" className="border-2" disabled={busy} onClick={() => act(() => api.giftCoordinator(task.id, item.id, "decline"))}>{t("wish.declineRole")}</Button>
              </div>
            </div>
          )}
          {gift.is_coordinator && (
            <>
              {gift.status !== "bought" ? (
                <Button disabled={busy} className="self-start" onClick={() => act(() => api.giftBought(task.id, item.id, true))} data-testid="mark-bought">{t("wish.markBought")}</Button>
              ) : (
                <Button variant="outline" className="border-2 self-start" disabled={busy} onClick={() => act(() => api.giftBought(task.id, item.id, false))}>{t("wish.unmarkBought")}</Button>
              )}
              <p className={HINT}>{t("wish.boughtNote")}</p>
              {gift.pending_coordinator_name ? (
                <p className="m-0 text-[14px]">{t("wish.handoverPending", { name: gift.pending_coordinator_name })} <button type="button" className="underline font-semibold min-h-[44px]" onClick={() => act(() => api.giftCoordinator(task.id, item.id, "cancel_transfer"))}>{t("wish.cancel")}</button></p>
              ) : (gift.participant_names?.length ?? 0) > 0 && (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex flex-col gap-1 min-w-[160px] flex-1"><span className={LABEL}>{t("wish.handoverTo")}</span>
                    <select className={FIELD} value={to} onChange={(e) => setTo(e.target.value)}>
                      <option value="">{t("wish.choosePerson")}</option>
                      {gift.participant_names!.map((p) => <option key={p.user_ref} value={p.user_ref}>{p.name}</option>)}
                    </select>
                  </label>
                  <Button variant="outline" className="border-2" disabled={!to || busy} onClick={() => act(() => api.giftCoordinator(task.id, item.id, "transfer", to))}>{t("wish.handover")}</Button>
                </div>
              )}
            </>
          )}
        </div>
      )}
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
    </section>
  );
}

/** «Vær med i gaven» / «Ret beløb»: an amount of your own choice, what is left shown clearly, nothing is charged. */
function PledgeSheet({ task, item, gift, onClose }: { task: Task; item: TaskItem; gift: GiverGroupGift; onClose: () => void }) {
  const t = useT("privat");
  const locale = useLocale();
  const fmt = useMoney();
  const { api, refresh } = usePrivat();
  const others = gift.pledged_minor - (gift.my_pledge_minor ?? 0);
  const left = gift.target_minor - others;
  const [raw, setRaw] = useState(gift.my_pledge_minor != null ? amountInput(gift.my_pledge_minor, gift.currency, locale) : "");
  const [err, setErr] = useState<string | null>(null);
  const [proposal, setProposal] = useState<number | null>(null);
  const [done, setDone] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const key = useRef(newKey());  // one key per attempt: a double click or a retry is the same pledge
  const amount = parseAmount(raw, gift.currency);
  const submit = async (minor: number) => {
    setBusy(true); setErr(null);
    try {
      await api.pledge(task.id, item.id, minor, key.current);
      key.current = newKey();
      setDone(minor); setProposal(null);
      await refresh();
    } catch (e) {
      const x = e as ApiError & { remaining_minor?: number };
      key.current = newKey();
      if (x.code === "pledge_exceeds_remaining" && x.remaining_minor) { setProposal(x.remaining_minor); setErr(null); }
      else setErr(errText(e));
      await refresh().catch(() => {});
    } finally { setBusy(false); }
  };
  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (amount == null || amount <= 0) { setErr(t("wish.amountInvalid")); return; }
    if (amount > left) { setProposal(left); return; }  // shown at once; the server checks again
    void submit(amount);
  };
  return (
    <Sheet title={done != null ? t("wish.pledgeDoneTitle") : gift.my_pledge_minor != null ? t("wish.changePledge") : t("wish.joinGift")} onClose={onClose}>
      {done != null ? (
        <div className="flex flex-col gap-3" role="status" data-testid="pledge-done">
          <p className="m-0 text-[16px]">{t("wish.pledgeDone", { amount: fmt(done, gift.currency), title: item.text })}</p>
          <p className={HINT}>{t("wish.noMoneyMoves")}</p>
          <p className={HINT}>{t("wish.pledgeChangeLater")}</p>
          <Button className={BIG} onClick={onClose}>{t("wish.ok")}</Button>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-3" noValidate>
          <p className="m-0 text-[15px] font-semibold [overflow-wrap:anywhere]">{item.text}</p>
          <GiftProgress gift={gift} />
          <p className="m-0 text-[15px]">{t("wish.leftForYou", { amount: fmt(Math.max(0, left), gift.currency) })}</p>
          <label className="flex flex-col gap-1">
            <span className={LABEL}>{t("wish.yourAmount", { currency: gift.currency })}</span>
            <input className={FIELD} inputMode="decimal" autoComplete="off" value={raw} onChange={(e) => { setRaw(e.target.value); setProposal(null); setErr(null); }}
              aria-invalid={!!err} aria-describedby="pledge-help" data-autofocus placeholder={amountInput(Math.min(left, Math.round(gift.target_minor / 4)), gift.currency, locale)} />
          </label>
          <p id="pledge-help" className="m-0 text-[14px] font-semibold rounded-xl bg-highlight border-[1.5px] border-ink p-3">{t("wish.noMoneyMoves")}</p>
          {proposal != null && (
            <div role="alert" className="rounded-xl border-2 border-ink p-3 flex flex-col gap-2" data-testid="pledge-proposal">
              <p className="m-0 text-[14px]">{t("wish.tooHigh", { amount: fmt(proposal, gift.currency) })}</p>
              <div className="flex flex-wrap gap-2">
                <Button type="button" disabled={busy} onClick={() => { setRaw(amountInput(proposal, gift.currency, locale)); void submit(proposal); }}>{t("wish.useRemaining", { amount: fmt(proposal, gift.currency) })}</Button>
                <Button type="button" variant="outline" className="border-2" onClick={() => setProposal(null)}>{t("wish.chooseOther")}</Button>
              </div>
            </div>
          )}
          {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
          <Button type="submit" className={BIG} disabled={busy || proposal != null}>{gift.my_pledge_minor != null ? t("wish.savePledge") : t("wish.joinWith", { amount: amount ? fmt(amount, gift.currency) : "…" })}</Button>
        </form>
      )}
    </Sheet>
  );
}

// ---------------------------------------------------------------- «Tilføj ønske»

type Way = "choose" | "search" | "link" | "form";

function AddWishSheet({ task, onClose }: { task: Task; onClose: () => void }) {
  const t = useT("privat");
  const [way, setWay] = useState<Way>("choose");
  const [imported, setImported] = useState<WishImport | null>(null);
  const [linkOnly, setLinkOnly] = useState<string | null>(null);
  const title = way === "search" ? t("wish.searchTitle") : way === "link" ? t("wish.linkTitle") : way === "form" ? t("wish.formTitle") : t("wish.add");
  return (
    <Sheet title={title} onClose={onClose}>
      {way === "choose" && (
        <div className="flex flex-col gap-2" data-testid="add-wish-ways">
          {([["search", "search", "wish.waySearch", "wish.waySearchSub"], ["link", "link", "wish.wayLink", "wish.wayLinkSub"], ["form", "pencil", "wish.wayManual", "wish.wayManualSub"]] as const).map(([w, icon, label, sub]) => (
            <button key={w} type="button" onClick={() => setWay(w)} className="w-full min-h-[64px] flex items-center gap-3 text-left rounded-[14px] border-2 border-ink bg-paper px-3.5 py-3 hover:bg-panel">
              <span className="w-10 h-10 rounded-[10px] bg-accent text-white inline-flex items-center justify-center"><Ico name={icon} size={20} /></span>
              <span className="flex-1 min-w-0 flex flex-col"><span className="font-semibold text-[16px]">{t(label)}</span><span className="text-[13px] text-ink-soft">{t(sub)}</span></span>
              <Ico name="chevron" size={18} />
            </button>
          ))}
        </div>
      )}
      {way === "search" && <SearchStep onPick={(imp) => { setImported(imp); setWay("form"); }} onFallback={(w) => setWay(w)} />}
      {way === "link" && <LinkStep onDone={(imp) => { setImported(imp.readable ? imp : null); setLinkOnly(imp.readable ? null : imp.link); setWay("form"); }} onManual={() => setWay("form")} />}
      {way === "form" && <WishForm task={task} imported={imported} linkOnly={linkOnly} onDone={onClose} onBack={() => { setImported(null); setLinkOnly(null); setWay("choose"); }} />}
    </Sheet>
  );
}

function SearchStep({ onPick, onFallback }: { onPick: (imp: WishImport) => void; onFallback: (w: "link" | "form") => void }) {
  const t = useT("privat");
  const fmt = useMoney();
  const { api } = usePrivat();
  const [q, setQ] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "done" | "error" | "unavailable" | "picking">("idle");
  const [rows, setRows] = useState<WishSearchResult[]>([]);
  const [err, setErr] = useState("");
  const go = async (e: React.FormEvent) => {
    e.preventDefault();
    if (q.trim().length < 2) return;
    setState("loading"); setErr("");
    try { const r = await api.searchWishes(q.trim()); setRows(r.results); setState("done"); }
    catch (x) { const a = x as ApiError; if (a.code === "search_unavailable") setState("unavailable"); else { setErr(errText(x)); setState("error"); } }
  };
  const pick = async (r: WishSearchResult) => {
    setState("picking");
    try { onPick(await api.importWish(r.link)); }
    catch (x) { setErr(errText(x)); setState("error"); }
  };
  if (state === "unavailable") {
    return (
      <div className="flex flex-col gap-3" role="status" data-testid="search-unavailable">
        <p className="m-0 text-[15px]">{t("wish.searchUnavailable")}</p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => onFallback("link")}><Ico name="link" size={16} />{t("wish.wayLink")}</Button>
          <Button variant="outline" className="border-2" onClick={() => onFallback("form")}><Ico name="pencil" size={16} />{t("wish.wayManual")}</Button>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={go} className="flex gap-2" role="search">
        <label htmlFor="wish-q" className={SR}>{t("wish.searchLabel")}</label>
        <input id="wish-q" className={FIELD} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("wish.searchPlaceholder")} autoComplete="off" data-autofocus />
        <Button type="submit" className={BIG} disabled={state === "loading" || q.trim().length < 2}><Ico name="search" size={18} /><span className="sr-only sm:not-sr-only">{t("wish.searchGo")}</span></Button>
      </form>
      {state === "loading" && <p className="m-0 text-[14px] text-ink-soft" role="status" aria-live="polite">{t("wish.searching")}</p>}
      {state === "picking" && <p className="m-0 text-[14px] text-ink-soft" role="status" aria-live="polite">{t("wish.reading")}</p>}
      {state === "error" && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      {state === "done" && rows.length === 0 && (
        <div className="flex flex-col gap-2"><p className="m-0 text-[15px]">{t("wish.noResults")}</p>
          <div className="flex flex-wrap gap-2"><button type="button" className={CHIP} onClick={() => onFallback("link")}>{t("wish.wayLink")}</button><button type="button" className={CHIP} onClick={() => onFallback("form")}>{t("wish.wayManual")}</button></div></div>
      )}
      {state === "done" && rows.length > 0 && (
        <ul className="list-none m-0 p-0 flex flex-col gap-2" aria-label={t("wish.results")}>
          {rows.map((r) => (
            <li key={r.link}>
              <button type="button" onClick={() => pick(r)} className="w-full flex gap-3 text-left rounded-[14px] border-2 border-ink bg-paper p-2.5 hover:bg-panel">
                <span className="w-20 h-20 shrink-0 rounded-xl bg-panel overflow-hidden flex items-center justify-center">
                  {r.image_url
                    // eslint-disable-next-line @next/next/no-img-element -- the shop's own picture, only in the results list
                    ? <img src={r.image_url} alt="" referrerPolicy="no-referrer" loading="lazy" className="w-full h-full object-contain" onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
                    : <Ico name="gift" size={28} className="text-muted" />}
                </span>
                <span className="flex-1 min-w-0 flex flex-col gap-0.5">
                  <span className="font-semibold text-[15px] line-clamp-2 [overflow-wrap:anywhere]">{r.title}</span>
                  <span className="text-[14px]">{r.price_minor != null && r.currency ? fmt(r.price_minor, r.currency) : t("wish.noPrice")}</span>
                  <span className="text-[12px] text-muted">{[r.shop, r.options?.sizes?.length ? t("wish.nSizes", { n: r.options.sizes.length }) : null, r.options?.colors?.length ? t("wish.nColors", { n: r.options.colors.length }) : null].filter(Boolean).join(" · ")}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LinkStep({ onDone, onManual }: { onDone: (imp: WishImport) => void; onManual: () => void }) {
  const t = useT("privat");
  const { api } = usePrivat();
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const go = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!link.trim()) return;
    setBusy(true); setErr("");
    try { onDone(await api.importWish(link.trim())); }
    catch (x) { setErr(errText(x)); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={go} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1"><span className={LABEL}>{t("wish.linkLabel")}</span>
        <input className={FIELD} type="url" inputMode="url" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://" autoComplete="off" data-autofocus aria-invalid={!!err} />
      </label>
      <p className={HINT}>{t("wish.linkHelp")}</p>
      {busy && <p className="m-0 text-[14px] text-ink-soft" role="status" aria-live="polite">{t("wish.reading")}</p>}
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      <Button type="submit" className={BIG} disabled={busy || !link.trim()}>{t("wish.fetch")}</Button>
      <button type="button" className="self-start min-h-[44px] text-[14px] font-semibold underline" onClick={onManual}>{t("wish.wayManual")}</button>
    </form>
  );
}

// ---------------------------------------------------------------- the one wish form

type Form = {
  text: string; link: string; price: string; currency: string; size: string; color: string; variant: string; quantity: string; note: string; shop: string;
  imageKey: string | null; image: { url: string; url_sm: string } | null; imageOrigin: "shop" | "upload" | null;
  gift: boolean; target: string;
};
type FormKey = "text" | "link" | "price" | "currency" | "size" | "color" | "variant" | "shop";

function WishFormSheet({ task, item, onClose }: { task: Task; item: TaskItem; onClose: () => void }) {
  const t = useT("privat");
  return <Sheet title={t("wish.editTitle")} onClose={onClose}><WishForm task={task} item={item} onDone={onClose} /></Sheet>;
}

function WishForm({ task, item, imported, linkOnly, onDone, onBack }: { task: Task; item?: TaskItem; imported?: WishImport | null; linkOnly?: string | null; onDone: () => void; onBack?: () => void }) {
  const t = useT("privat");
  const locale = useLocale();
  const fmt = useMoney();
  const f = useFmt();
  const { api, refresh } = usePrivat();
  const og = item && !isGiverGift(item.group_gift) ? (item.group_gift as OwnerGroupGift | null) : null;
  const defCurrency = item?.currency || imported?.currency || currencyFor(locale) || "DKK";
  const [v, setV] = useState<Form>(() => ({
    text: item?.text ?? imported?.title ?? "", link: item?.link ?? imported?.link ?? linkOnly ?? "",
    price: amountInput(item?.price_minor ?? imported?.price_minor ?? null, defCurrency, locale), currency: defCurrency,
    size: item?.size ?? imported?.size ?? "", color: item?.color ?? imported?.color ?? "", variant: item?.variant ?? imported?.variant ?? "",
    quantity: String(item?.quantity ?? 1), note: item?.note ?? "", shop: item?.shop ?? imported?.shop ?? "",
    imageKey: null, image: item?.image ?? imported?.image ?? null, imageOrigin: item?.image_origin ?? (imported?.image ? "shop" : null),
    gift: !!og?.enabled, target: amountInput(og?.target_minor ?? null, defCurrency, locale),
  }));
  // Fields the user has changed by hand: a later «Hent oplysninger» never overwrites them without an active choice.
  const touched = useRef<Set<FormKey>>(new Set(item ? (["text", "link", "price", "currency", "size", "color", "variant", "shop"] as FormKey[]) : []));
  const [fetched, setFetched] = useState<WishImport | null>(imported ?? null);
  const [offers, setOffers] = useState<Partial<Record<FormKey, string>>>({});
  const [priceFromShop, setPriceFromShop] = useState<{ at: string } | null>(
    item?.price_source === "shop" && item.price_fetched_at ? { at: item.price_fetched_at } : imported?.price_minor != null ? { at: imported.fetched_at } : null);
  const [imageKeyFromImport] = useState<string | null>(imported?.image_key ?? null);
  const [err, setErr] = useState<{ field?: string; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const options: WishOptions | null | undefined = fetched?.options ?? item?.details?.options;
  const set = (k: FormKey, val: string) => {
    touched.current.add(k);
    if (k === "price" || k === "currency") setPriceFromShop(null);  // a typed price is the user's, not the shop's
    setV((x) => ({ ...x, [k]: val }));
    setOffers((o) => { const n = { ...o }; delete n[k]; return n; });
  };
  // Suggest the price as the group gift's target when the box is ticked (the owner may change it).
  useEffect(() => { if (v.gift && !v.target && v.price) setV((x) => ({ ...x, target: x.price })); }, [v.gift, v.target, v.price]);

  const refetch = async () => {
    if (!v.link.trim()) return;
    setFetching(true); setErr(null);
    try {
      const imp = await api.importWish(v.link.trim());
      setFetched(imp);
      const vals: Partial<Record<FormKey, string>> = {
        text: imp.title ?? undefined, link: imp.link, shop: imp.shop ?? undefined, size: imp.size ?? undefined, color: imp.color ?? undefined,
        variant: imp.variant ?? undefined, price: imp.price_minor != null ? amountInput(imp.price_minor, imp.currency || v.currency, locale) : undefined,
        currency: imp.currency ?? undefined,
      };
      const next: Partial<Form> = {}; const offer: Partial<Record<FormKey, string>> = {};
      for (const [k, val] of Object.entries(vals) as [FormKey, string | undefined][]) {
        if (val == null || val === "" || val === v[k]) continue;
        if (touched.current.has(k) && v[k]) offer[k] = val; else (next as Record<string, string>)[k] = val;
      }
      setV((x) => ({ ...x, ...next, ...(imp.image && !x.image ? { image: imp.image, imageKey: imp.image_key ?? null, imageOrigin: "shop" as const } : {}) }));
      setOffers(offer);
      if (imp.price_minor != null && !offer.price) setPriceFromShop({ at: imp.fetched_at });
      if (!imp.readable) setErr({ msg: t("wish.couldNotRead") });
    } catch (x) { setErr({ field: "link", msg: errText(x) }); }
    finally { setFetching(false); }
  };
  const upload = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true); setErr(null);
    try { const r = await api.uploadWishImage(file); setV((x) => ({ ...x, imageKey: r.image_key, image: r.image, imageOrigin: "upload" })); }
    catch (x) { setErr({ field: "image", msg: errText(x) }); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!v.text.trim()) { setErr({ field: "text", msg: t("wish.titleRequired") }); return; }
    const price = v.price.trim() ? parseAmount(v.price, v.currency) : null;
    if (v.price.trim() && price == null) { setErr({ field: "price", msg: t("wish.amountInvalid") }); return; }
    const qty = Number(v.quantity || "1");
    if (!Number.isInteger(qty) || qty < 1 || qty > 99) { setErr({ field: "quantity", msg: t("wish.qtyInvalid") }); return; }
    const target = v.gift ? parseAmount(v.target, v.currency) : null;
    if (v.gift && (target == null || target <= 0)) { setErr({ field: "target", msg: t("wish.targetInvalid") }); return; }
    const body: WishBody = {
      text: v.text.trim(), link: v.link.trim() || null, note: v.note.trim() || null, quantity: qty, price_minor: price, currency: price != null || v.gift ? v.currency : null,
      price_source: price != null && priceFromShop ? "shop" : price != null ? "user" : null, price_fetched_at: price != null && priceFromShop ? priceFromShop.at : null,
      shop: v.shop.trim() || null, size: v.size.trim() || null, color: v.color.trim() || null, variant: v.variant.trim() || null,
      group_gift_enabled: v.gift, group_gift_target_minor: v.gift ? target : og?.target_minor ?? null,
    };
    const key = v.imageKey ?? (!item && v.image ? imageKeyFromImport : null);
    if (key) { body.image_key = key; body.image_origin = v.imageOrigin ?? "upload"; }
    else if (item && item.image && !v.image) body.image_key = null;
    if (fetched?.details || (!item && imported?.details)) body.details = { ...(fetched?.details ?? imported?.details ?? {}), options: options ?? undefined };
    setBusy(true);
    try {
      if (item) await api.editWish(task.id, item.id, body); else await api.addWish(task.id, body);
      await refresh();
      onDone();
    } catch (x) {
      const a = x as ApiError;
      setErr({ field: a.field_errors?.[0]?.field, msg: a.field_errors?.[0]?.message || errText(x) });
    } finally { setBusy(false); }
  };
  const fe = (k: string) => (err?.field === k ? err.msg : null);
  const Offer = ({ k }: { k: FormKey }) => offers[k] ? (
    <p className="m-0 text-[13px] flex flex-wrap items-center gap-2" data-testid={`offer-${k}`}>{t("wish.shopSays", { v: offers[k]! })}
      <button type="button" className="underline font-semibold min-h-[36px]" onClick={() => { setV((x) => ({ ...x, [k]: offers[k]! })); if (k === "price" && fetched?.price_minor != null) setPriceFromShop({ at: fetched.fetched_at }); setOffers((o) => { const n = { ...o }; delete n[k]; return n; }); }}>{t("wish.useIt")}</button></p>
  ) : null;
  const sel = (k: "size" | "color", list: string[] | undefined) => list && list.length > 0 ? (
    <select className={FIELD} value={list.includes(v[k]) ? v[k] : ""} onChange={(e) => set(k, e.target.value)} aria-label={t(`wish.${k}`)}>
      <option value="">{t("wish.choose")}</option>
      {list.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  ) : null;
  return (
    <form onSubmit={save} className="flex flex-col gap-3.5" noValidate data-testid="wish-form">
      {fetched && !fetched.readable && <p role="status" className="m-0 rounded-xl bg-highlight border-[1.5px] border-ink p-3 text-[14px]">{t("wish.couldNotRead")}</p>}
      {!fetched && linkOnly && <p role="status" className="m-0 rounded-xl bg-highlight border-[1.5px] border-ink p-3 text-[14px]">{t("wish.couldNotRead")}</p>}
      {fetched?.readable && <p className={HINT}>{t("wish.checkBeforeSave")}</p>}
      {/* picture */}
      <div className="flex gap-3 items-start">
        <div className="w-28 shrink-0"><WishImage item={{ id: "x", text: v.text || t("wish.title"), done: false, image: v.image }} /></div>
        <div className="flex flex-col gap-2 min-w-0">
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" id="wish-file" onChange={(e) => upload(e.target.files?.[0])} />
          <label htmlFor="wish-file" className={`${CHIP} cursor-pointer`}><Ico name="image" size={16} />{v.image ? t("wish.changeImage") : t("wish.addImage")}</label>
          {v.image && <button type="button" className="self-start min-h-[44px] text-[14px] underline" onClick={() => setV((x) => ({ ...x, image: null, imageKey: null, imageOrigin: null }))}>{t("wish.removeImage")}</button>}
          {uploading && <span className="text-[13px] text-ink-soft" role="status">{t("wish.uploading")}</span>}
          {fe("image") && <span role="alert" className="text-[13px] text-danger font-semibold">{fe("image")}</span>}
          <span className="text-[12px] text-muted">{t("wish.imageHelp")}</span>
        </div>
      </div>
      <label className="flex flex-col gap-1"><span className={LABEL}>{t("wish.title")}</span>
        <input className={FIELD} value={v.text} onChange={(e) => set("text", e.target.value)} maxLength={300} aria-invalid={!!fe("text")} data-autofocus />
        {fe("text") && <span role="alert" className="text-[13px] text-danger font-semibold">{fe("text")}</span>}
        <Offer k="text" />
      </label>
      <div className="flex flex-col gap-1">
        <label htmlFor="wish-link" className={LABEL}>{t("wish.link")} <span className="font-normal text-muted">{t("wish.optional")}</span></label>
        <div className="flex gap-2">
          <input id="wish-link" className={FIELD} type="url" inputMode="url" value={v.link} onChange={(e) => set("link", e.target.value)} placeholder="https://" aria-invalid={!!fe("link")} />
          {v.link.trim() && <Button type="button" variant="outline" className="border-2 shrink-0" disabled={fetching} onClick={refetch}>{fetching ? t("wish.reading") : t("wish.fetchShort")}</Button>}
        </div>
        {fe("link") && <span role="alert" className="text-[13px] text-danger font-semibold">{fe("link")}</span>}
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_110px] gap-2">
        <label className="flex flex-col gap-1"><span className={LABEL}>{t("wish.price")} <span className="font-normal text-muted">{t("wish.optional")}</span></span>
          <input className={FIELD} inputMode="decimal" value={v.price} onChange={(e) => set("price", e.target.value)} placeholder={t("wish.noPrice")} aria-invalid={!!fe("price") || !!fe("price_minor")} />
        </label>
        <label className="flex flex-col gap-1"><span className={LABEL}>{t("wish.currency")}</span>
          <select className={FIELD} value={v.currency} onChange={(e) => set("currency", e.target.value)}>
            {[...new Set([v.currency, ...CURRENCIES])].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>
      {(fe("price") || fe("price_minor")) && <span role="alert" className="-mt-2 text-[13px] text-danger font-semibold">{fe("price") || fe("price_minor")}</span>}
      <Offer k="price" />
      {priceFromShop && v.price && <p className="-mt-1 m-0 text-[12px] text-muted">{t("wish.priceFrom", { shop: v.shop || t("wish.theShop"), date: f.date(priceFromShop.at) })}</p>}
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1"><span className={LABEL}>{t("wish.size")}</span>
          {sel("size", options?.sizes) ?? <input className={FIELD} value={v.size} onChange={(e) => set("size", e.target.value)} placeholder={t("wish.sizePlaceholder")} />}
        </label>
        <label className="flex flex-col gap-1"><span className={LABEL}>{t("wish.color")}</span>
          {sel("color", options?.colors) ?? <input className={FIELD} value={v.color} onChange={(e) => set("color", e.target.value)} placeholder={t("wish.colorPlaceholder")} />}
        </label>
      </div>
      <Offer k="size" /><Offer k="color" />
      <div className="grid grid-cols-[minmax(0,1fr)_96px] gap-2">
        <label className="flex flex-col gap-1"><span className={LABEL}>{t("wish.variant")}</span>
          {options?.variants?.length ? (
            <select className={FIELD} value={v.variant} onChange={(e) => { const name = e.target.value; const vv = options.variants.find((x) => x.name === name); set("variant", name); if (vv?.size) set("size", vv.size); if (vv?.color) set("color", vv.color); }}>
              <option value="">{t("wish.choose")}</option>
              {options.variants.filter((x) => x.name).map((x) => <option key={x.name} value={x.name}>{x.name}{x.availability === "out_of_stock" ? ` (${t("wish.avail.out_of_stock")})` : ""}</option>)}
            </select>
          ) : <input className={FIELD} value={v.variant} onChange={(e) => set("variant", e.target.value)} placeholder={t("wish.variantPlaceholder")} />}
        </label>
        <label className="flex flex-col gap-1"><span className={LABEL}>{t("wish.quantity")}</span>
          <input className={FIELD} inputMode="numeric" value={v.quantity} onChange={(e) => setV((x) => ({ ...x, quantity: e.target.value.replace(/\D/g, "").slice(0, 2) }))} aria-invalid={!!fe("quantity")} />
        </label>
      </div>
      {fe("quantity") && <span role="alert" className="-mt-2 text-[13px] text-danger font-semibold">{fe("quantity")}</span>}
      <label className="flex flex-col gap-1"><span className={LABEL}>{t("wish.note")} <span className="font-normal text-muted">{t("wish.optional")}</span></span>
        <textarea className={`${FIELD} py-2.5 min-h-[80px]`} value={v.note} onChange={(e) => setV((x) => ({ ...x, note: e.target.value }))} maxLength={500} placeholder={t("wish.notePlaceholder")} />
      </label>
      {/* «Tillad fællesgave» */}
      <div className="rounded-[14px] border-2 border-ink p-3 flex flex-col gap-2">
        <label className="flex items-start gap-3 min-h-[44px] cursor-pointer">
          <input type="checkbox" className="mt-1 w-5 h-5 accent-[var(--color-accent)]" checked={v.gift} onChange={(e) => setV((x) => ({ ...x, gift: e.target.checked }))} data-testid="allow-gift" />
          <span className="flex flex-col"><span className="font-semibold text-[15px]">{t("wish.allowGift")}</span><span className="text-[13px] text-ink-soft">{t("wish.allowGiftHelp")}</span></span>
        </label>
        {v.gift && (
          <label className="flex flex-col gap-1"><span className={LABEL}>{t("wish.target", { currency: v.currency })}</span>
            <input className={FIELD} inputMode="decimal" value={v.target} onChange={(e) => setV((x) => ({ ...x, target: e.target.value }))} aria-invalid={!!fe("target") || !!fe("group_gift_target_minor")} data-testid="gift-target" />
            {(fe("target") || fe("group_gift_target_minor")) && <span role="alert" className="text-[13px] text-danger font-semibold">{fe("target") || fe("group_gift_target_minor")}</span>}
            <span className="text-[12px] text-muted">{t("wish.targetHelp")}{v.target && parseAmount(v.target, v.currency) ? ` · ${fmt(parseAmount(v.target, v.currency)!, v.currency)}` : ""}</span>
          </label>
        )}
        {og?.enabled && !v.gift && <p className={HINT}>{t("wish.giftOffNote")}</p>}
      </div>
      {err && !err.field && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err.msg}</p>}
      {err?.field && !["text", "link", "price", "price_minor", "quantity", "target", "group_gift_target_minor", "image"].includes(err.field) && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err.msg}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" className={BIG} disabled={busy || uploading}>{busy ? t("wish.saving") : t("wish.save")}</Button>
        {onBack && <Button type="button" variant="outline" className="border-2" onClick={onBack}>{t("wish.back")}</Button>}
      </div>
    </form>
  );
}
