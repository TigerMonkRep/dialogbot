"use client";
import Link from "@/i18n/link";
import { useT } from "@/i18n/client";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/client";
import type { ApiError } from "@/lib/client";
import { Alert, Button,  ErrorBox } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { isPrivatContext, nextQuery, privatKind, privatNext } from "@/lib/privat-next";

/** Is someone logged in in THIS browser? (The mail may open another one.) Plain fetch: api() would send a 401 to /login. */
async function loggedIn(): Promise<boolean> {
  try { return (await fetch("/api/backend/auth/me", { headers: { "x-requested-with": "dialogbot" }, credentials: "same-origin" })).ok; }
  catch { return false; }
}

/** A03: pending, resend, verified and expired-link states. */
function Verify({ privat, next }: { privat: boolean; next: string | null }) {
  const token = useSearchParams().get("token");
  const t = useT("auth");
  const [state, setState] = useState<"idle" | "verifying" | "verified" | "error">(token ? "verifying" : "idle");
  const [error, setError] = useState<ApiError | null>(null);
  const [resent, setResent] = useState(false);
  const [after, setAfter] = useState<string | null>(null);
  const kind = privatKind(next);
  // ?for=privat&next=… (set by the API, so it also works when the mail opens another browser): back to where the
  // person was going – the plan's checkout (/privat/konto?plan=…), the shared list, the group – and without `next` on
  // to the plans, where the trial starts. Never into the business set-up (F-PK-04, F-JP-01, F-JP-05).
  useEffect(() => {
    if (privat) {
      if (!next) { setAfter("/privat/konto"); return; }
      setAfter(next);
      // logged out here (another browser): log in first, then on to the same place
      void loggedIn().then((ok) => { if (!ok) setAfter(`/login?next=${encodeURIComponent(next)}`); });
      return;
    }
    try { const v = localStorage.getItem("db_after_verify"); if (v?.startsWith("/ambassador") || v?.startsWith("/invite/")) setAfter(v); } catch { /* optional */ }
  }, [privat, next]);
  useEffect(() => {
    if (!token) return;
    api("/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) }).then(() => setState("verified")).catch((e) => { setError(e); setState("error"); });
  }, [token]);
  if (state === "verifying") return <Alert kind="info">{t("verify.verifying")}</Alert>;
  if (state === "verified") {
    const label = privat ? (kind === "trial" ? t("verify.continuePrivat") : kind === "list" ? t("verify.continueList") : t("verify.continueNext"))
      : after?.startsWith("/ambassador") ? t("verify.continueAmbassador") : after ? t("verify.continueNext") : t("verify.continueWorkspace");
    return (
      <div className="space-y-3">
        <Alert kind="ok">{t("verify.verified")}</Alert>
        <Link href={after ?? (privat ? "/privat/konto" : "/onboarding/workspace")} onClick={() => { try { localStorage.removeItem("db_after_verify"); } catch { /* optional */ } }} className="w-full h-12 rounded-lg bg-ink text-paper text-label-lg flex items-center justify-center gap-1 hover:bg-ink">{label}<span aria-hidden className="material-symbols-outlined text-[18px]">arrow_forward</span></Link>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {state === "error" && <ErrorBox error={error} />}
      {state === "error" && error?.code === "token_expired" && <Alert kind="info">{t("verify.expired")}</Alert>}
      {state === "idle" && <p className="text-body-md text-ink-soft">{t("verify.pending")}</p>}
      {resent ? <Alert kind="ok">{t("verify.resent")}</Alert> : (
        // A new link keeps the way back (`next`), and a Privat account gets the Privat mail (F-JP-03, F-JP-10).
        <Button variant="secondary" icon="forward_to_inbox" className="w-full h-12 rounded-lg" onClick={async () => { await api("/auth/verify-email/resend", { method: "POST", ...(next ? { body: JSON.stringify({ next }) } : {}) }); setResent(true); }}>{t("verify.resend")}</Button>
      )}
      <p className="text-body-sm text-ink-soft"><Link className="font-semibold text-ink underline" href={`/login${nextQuery(next, "?")}`}>{t("verify.backToLogin")}</Link></p>
    </div>
  );
}

/** In the Privat context (?for=privat or a Privat `next`) the page never shows the workspace/company words (F-JP-10). */
function VerifyScreen() {
  const t = useT("auth");
  const params = useSearchParams();
  const next = privatNext(params.get("next"));
  const privat = isPrivatContext(params);
  const kind = privatKind(next);
  const subtitle = !privat ? t("verify.subtitle") : kind === "trial" ? t("verify.subtitlePrivat")
    : kind === "list" ? t("verify.subtitlePrivatList") : t("verify.subtitlePrivatNeutral");
  return (
    <AuthFrame icon="mark_email_read" audience={privat ? "privat" : "erhverv"} title={t("verify.title")}
      subtitle={subtitle}><Verify privat={privat} next={next} /></AuthFrame>
  );
}

export default function VerifyPage() {
  return <Suspense><VerifyScreen /></Suspense>;
}
