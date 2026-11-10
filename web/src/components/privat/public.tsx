"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, LogoMark } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import { isShortCode, isUnavailable, realPrivat, type GroupInvitePreview, type InvitePreview, type PrivatApi } from "@/lib/privat/api";
import { createFakePrivat } from "@/lib/privat/fake";
import { BIG, Sim } from "./bits";
import { Ico, Tile } from "./icons";
import { FAKE_KEY, FORCE_FAKE } from "./store";

const FAKE_LOGIN_KEY = "dialogbot-privat-fake-login";

/** The calm Dialogbot card under the value on invite pages (the invite is the ad – no pop-ups, no tracking). */
export function BrandCard({ name, refToken }: { name: string; refToken?: string }) {
  const t = useT("privat");
  return (
    <aside className="rounded-[18px] border-2 border-ink bg-panel p-4 flex flex-col gap-2.5" aria-label="Dialogbot">
      <div className="flex items-center gap-2.5"><LogoMark size={32} /><span className="font-display font-extrabold text-[19px]">Dialogbot</span></div>
      <p className="m-0 text-[15px] leading-normal"><b>{t("invitation.brandTitle", { name })}</b> {t("invitation.brandText")}</p>
      <p className="m-0 text-[15px] font-semibold">{t("invitation.brandOffer")}</p>
      <Link href={`/privat${refToken ? `?ref=${encodeURIComponent(refToken)}` : ""}`} className="inline-flex items-center justify-center self-start min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper font-semibold text-[15px] hover:bg-paper/70">{t("invitation.brandCta")}</Link>
    </aside>
  );
}

function PublicFrame({ children }: { children: React.ReactNode }) {
  const t = useT("privat");
  return (
    <div className="min-h-dvh bg-paper text-ink flex flex-col app-type">
      <header className="flex items-center gap-2.5 px-4 py-3 min-h-16 border-b-2 border-ink">
        <Link href="/privat" className="flex items-center gap-2.5 min-h-[44px]"><LogoMark size={32} /><span className="font-display font-extrabold text-[20px]">Dialogbot</span>
          <span className="text-[13px] font-semibold text-muted border-[1.5px] border-line rounded-full px-2 py-0.5">{t("brand.privat")}</span></Link>
        {FORCE_FAKE && <span className="ml-auto"><Sim /></span>}
      </header>
      <main className="flex-1 w-full max-w-[560px] mx-auto px-4 py-6 flex flex-col gap-5">{children}</main>
    </div>
  );
}

/** Real API for logged-in or anonymous visitors; the in-browser simulation when the API is missing or in fake mode. */
function usePublicApi(): { api: PrivatApi; fallback: () => PrivatApi; simulated: boolean } {
  const fake = useMemo(() => (typeof window === "undefined" ? null : createFakePrivat(FAKE_KEY)), []);
  const [useFake, setUseFake] = useState(FORCE_FAKE);
  return {
    api: useFake && fake ? fake : realPrivat,
    fallback: () => { setUseFake(true); return fake ?? realPrivat; },
    simulated: useFake,
  };
}

export function InvitationPage({ token, loggedIn }: { token: string; loggedIn: boolean }) {
  const t = useT("privat");
  const router = useRouter();
  const params = useSearchParams();
  const { api, fallback, simulated } = usePublicApi();
  const [p, setP] = useState<InvitePreview | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "gone">("loading");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    (async () => {
      const read = (a: PrivatApi) => (isShortCode(token) ? a.inviteByCode(token) : a.invite(token));
      try { const r = await read(api); if (alive) { setP(r); setState("ok"); } }
      catch (e) {
        if (!simulated && isUnavailable(e)) {
          try { const r = await read(fallback()); if (alive) { setP(r); setState("ok"); } return; } catch { /* fall through */ }
        }
        if (alive) setState("gone");
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  const canAccept = loggedIn || simulated;
  const accept = async () => {
    setBusy(true); setErr(null);
    try {
      if (simulated) { try { sessionStorage.setItem(FAKE_LOGIN_KEY, "1"); } catch { /* ignore */ } }
      const task = await (isShortCode(token) ? api.acceptInviteByCode(token) : api.acceptInvite(token));
      // Familie (resource_type household): the plan comes along, no task to open – land on Konto → Husstand.
      router.push(p?.resource_type === "household" ? "/privat/konto" : `/privat/opgaver/${encodeURIComponent(task.id)}?velkommen=1`);
    } catch (e) { setErr((e as ApiError).message); setBusy(false); }
  };
  useEffect(() => { if (state === "ok" && params.get("accept") === "1" && canAccept) void accept(); /* after login */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);
  const next = encodeURIComponent(`/privat/invitation/${token}?accept=1`);
  if (state === "loading") return <PublicFrame><p role="status" className="text-muted">{t("common.loading")}</p></PublicFrame>;
  if (state === "gone" || !p) return (
    <PublicFrame>
      <h1 className="m-0 font-display font-extrabold text-[28px]">{t("invitation.notFound")}</h1>
      <p className="m-0 text-[15px] text-ink-soft">{t("invitation.notFoundText")}</p>
      <BrandCard name={t("invitation.someone")} />
    </PublicFrame>
  );
  const name = p.inviter_first_name ?? p.owner_first_name;
  const wish = p.share_mode === "wishlist" || p.list_type === "wishlist";
  if (p.resource_type === "household") return (
    <PublicFrame>
      <section className="rounded-[18px] border-2 border-ink bg-paper p-5 shadow-block flex flex-col gap-3" aria-labelledby="inv-title" data-testid="household-invite">
        <div className="flex items-center gap-3"><Tile name="users" size={48} /><p className="eyebrow m-0">{t("familyHousehold.title")}</p></div>
        <h1 id="inv-title" className="m-0 font-display font-extrabold text-[30px] leading-[1.1] tracking-[-0.5px] [overflow-wrap:anywhere]">{t("familyHousehold.inviteTitle", { name })}</h1>
        <p className="m-0 text-[15px] text-ink-soft">{t("familyHousehold.inviteText", { name })}</p>
        {canAccept
          ? <Button className={BIG} onClick={accept} disabled={busy}>{busy ? t("invitation.opening") : t("familyHousehold.join")}</Button>
          : <>
            <Link href={`/signup?next=${next}`} className={`inline-flex items-center justify-center rounded-xl ${BIG} bg-accent text-white font-semibold hover:bg-accent-deep`}>{t("familyHousehold.join")}</Link>
            <Link href={`/login?next=${next}`} className="inline-flex items-center justify-center min-h-[44px] rounded-xl border-2 border-ink font-semibold text-[15px] hover:bg-panel">{t("invitation.login")}</Link>
          </>}
        {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      </section>
    </PublicFrame>
  );
  return (
    <PublicFrame>
      <section className="rounded-[18px] border-2 border-ink bg-paper p-5 shadow-block flex flex-col gap-3" aria-labelledby="inv-title">
        <p className="eyebrow m-0">{t("invitation.eyebrow")}</p>
        <div className="flex items-center gap-3"><Tile name={wish ? "gift" : "list"} size={48} />
          <p className="m-0 text-[15px] text-ink-soft">{wish ? t("invitation.wishlistBy", { name }) : t("invitation.listBy", { name })}</p></div>
        <h1 id="inv-title" className="m-0 font-display font-extrabold text-[30px] leading-[1.1] tracking-[-0.5px] [overflow-wrap:anywhere]">{p.title}</h1>
        <p className="m-0 text-[15px] font-semibold">{wish ? t("invitation.itemsWish", { n: p.item_count }) : t("invitation.itemsList", { n: p.item_count })}</p>
        {wish && <p className="m-0 text-[13px] text-muted">{t("invitation.wishPrivacy", { name })}</p>}
        {canAccept ? (
          <Button className={BIG} onClick={accept} disabled={busy}>{busy ? t("invitation.opening") : t("invitation.open")}</Button>
        ) : (
          <>
            <p className="m-0 text-[14px] text-ink-soft">{t("invitation.loginFirst")}</p>
            <Link href={`/signup?next=${next}`} className={`inline-flex items-center justify-center rounded-xl ${BIG} bg-accent text-white font-semibold hover:bg-accent-deep`}>{t("invitation.open")}</Link>
            <Link href={`/login?next=${next}`} className="inline-flex items-center justify-center min-h-[44px] rounded-xl border-2 border-ink font-semibold text-[15px] hover:bg-panel">{t("invitation.login")}</Link>
          </>
        )}
        {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      </section>
      <BrandCard name={name} refToken={token} />
    </PublicFrame>
  );
}

export function GroupJoinPage({ code, loggedIn }: { code: string; loggedIn: boolean }) {
  const t = useT("privat");
  const { api, fallback, simulated } = usePublicApi();
  const [p, setP] = useState<GroupInvitePreview | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "gone" | "joined">("loading");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ownApi, setOwnApi] = useState<PrivatApi | null>(null);
  const [smsCode, setSmsCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  useEffect(() => {
    let alive = true;
    (async () => {
      try { const r = await api.groupInvite(code); if (alive) { setP(r); setState("ok"); } }
      catch (e) {
        if (!simulated && isUnavailable(e)) {
          try { const f = fallback(); const r = await f.groupInvite(code); if (alive) { setOwnApi(f); setP(r); setState("ok"); } return; } catch { /* fall through */ }
        }
        if (alive) setState("gone");
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);
  const join = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null); setBusy(true);
    try {
      const r = await (ownApi ?? api).joinGroup(code, { name: name.trim(), ...(phone.trim() ? { phone: phone.trim() } : {}), ...(codeSent ? { code: smsCode.trim() } : {}) });
      // Without login, a phone number is confirmed with an SMS code first (the backend answers code_sent).
      if (r.code_sent && !r.joined) setCodeSent(true); else setState("joined");
    }
    catch (x) { setErr((x as ApiError).message); } finally { setBusy(false); }
  };
  const field = "w-full min-h-[52px] rounded-[14px] border-2 border-ink px-3.5 text-[16px] bg-paper";
  if (state === "loading") return <PublicFrame><p role="status" className="text-muted">{t("common.loading")}</p></PublicFrame>;
  if (state === "gone" || !p) return <PublicFrame><h1 className="m-0 font-display font-extrabold text-[28px]">{t("invitation.notFound")}</h1><p className="m-0 text-[15px] text-ink-soft">{t("invitation.notFoundText")}</p><BrandCard name={t("invitation.someone")} /></PublicFrame>;
  return (
    <PublicFrame>
      <section className="rounded-[18px] border-2 border-ink bg-paper p-5 shadow-block flex flex-col gap-3">
        <div className="flex items-center gap-3"><Tile name="users" size={48} /><p className="eyebrow m-0">{t("groupJoin.eyebrow", { n: p.member_count })}</p></div>
        <h1 className="m-0 font-display font-extrabold text-[28px] leading-[1.1] tracking-[-0.5px] [overflow-wrap:anywhere]">{t("groupJoin.title", { name: p.owner_first_name, group: p.group_name })}</h1>
        {state === "joined" ? (
          <div role="status" className="rounded-[18px] border-2 border-success bg-success-soft p-4 flex items-center gap-2.5">
            <span className="text-success"><Ico name="check" size={24} stroke={2.6} /></span>
            <span className="text-[17px] font-semibold">{t("groupJoin.joined", { group: p.group_name })}</span>
          </div>
        ) : (
          <form onSubmit={join} className="flex flex-col gap-2.5">
            <label htmlFor="join-name" className="text-[15px] font-semibold">{t("groupJoin.name")}</label>
            <input id="join-name" className={field} value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" required maxLength={40} />
            <label htmlFor="join-phone" className="text-[15px] font-semibold">{t("groupJoin.phone")} <span className="font-normal text-muted">{t("groupJoin.optional")}</span></label>
            <input id="join-phone" type="tel" inputMode="tel" autoComplete="tel" className={field} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="12 34 56 78" />
            <p className="m-0 text-[12px] text-muted">{t("groupJoin.phoneHint", { name: p.owner_first_name })}</p>
            {codeSent && (
              <>
                <p role="status" className="m-0 text-[14px] text-ink-soft">{t("phone.sent", { phone })}</p>
                <label htmlFor="join-code" className="text-[15px] font-semibold">{t("phone.code")}</label>
                <input id="join-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} className={`${field} tracking-[0.3em]`} value={smsCode} onChange={(e) => setSmsCode(e.target.value.replace(/\D/g, ""))} required />
              </>
            )}
            <Button type="submit" className={BIG} disabled={busy || !name.trim()}>{t("groupJoin.submit")}</Button>
            {!loggedIn && <Link href={`/login?next=${encodeURIComponent(`/g/${code}`)}`} className="inline-flex items-center justify-center min-h-[44px] rounded-xl border-2 border-ink font-semibold text-[15px] hover:bg-panel">{t("invitation.login")}</Link>}
            {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
          </form>
        )}
        <p className="m-0 text-[12px] text-muted">{t("groupJoin.privacy", { name: p.owner_first_name })}</p>
      </section>
      <BrandCard name={p.owner_first_name} />
    </PublicFrame>
  );
}
