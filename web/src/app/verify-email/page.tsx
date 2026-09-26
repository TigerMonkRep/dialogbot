"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/client";
import type { ApiError } from "@/lib/client";
import { Alert, Button,  ErrorBox } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";

/** A03: pending, resend, verified and expired-link states. */
function Verify() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"idle" | "verifying" | "verified" | "error">(token ? "verifying" : "idle");
  const [error, setError] = useState<ApiError | null>(null);
  const [resent, setResent] = useState(false);
  useEffect(() => {
    if (!token) return;
    api("/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) }).then(() => setState("verified")).catch((e) => { setError(e); setState("error"); });
  }, [token]);
  if (state === "verifying") return <Alert kind="info">Bekræfter din e-mail…</Alert>;
  if (state === "verified") return (
    <div className="space-y-space-md">
      <Alert kind="ok">Din e-mail er bekræftet.</Alert>
      <Link href="/onboarding/workspace" className="w-full h-12 rounded-lg bg-primary text-on-primary font-label-lg text-label-lg flex items-center justify-center gap-space-xs hover:bg-primary-container">Fortsæt til arbejdsrum<span aria-hidden className="material-symbols-outlined text-[18px]">arrow_forward</span></Link>
    </div>
  );
  return (
    <div className="space-y-space-md">
      {state === "error" && <ErrorBox error={error} />}
      {state === "error" && error?.code === "token_expired" && <Alert kind="info">Linket er udløbet. Bestil et nyt nedenfor.</Alert>}
      {state === "idle" && <p className="font-body-md text-body-md text-on-surface-variant">Vi har sendt et bekræftelseslink til din e-mail. Åbn linket for at fortsætte. I udviklingsmiljøet findes mailen i den simulerede postkasse.</p>}
      {resent ? <Alert kind="ok">Et nyt link er sendt.</Alert> : (
        <Button variant="secondary" icon="forward_to_inbox" className="w-full h-12 rounded-lg" onClick={async () => { await api("/auth/verify-email/resend", { method: "POST" }); setResent(true); }}>Send nyt link</Button>
      )}
      <p className="font-body-sm text-body-sm text-on-surface-variant"><Link className="font-semibold text-primary underline" href="/login">Tilbage til login</Link></p>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <AuthFrame icon="mark_email_read" title="Bekræft din e-mail" subtitle="Bekræftelsen beskytter arbejdsrummet og er nødvendig, før du kan oprette virksomheder."><Suspense><Verify /></Suspense></AuthFrame>
  );
}
