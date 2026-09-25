"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/client";
import type { ApiError } from "@/lib/client";
import { Alert, Button, Card, ErrorBox } from "@/components/ui";

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
    <div className="space-y-4">
      <Alert kind="ok">Din e-mail er bekræftet.</Alert>
      <Link href="/onboarding/workspace"><Button>Fortsæt til arbejdsrum</Button></Link>
    </div>
  );
  return (
    <div className="space-y-4">
      {state === "error" && <ErrorBox error={error} />}
      {state === "error" && error?.code === "token_expired" && <Alert kind="info">Linket er udløbet. Bestil et nyt nedenfor.</Alert>}
      {state === "idle" && <p className="text-sm text-muted">Vi har sendt et bekræftelseslink til din e-mail. Åbn linket for at fortsætte. I udviklingsmiljøet findes mailen i den simulerede postkasse.</p>}
      {resent ? <Alert kind="ok">Et nyt link er sendt.</Alert> : (
        <Button variant="secondary" onClick={async () => { await api("/auth/verify-email/resend", { method: "POST" }); setResent(true); }}>Send nyt link</Button>
      )}
      <p className="text-sm text-muted"><Link className="underline" href="/login">Tilbage til login</Link></p>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <main className="mx-auto max-w-md px-4 py-12">
      <h1 className="mb-6 text-2xl font-extrabold text-primary-dark">Bekræft e-mail</h1>
      <Card><Suspense><Verify /></Suspense></Card>
    </main>
  );
}
