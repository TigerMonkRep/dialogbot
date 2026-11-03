"use client";
import Link from "@/i18n/link";
import { useT } from "@/i18n/client";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/client";
import type { ApiError } from "@/lib/client";
import { Alert, Button,  ErrorBox } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";

/** A03: pending, resend, verified and expired-link states. */
function Verify() {
  const token = useSearchParams().get("token");
  const t = useT("auth");
  const [state, setState] = useState<"idle" | "verifying" | "verified" | "error">(token ? "verifying" : "idle");
  const [error, setError] = useState<ApiError | null>(null);
  const [resent, setResent] = useState(false);
  const [after, setAfter] = useState<string | null>(null);
  useEffect(() => { try { const v = localStorage.getItem("db_after_verify"); if (v?.startsWith("/ambassador")) setAfter(v); } catch { /* optional */ } }, []);
  useEffect(() => {
    if (!token) return;
    api("/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) }).then(() => setState("verified")).catch((e) => { setError(e); setState("error"); });
  }, [token]);
  if (state === "verifying") return <Alert kind="info">{t("verify.verifying")}</Alert>;
  if (state === "verified") return (
    <div className="space-y-3">
      <Alert kind="ok">{t("verify.verified")}</Alert>
      <Link href={after ?? "/onboarding/workspace"} onClick={() => { try { localStorage.removeItem("db_after_verify"); } catch { /* optional */ } }} className="w-full h-12 rounded-lg bg-ink text-paper text-label-lg flex items-center justify-center gap-1 hover:bg-ink">{after ? t("verify.continueAmbassador") : t("verify.continueWorkspace")}<span aria-hidden className="material-symbols-outlined text-[18px]">arrow_forward</span></Link>
    </div>
  );
  return (
    <div className="space-y-3">
      {state === "error" && <ErrorBox error={error} />}
      {state === "error" && error?.code === "token_expired" && <Alert kind="info">{t("verify.expired")}</Alert>}
      {state === "idle" && <p className="text-body-md text-ink-soft">{t("verify.pending")}</p>}
      {resent ? <Alert kind="ok">{t("verify.resent")}</Alert> : (
        <Button variant="secondary" icon="forward_to_inbox" className="w-full h-12 rounded-lg" onClick={async () => { await api("/auth/verify-email/resend", { method: "POST" }); setResent(true); }}>{t("verify.resend")}</Button>
      )}
      <p className="text-body-sm text-ink-soft"><Link className="font-semibold text-ink underline" href="/login">{t("verify.backToLogin")}</Link></p>
    </div>
  );
}

export default function VerifyPage() {
  const t = useT("auth");
  return (
    <AuthFrame icon="mark_email_read" title={t("verify.title")} subtitle={t("verify.subtitle")}><Suspense><Verify /></Suspense></AuthFrame>
  );
}
