"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui";
import { useRaw, useT } from "@/i18n/client";
import { ADDON, CONFLICT, type Task } from "@/lib/privat/api";
import type { ApiError, ApiError as ClientApiError } from "@/lib/client";
import { FAKE_SMS_CODE } from "@/lib/privat/fake";
import { Avatars, BIG, CheckBox, CHIP, Eyebrow, Ex, Kv, LINK, Pill, Sim, SR } from "./bits";
import { Ico, Tile } from "./icons";
import { useFmt, usePlan, usePrivat } from "./store";
import { addonIncluded, addonText } from "./addons";
import { PushPrompt } from "./push";
import { isDanishMobile } from "@/lib/privat/fake";
import { platformOf, smsHref } from "@/lib/privat/sms";

const CARD = "rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5";
const PROPOSAL = "rounded-[18px] border-2 border-dashed border-ink bg-paper p-4 flex flex-col gap-3";
const OK = "rounded-[18px] border-2 border-success bg-success-soft p-4 flex flex-col gap-2.5";
const BAD = "rounded-[18px] border-2 border-ink bg-panel p-4 flex flex-col gap-2.5";

// ---------------------------------------------------------------- lists

const isWish = (t: Task) => t.list_type === "wishlist" || t.share_mode === "wishlist";
const isOwner = (t: Task) => !t.my_role || t.my_role === "owner";

/** A list in all its shapes: own list, shared group list (who added / ticked off), wishlist for the owner (never any
 *  reservation info) and wishlist for the others («Jeg køber den» / «Fortryd» / «Reserveret»). */
export function ListBody({ task, withAdd = false }: { task: Task; withAdd?: boolean }) {
  const t = useT("privat");
  const { run, simulated, fake, addonOn, openSheet } = usePrivat();
  const wish = isWish(task);
  const owner = isOwner(task);
  const doneCount = task.items.filter((i) => i.done).length;
  const canEdit = task.my_role !== "viewer";
  const canShare = owner && (addonOn(ADDON.sharedLists) || (wish && addonOn(ADDON.wishlists)));
  const others = (task.members ?? []).filter((m) => !m.is_me);
  return (
    <div className="flex flex-col gap-2.5">
      {task.shared && (task.members?.length ?? 0) > 0 && (
        <div className="flex items-center gap-2.5 flex-wrap">
          <Avatars names={(task.members ?? []).map((m) => m.name)} />
          <span className="text-[13px] text-ink-soft min-w-0">{owner ? t("list.sharedWith", { names: others.map((m) => m.name).join(", ") || "–" }) : t("list.sharedBy", { name: task.members?.find((m) => m.role === "owner")?.name ?? "" })}</span>
        </div>
      )}
      {wish && owner && <p className="m-0 text-[13px] text-muted">{t("list.ownerNote")}</p>}
      {task.items.length === 0 && <p className="m-0 text-[14px] text-muted">{t("list.emptyItems")}</p>}
      <ul className="list-none m-0 p-0 flex flex-col gap-0.5">
        {task.items.map((it) => (
          <li key={it.id} className="flex flex-col">
            {wish ? (
              <div className="flex flex-wrap items-start gap-x-3 gap-y-1.5 min-h-[44px] py-1.5 px-1">
                <span className="mt-0.5 text-accent"><Ico name="gift" size={20} /></span>
                <span className="flex-1 min-w-[55%] flex flex-col gap-0.5">
                  <span className="text-[16px] [overflow-wrap:anywhere]">{it.text}</span>
                  {it.note && <span className="text-[13px] text-ink-soft [overflow-wrap:anywhere]">{it.note}</span>}
                  {it.link && <a href={it.link} target="_blank" rel="noopener noreferrer nofollow" className="text-[13px] text-accent underline [overflow-wrap:anywhere]">{t("list.openLink")}</a>}
                </span>
                {!owner && (it.reserved_by_me ? (
                  <span className="flex items-center gap-2 shrink-0 ml-auto"><Pill tone="ok">{t("list.reservedByMe")}</Pill>
                    <button type="button" className={CHIP} onClick={() => run((a) => a.unreserve(task.id, it.id))}>{t("list.unreserve")}</button></span>
                ) : it.reserved ? <span className="ml-auto"><Pill>{t("list.reserved")}</Pill></span> : (
                  <button type="button" className={`${CHIP} shrink-0 ml-auto`} onClick={() => run((a) => a.reserve(task.id, it.id))}>{t("list.reserve")}</button>
                ))}
              </div>
            ) : (
              <button type="button" aria-pressed={it.done} disabled={!canEdit} onClick={() => run((a) => a.toggleItem(task.id, it.id))}
                className="w-full min-h-[44px] flex items-center gap-3 rounded-lg px-1 text-left text-[16px] text-ink hover:bg-panel disabled:hover:bg-transparent">
                <CheckBox done={it.done} />
                <span className={`flex-1 min-w-0 [overflow-wrap:anywhere] ${it.done ? "line-through text-muted" : ""}`}>{it.text}</span>
              </button>
            )}
            {(it.added_by_name || it.done_by_name) && (
              <span className="pl-10 -mt-1 pb-1 text-[12px] text-muted">
                {[it.added_by_name ? t("list.addedBy", { name: it.added_by_name, item: it.text.toLowerCase() }) : null, it.done && it.done_by_name ? t("list.doneBy", { name: it.done_by_name }) : null].filter(Boolean).join(" · ")}
              </span>
            )}
          </li>
        ))}
      </ul>
      {withAdd && canEdit && (owner || !wish) && <AddItem task={task} wish={wish} />}
      {!withAdd && <span className="text-[13px] text-muted">{t("list.count", { n: task.items.length, done: doneCount })}</span>}
      <div className="flex flex-wrap gap-2 items-center">
        {canShare && (
          <Button variant="outline" icon={undefined} onClick={() => openSheet({ kind: "share", taskId: task.id })} className="gap-2">
            <Ico name="share" size={18} />{task.shared ? t("list.shareManage") : t("list.share")}
          </Button>
        )}
        {simulated && fake && task.shared && owner && (
          <>
            <Button variant="tonal" onClick={() => run((a) => (a as typeof fake).simulateMember(task.id))}>
              {wish ? t("list.simulateReserve", { name: "Anna" }) : t("list.simulateMember", { name: "Anna" })} <Sim />
            </Button>
            {others.some((m) => m.id === "anna") && (
              <Button variant="tonal" onClick={() => run((a) => (a as typeof fake).simulateInviteeActivated())}>{t("list.simulateActivated", { name: "Anna" })} <Sim /></Button>
            )}
          </>
        )}
      </div>
      {task.shared && owner && withAdd && <PeopleStatus task={task} />}
      {task.shared && (
        <p className="m-0 pt-2 border-t-[1.5px] border-line text-[12px] text-muted">
          {t("list.sharedVia")} · <Link href={`/privat?ref=${encodeURIComponent(task.id)}`} className="underline underline-offset-2 hover:text-ink">{t("list.makeOwn")}</Link>
        </p>
      )}
    </div>
  );
}

/** After sharing: who is in, who opened the link, who has not opened it yet. «Påmind» opens a new SMS from the user's
 *  own phone (we have no numbers here, so the user picks the person in Messages). */
function PeopleStatus({ task }: { task: Task }) {
  const t = useT("privat");
  const { api, simulated, fake, refresh } = usePrivat();
  const [rows, setRows] = useState<{ name: string; status: "member" | "opened" | "invited" }[] | null>(null);
  const [ua, setUa] = useState("");
  useEffect(() => {
    let alive = true;
    setUa(navigator.userAgent);
    api.inviteStatus(task.id).then((r) => { if (alive) setRows(r); }).catch(() => { if (alive) setRows(null); });
    return () => { alive = false; };
  }, [api, task.id, task.updated_at, task.members?.length]);
  if (!rows || rows.length === 0) return null;
  const tone = { member: "ok", opened: "progress", invited: "soon" } as const;
  const remind = smsHref(t(isWish(task) ? "share.remindWishlist" : "share.remindGroup", { title: task.title }), [], platformOf(ua));
  return (
    <div className="flex flex-col gap-1.5 border-t-[1.5px] border-line pt-2.5" data-testid="people-status">
      <Eyebrow>{t("people.statusTitle")}</Eyebrow>
      <ul className="m-0 p-0 list-none flex flex-col">
        {rows.map((r, i) => (
          <li key={`${r.name}${i}`} className="flex items-center gap-2.5 min-h-[44px]">
            <Avatars names={[r.name]} size={28} />
            <span className="flex-1 min-w-0 text-[15px] [overflow-wrap:anywhere]">{r.name}</span>
            <Pill tone={tone[r.status]}>{t(`people.status.${r.status}`)}</Pill>
            {r.status !== "member" && <a href={remind} className="min-h-[44px] inline-flex items-center px-1 text-[14px] font-semibold text-accent underline">{t("people.remind")}</a>}
          </li>
        ))}
      </ul>
      {simulated && fake && rows.some((r) => r.status !== "member") && (
        <Button variant="tonal" className="self-start" onClick={async () => { await fake.simulateInviteProgress(task.id); await refresh(); }}>{t("people.simulate")} <Sim /></Button>
      )}
    </div>
  );
}

function AddItem({ task, wish }: { task: Task; wish: boolean }) {
  const t = useT("privat");
  const { run } = usePrivat();
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [link, setLink] = useState("");
  const id = `add-${task.id}`;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    const r = await run((a) => a.addItem(task.id, wish ? { text, note: note || undefined, link: link || undefined } : { text }));
    if (r) { setText(""); setNote(""); setLink(""); }
  };
  const field = "flex-1 min-w-0 min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px] bg-paper text-ink placeholder:text-muted";
  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label htmlFor={id} className={SR}>{wish ? t("list.wishPlaceholder") : t("list.addLabel")}</label>
      <div className="flex gap-2">
        <input id={id} className={field} value={text} onChange={(e) => setText(e.target.value)} placeholder={wish ? t("list.wishPlaceholder") : t("list.addPlaceholder")} autoComplete="off" />
        <Button type="submit" className={BIG} variant="primary"><Ico name="plus" size={18} />{t("list.add")}</Button>
      </div>
      {wish && (
        <div className="flex flex-col sm:flex-row gap-2">
          <input aria-label={t("list.notePlaceholder")} className={field} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("list.notePlaceholder")} />
          <input aria-label={t("list.linkPlaceholder")} type="url" inputMode="url" className={field} value={link} onChange={(e) => setLink(e.target.value)} placeholder={t("list.linkPlaceholder")} />
        </div>
      )}
    </form>
  );
}

export function ListCard({ task }: { task: Task }) {
  const t = useT("privat");
  const { talk } = usePrivat();
  return (
    <div className={CARD}>
      <div className="flex items-center gap-2.5">
        <Tile name={isWish(task) ? "gift" : "list"} />
        <div className="flex-1 min-w-0">
          <h3 className="m-0 font-display font-bold text-[19px] [overflow-wrap:anywhere]">{task.title}</h3>
          <span className="text-[13px] text-muted">{task.usage_text}</span>
        </div>
        {task.is_example && <Ex />}
      </div>
      <ListBody task={task} />
      <button type="button" className={LINK} onClick={() => talk(task.id)}>{t("list.talk")}</button>
    </div>
  );
}

// ---------------------------------------------------------------- reminder

export function ReminderCard({ task }: { task: Task }) {
  const t = useT("privat");
  const f = useFmt();
  return (
    <div className={CARD}>
      <div className="flex items-center gap-2.5">
        <Tile name="bell" />
        <div className="flex-1 min-w-0">
          <h3 className="m-0 font-display font-bold text-[19px] [overflow-wrap:anywhere]">{task.title}</h3>
          <span className="text-[14px] text-ink-soft">{f.when(task.remind_at ?? task.due_at)}</span>
        </div>
      </div>
      <PushPrompt moment="reminder" />
      <span className="text-[13px] text-muted">{task.usage_text}</span>
    </div>
  );
}

export function MoveCard({ task, before, after }: { task: Task | undefined; before: string; after: string }) {
  const t = useT("privat");
  return (
    <div className={CARD}>
      <Eyebrow>{t("move.label")}</Eyebrow>
      {task && <h3 className="m-0 font-display font-bold text-[19px] [overflow-wrap:anywhere]">{task.title}</h3>}
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] gap-2 items-center">
        <div className="border-[1.5px] border-line rounded-xl p-2.5"><span className="eyebrow text-[11px]">{t("move.before")}</span><div className="text-[15px] line-through text-muted [overflow-wrap:anywhere]">{before}</div></div>
        <Ico name="arrow" size={22} stroke={2.4} />
        <div className="border-2 border-ink rounded-xl p-2.5"><span className="eyebrow text-[11px]">{t("move.after")}</span><div className="text-[15px] font-bold [overflow-wrap:anywhere]">{after}</div></div>
      </div>
      <p className="m-0 text-[13px] text-muted">{t("move.note")}</p>
    </div>
  );
}

// ---------------------------------------------------------------- phone verification

/** Mobile number + SMS code. Used inline before the first call and on Konto. */
export function PhoneVerify({ onDone, compact = false }: { onDone?: () => void; compact?: boolean }) {
  const t = useT("privat");
  const { api, refresh, simulated, balance } = usePrivat();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const field = "w-full min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px] bg-paper text-ink";
  const start = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null); setBusy(true);
    try { await api.phoneStart(phone); setSent(phone); } catch (x) { setErr((x as ApiError).message); } finally { setBusy(false); }
  };
  const verify = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null); setBusy(true);
    try { await api.phoneVerify(code); await refresh(); onDone?.(); } catch (x) { setErr((x as ApiError).message); } finally { setBusy(false); }
  };
  if (balance?.phone_verified && !sent) return null;
  return (
    <div className={`flex flex-col gap-2.5 ${compact ? "" : ""}`}>
      {!sent ? (
        <form onSubmit={start} className="flex flex-col gap-2">
          <label htmlFor="privat-phone" className="text-[14px] font-semibold">{t("phone.label")}</label>
          <div className="flex gap-2 flex-wrap">
            <input id="privat-phone" type="tel" inputMode="tel" autoComplete="tel" className={`${field} flex-1 min-w-[160px]`} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="12 34 56 78" required />
            <Button type="submit" variant="outline" disabled={busy}>{t("phone.send")}</Button>
          </div>
        </form>
      ) : (
        <form onSubmit={verify} className="flex flex-col gap-2">
          <p className="m-0 text-[14px] text-ink-soft" role="status">{t("phone.sent", { phone: sent })}</p>
          {simulated && <p className="m-0 text-[13px] flex items-center gap-2 flex-wrap"><Sim />{t("phone.fakeHint", { code: FAKE_SMS_CODE })}</p>}
          <label htmlFor="privat-code" className="text-[14px] font-semibold">{t("phone.code")}</label>
          <div className="flex gap-2 flex-wrap">
            <input id="privat-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" maxLength={6} className={`${field} flex-1 min-w-[140px] tracking-[0.3em]`} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} required />
            <Button type="submit" disabled={busy || code.length !== 6}>{t("phone.verify")}</Button>
          </div>
          <button type="button" className={LINK} onClick={() => { setSent(null); setCode(""); }}>{t("phone.resend")}</button>
        </form>
      )}
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- call

export function CallCard({ task }: { task: Task }) {
  const t = useT("privat");
  const raw = useRaw();
  const f = useFmt();
  const { simulated, mode, balance, run, api, refresh, openSheet, openTask, fake, addonOn, sendAbout } = usePrivat();
  const plan = usePlan();
  const c = task.call!;
  const [editing, setEditing] = useState(false);
  const [win, setWin] = useState(c.window);
  const [other, setOther] = useState("");
  const [share, setShare] = useState(c.share_phone);
  const [needPhone, setNeedPhone] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [isBusiness, setIsBusiness] = useState(false);
  const [number, setNumber] = useState("");
  useEffect(() => { setWin(c.window); }, [c.window]);
  const mobile = c.is_mobile ?? isDanishMobile(c.phone_e164);
  const noNumber = c.phone_e164 === null || (c.phone_e164 === undefined && !c.phone_display);
  const closed = c.open_now === false;
  const swap = (s: string) => (win && win !== c.window ? s.split(c.window).join(win) : s);
  const credits = balance?.credits ?? 0;
  // The plan's monthly quota pays first; credits («ekstra opkald») when it is used up or there is no plan.
  const viaPlan = plan.entitled && plan.callsLeft > 0;
  const approve = async (phoneJustVerified = false) => {
    setErr(null);
    if (!addonOn(ADDON.call)) { openSheet({ kind: "addon", addonKey: ADDON.call }); return; }
    if (!phoneJustVerified && balance && !balance.phone_verified) { setNeedPhone(true); return; }
    if (!viaPlan && credits < c.max_credits) { openSheet({ kind: "paywall", taskId: task.id }); return; }
    setBusy(true);
    try {
      await api.approveCall(task.id, { window: win, share_phone: share, ...(mobile ? { confirm_business: isBusiness } : {}), ...(closed ? { at_next_open: true } : {}) });
      setNeedPhone(false); await refresh();
    }
    catch (e) {
      const x = e as ClientApiError;
      if (x.code === CONFLICT.needsPhone) setNeedPhone(true);
      else if (x.code === CONFLICT.insufficientCredits) openSheet({ kind: "paywall", taskId: task.id });
      else if (x.code === CONFLICT.needsPlan) openSheet({ kind: "needsPlan", taskId: task.id });
      else if (x.code === CONFLICT.addonDisabled) openSheet({ kind: "addon", addonKey: ADDON.call });
      else if (x.code === CONFLICT.demoBusiness) setErr(t("call.demoBusiness"));
      // The card was stale (no number yet / just closed / mobile number): refresh so it shows the right step, and say why.
      else if (x.code === CONFLICT.needsBusinessPhone) { setErr(t("call.askNumber")); await refresh(); }
      else if (x.code === CONFLICT.businessClosed) { setErr(x.message || t("call.outsideHours")); await refresh(); }
      else if (x.code === CONFLICT.confirmBusiness) setErr(t("call.isBusinessHint"));
      else setErr(x.code === CONFLICT.outsideHours ? t("call.outsideHours") : x.message);
    } finally { setBusy(false); }
  };
  const res = c.result;
  // The backend's usage text («1 af 10 opkald i Plus · 2 min.» or «3 credits · …») wins; the credits line is the fallback.
  const usage = task.usage_text || t("call.callUsage", { n: c.max_credits, duration: f.duration(c.duration_seconds) });
  const noAnswerTitle = plan.entitled ? t("day2.noAnswerPlan") : t("call.noAnswerTitle", { n: c.max_credits });

  if (task.status === "declined" || res === "declined") {
    return <div className={BAD}><h3 className="m-0 font-display font-bold text-[18px]">{t("call.declinedTitle")}</h3><p className="m-0 text-[14px] text-ink-soft">{t("call.declinedText")}</p></div>;
  }
  if (task.status === "planned" && (c.status === "approved" || c.next_open_text)) {
    return (
      <div className="rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-3">
        <div className="flex gap-2 items-center flex-wrap"><Pill>{t("status.planned")}</Pill>{simulated && <Sim />}</div>
        <h3 className="m-0 font-display font-bold text-[20px] [overflow-wrap:anywhere]">{t("call.plannedTitle", { name: c.business_name, when: c.next_open_text ?? "" })}</h3>
        <p className="m-0 text-[14px] text-ink-soft">{task.usage_text || t("call.reserved", { n: c.max_credits })}</p>
        {simulated && fake && (
          <div className="flex gap-2 flex-wrap">
            <Button variant="outline" onClick={() => run((a) => (a as typeof fake).simulateOutcome(task.id, "answered"))}>{t("call.outcomeAnswered")}</Button>
            <Button variant="outline" onClick={() => run((a) => (a as typeof fake).simulateOutcome(task.id, "no_answer"))}>{t("call.outcomeNoAnswer")}</Button>
          </div>
        )}
        <PushPrompt moment="call" />
      </div>
    );
  }
  if (task.status === "in_progress") {
    return (
      <div className="rounded-[18px] border-2 border-ink bg-accent-soft p-4 flex flex-col gap-3">
        <div className="flex gap-2 items-center flex-wrap"><Pill>{t("status.in_progress")}</Pill>{simulated && <Sim label={t("call.simulatedCall")} />}</div>
        <h3 className="m-0 font-display font-bold text-[20px] [overflow-wrap:anywhere]">{t("call.calling", { name: c.business_name })}</h3>
        <p className="m-0 text-[14px] text-ink-soft">{task.usage_text || t("call.reserved", { n: c.max_credits })}</p>
        {simulated && fake ? (
          <>
            <Eyebrow className="mt-1">{t("call.chooseOutcome")}</Eyebrow>
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" onClick={() => run((a) => (a as typeof fake).simulateOutcome(task.id, "answered"))}>{t("call.outcomeAnswered")}</Button>
              <Button variant="outline" onClick={() => run((a) => (a as typeof fake).simulateOutcome(task.id, "no_answer"))}>{t("call.outcomeNoAnswer")}</Button>
            </div>
          </>
        ) : <p className="m-0 text-[14px] text-ink-soft">{t("call.realWait")}</p>}
        <PushPrompt moment="call" />
      </div>
    );
  }
  if (res === "answered" && task.status === "done") {
    return (
      <div className={OK}>
        <div className="flex gap-2 items-center flex-wrap"><span className="inline-flex items-center min-h-6 px-2.5 rounded-full border-[1.5px] border-success text-success bg-paper text-[12px] font-semibold">{t("call.confirmedBy")}</span>{simulated && <Sim />}</div>
        <h3 className="m-0 font-display font-extrabold text-[22px] [overflow-wrap:anywhere]">{t("call.isConfirmed", { text: c.confirmed_text ?? "" })}</h3>
        {c.business_reply && <p className="m-0 text-[15px] leading-normal"><b>{t("call.reply")}</b> «{c.business_reply}»</p>}
        <Kv rows={[[t("call.priceAt"), `${c.business_price_text ?? "–"} ${t("call.priceNote")}`], [t("call.assistantCall"), usage]]} />
        <button type="button" className={LINK} onClick={() => openTask(task.id)}>{t("call.seeTask")}</button>
      </div>
    );
  }
  if (res === "no_answer" && task.status === "awaiting_user") {
    return (
      <div className={BAD}>
        <div className="flex gap-2 items-center flex-wrap"><Pill tone="highlight">{t("status.awaiting_user")}</Pill>{simulated && <Sim />}</div>
        <h3 className="m-0 font-display font-bold text-[20px]">{noAnswerTitle}</h3>
        <p className="m-0 text-[15px] text-ink-soft">{t("call.noAnswerText")}</p>
        <div className="flex gap-2 flex-wrap">
          <Button className={BIG} onClick={() => run((a) => a.retryCall(task.id))}>{t("call.retry")}</Button>
          <Button variant="outline" onClick={() => run((a) => a.declineCall(task.id))}>{t("call.cancel")}</Button>
        </div>
      </div>
    );
  }
  if (task.status !== "awaiting_user" || res) return null;

  if (editing) {
    const wins = Array.from(new Set([c.window, ...(raw<string[]>("privat.call.windows") ?? [])]));
    return (
      <div className={PROPOSAL}>
        <Eyebrow>{t("call.editTitle")}</Eyebrow>
        <p className="m-0 text-[15px]">{t("call.editQ")}</p>
        <div className="flex gap-2 flex-wrap" role="group" aria-label={t("call.window")}>
          {wins.map((w) => (
            <button key={w} type="button" aria-pressed={win === w} onClick={() => setWin(w)} className={`${CHIP} ${win === w ? "!bg-ink !text-paper" : ""}`}>{w}</button>
          ))}
        </div>
        <label className="flex flex-col gap-1.5 text-[14px] font-semibold">{t("call.otherWindow")}
          <input className="min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px] font-normal" value={other} onChange={(e) => { setOther(e.target.value); if (e.target.value.trim()) setWin(e.target.value.trim()); }} />
        </label>
        <Button className={`${BIG} self-start`} onClick={() => setEditing(false)}>{t("call.saveEdit")}</Button>
      </div>
    );
  }

  return (
    <div className={PROPOSAL}>
      <Eyebrow>{t("call.proposal")}</Eyebrow>
      <h3 className="m-0 font-display font-bold text-[20px] [overflow-wrap:anywhere]">{t("call.ask", { name: c.business_name })}</h3>
      <Kv rows={[
        [t("call.recipient"), `${c.business_name}, ${c.address}`],
        [t("call.number"), noNumber ? <span key="n" className="text-muted">{t("call.noNumber")}</span> : <span key="n">{c.phone_display} {(mode !== "real" || c.source === "demo") && <Ex label={t("brand.exampleNumber")} />}</span>],
        [t("call.window"), win],
        [t("call.mayAsk"), swap(c.may_ask)],
        [t("call.mayAgree"), swap(c.may_agree)],
        [t("call.mayNot"), c.may_not],
      ]} />
      <div className="rounded-xl border-[1.5px] border-ink bg-panel p-3 flex flex-col gap-1.5">
        {viaPlan ? <span className="text-[15px]"><b>{t("day2.callQuota", { used: plan.callsUsed + 1, quota: plan.callsQuota, plan: plan.rightsName })}</b></span>
          : <span className="text-[15px]"><b>{t("call.cost", { n: c.max_credits })}</b> {t("call.costTime")}</span>}
        <span className="text-[14px] text-ink-soft">{t("call.refund")}</span>
        <span className="text-[14px] text-ink-soft">{t("call.price")}</span>
      </div>
      <label className="flex items-center gap-3 min-h-[44px] cursor-pointer">
        <button type="button" role="switch" aria-checked={share} onClick={() => setShare(!share)}
          className={`relative w-12 h-7 rounded-full border-2 border-ink shrink-0 transition-colors ${share ? "bg-accent" : "bg-paper"}`}>
          <span className={`absolute top-0.5 w-5 h-5 rounded-full border-2 border-ink bg-paper transition-all ${share ? "left-[22px]" : "left-0.5"}`} />
          <span className={SR}>{t("call.shareQ")}</span>
        </button>
        <span className="flex flex-col"><span className="text-[15px] font-semibold">{t("call.shareQ")}</span><span className="text-[13px] text-muted">{t("call.shareHint")}</span></span>
      </label>
      {closed && <p className="m-0 rounded-xl border-[1.5px] border-ink bg-highlight px-3 py-2 text-[14px] font-semibold">{t("call.closedNow", { when: c.next_open_text ?? "" })}</p>}
      {noNumber && (
        <form className="flex flex-col gap-1.5" onSubmit={async (e) => { e.preventDefault(); if (number.trim()) { await sendAbout(number.trim(), task.id); setNumber(""); } }}>
          <label htmlFor={`num-${task.id}`} className="text-[15px] font-semibold">{t("call.askNumber")}</label>
          <div className="flex gap-2">
            <input id={`num-${task.id}`} type="tel" inputMode="tel" className="flex-1 min-w-0 min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px]" value={number} onChange={(e) => setNumber(e.target.value)} placeholder="86 12 34 56" />
            <Button type="submit" variant="outline" className="border-2">{t("call.useNumber")}</Button>
          </div>
        </form>
      )}
      {mobile && !noNumber && (
        <label className="flex items-start gap-3 min-h-[44px] cursor-pointer rounded-xl border-[1.5px] border-ink p-3">
          <input type="checkbox" className="mt-0.5 w-5 h-5 accent-[var(--color-accent)]" checked={isBusiness} onChange={(e) => setIsBusiness(e.target.checked)} />
          <span className="flex flex-col"><span className="text-[15px] font-semibold">{t("call.isBusiness")}</span><span className="text-[13px] text-muted">{t("call.isBusinessHint")}</span></span>
        </label>
      )}
      {!viaPlan && credits < c.max_credits && <p className="m-0 text-[14px] text-danger font-semibold">{t("call.needCredits", { have: credits, need: c.max_credits })}</p>}
      {needPhone && (
        <div className="rounded-xl border-2 border-ink bg-paper p-3 flex flex-col gap-2">
          <p className="m-0 font-semibold">{t("call.phoneStep")}</p>
          <p className="m-0 text-[14px] text-ink-soft">{t("call.phoneStepText")}</p>
          <p className="m-0 text-[13px] text-muted">{t("call.phoneThenCall")}</p>
          <PhoneVerify onDone={() => { setNeedPhone(false); void approve(true); }} />
        </div>
      )}
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      <div className="flex gap-2 flex-wrap">
        <Button className={`${BIG} flex-[1_1_180px]`} onClick={() => approve()} disabled={busy || noNumber || (mobile && !isBusiness)}>{closed ? t("call.approveWhenOpen") : t("call.approve")}</Button>
        <Button variant="outline" onClick={() => setEditing(true)}>{t("call.edit")}</Button>
        <Button variant="outline" onClick={() => run((a) => a.declineCall(task.id))}>{t("call.decline")}</Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- draft, add-on, share proposal

export function DraftCard({ task }: { task: Task }) {
  const t = useT("privat");
  const { openSheet } = usePrivat();
  const p = usePlan();
  return (
    <div className={PROPOSAL}>
      <Eyebrow>{t("draft.label")}</Eyebrow>
      <h3 className="m-0 font-display font-bold text-[19px] [overflow-wrap:anywhere]">{task.title}</h3>
      {task.status === "draft" ? (
        <>
          <p className="m-0 text-[15px] text-ink-soft">{t(p.status === "none" ? "draft.textTrial" : "draft.text")}</p>
          <Button className={`${BIG} self-start`} onClick={() => openSheet({ kind: "paywall", taskId: task.id })}>{t("draft.choose")}</Button>
        </>
      ) : <p className="m-0 text-[14px] text-success font-semibold">{t("draft.active", { usage: task.usage_text })}</p>}
    </div>
  );
}

export function AddonCard({ addonKey, retryText }: { addonKey: string; retryText: string | null }) {
  const t = useT("privat");
  const { addons, run, send, go, openSheet, entitled } = usePrivat();
  const a = addons?.find((x) => x.key === addonKey);
  const name = a ? addonText(t, a, "name") : addonKey;
  const on = !!a?.enabled;
  const enable = () => (a && !addonIncluded(a, entitled) ? openSheet({ kind: "needsPlan", addonKey }) : run((x) => x.enableAddon(addonKey)));
  return (
    <div className={PROPOSAL}>
      <div className="flex items-center gap-2.5">
        <Tile name={a?.icon ?? "puzzle"} />
        <h3 className="m-0 flex-1 min-w-0 font-display font-bold text-[19px] [overflow-wrap:anywhere]">{on ? t("addonCard.enabled", { name }) : t("addonCard.notOn", { name })}</h3>
      </div>
      {!on && <p className="m-0 text-[15px] text-ink-soft">{t("addonCard.text")}</p>}
      <div className="flex gap-2 flex-wrap items-center">
        {!on && a?.status !== "coming_soon" && <Button className={BIG} onClick={enable}>{t("addons.enable")}</Button>}
        {on && retryText && <Button className={BIG} onClick={() => send(retryText)}>{t("addonCard.resend")}</Button>}
        <button type="button" className={LINK} onClick={() => go("store")}>{t("addonCard.seeAll")}</button>
      </div>
    </div>
  );
}

export function ShareProposalCard({ task, text, groupId }: { task: Task; text: string; groupId?: string | null }) {
  const t = useT("privat");
  const { openSheet } = usePrivat();
  return (
    <div className={PROPOSAL}>
      <Eyebrow>{t("shareCard.label")}</Eyebrow>
      <h3 className="m-0 font-display font-bold text-[19px] [overflow-wrap:anywhere]">{task.title}</h3>
      {text && <p className="m-0 text-[15px] text-ink-soft">{text}</p>}
      <p className="m-0 text-[13px] text-muted">{t("shareCard.nothingSent")}</p>
      <Button className={`${BIG} self-start`} onClick={() => openSheet({ kind: "share", taskId: task.id, groupId: groupId ?? undefined })}><Ico name="share" size={18} />{groupId ? t("shareCard.withGroup") : t("shareCard.make")}</Button>
    </div>
  );
}
