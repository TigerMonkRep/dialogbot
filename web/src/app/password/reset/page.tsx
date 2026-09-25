"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button,  ErrorBox, Field, Input, useSubmit } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const router = useRouter();
  const [password, setPassword] = useState("");
  const { run, pending, error } = useSubmit(async () => {
    await api("/auth/password/reset", { method: "POST", body: JSON.stringify({ token, password }) });
    router.push("/login?reset=1");
  });
  if (!token) return <Alert>Linket mangler en token. Bestil et nyt link.</Alert>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-4">
      <ErrorBox error={error} />
      {error?.code === "token_expired" && <Link className="text-body-sm underline" href="/password/forgot">Bestil nyt link</Link>}
      <Field label="Ny adgangskode" hint="Mindst 10 tegn" error={fieldError(error, "password")}><Input type="password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" /></Field>
      <Button type="submit" disabled={pending} className="w-full">Gem ny adgangskode</Button>
    </form>
  );
}

export default function ResetPage() {
  return (
    <AuthFrame code="A04" title="Vælg ny adgangskode"><Suspense><ResetForm /></Suspense></AuthFrame>
  );
}
