"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, useSubmit } from "@/components/ui";
import { AuthAside, AuthFrame } from "@/components/auth-frame";
import { PasswordField } from "@/components/password-field";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const { run, pending, error } = useSubmit(async () => {
    await api("/auth/password/reset", { method: "POST", body: JSON.stringify({ token, password }) });
    // The reset revokes every session server-side; drop the now-dead cookie too, so /login is not skipped.
    await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } });
    router.push("/login?reset=1");
  });
  if (!token) return <Alert>Linket mangler en token. Bestil et nyt link.</Alert>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-space-md">
      <ErrorBox error={error} />
      {error?.code === "token_expired" && <Link className="text-body-sm underline" href="/password/forgot">Bestil nyt link</Link>}
      <PasswordField label="Ny adgangskode" value={password} onChange={setPassword} error={fieldError(error, "password")} />
      <PasswordField label="Bekræft ny adgangskode" value={confirm} onChange={setConfirm} withRules={false} placeholder="Gentag din valgte kode" error={confirm && confirm !== password ? "Adgangskoderne er ikke ens" : undefined} />
      <Button type="submit" icon="check_circle" disabled={pending || !password || password !== confirm} className="w-full h-12 rounded-lg">{pending ? "Gemmer…" : "Gem ny adgangskode og fortsæt"}</Button>
    </form>
  );
}

export default function ResetPage() {
  return (
    <AuthFrame code="A04" icon="key" title="Opret ny adgangskode" subtitle="Vælg en stærk kode til din Dialogbot-konto." aside={<AuthAside icon="history" title="Har du problemer med linket?">Nulstillingslinks udløber efter kort tid og kan kun bruges én gang. <Link className="font-semibold text-primary underline" href="/password/forgot">Send nyt nulstillingslink</Link></AuthAside>}><Suspense><ResetForm /></Suspense></AuthFrame>
  );
}
