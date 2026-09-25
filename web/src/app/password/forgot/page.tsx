"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button,  ErrorBox, Field, Input, useSubmit } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";

export default function ForgotPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const { run, pending, error } = useSubmit(async () => { await api("/auth/password/forgot", { method: "POST", body: JSON.stringify({ email }) }); setSent(true); });
  return (
    <AuthFrame code="A04" title="Nulstil adgangskode">
        {sent ? <Alert kind="ok">Hvis adressen findes, har vi sendt et link til nulstilling. Linket gælder i en begrænset periode.</Alert> : (
          <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-4">
            <ErrorBox error={error} />
            <Field label="E-mail"><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Button type="submit" disabled={pending} className="w-full">Send link</Button>
          </form>
        )}
        <p className="mt-4 text-body-sm text-on-surface-variant"><Link className="underline" href="/login">Tilbage til login</Link></p>
      </AuthFrame>
  );
}
