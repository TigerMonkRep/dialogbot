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
    <AuthFrame icon="key" title="Nulstil adgangskode" subtitle="Vi sender et link til din e-mail. Af hensyn til sikkerheden fortæller vi ikke, om adressen findes.">
        {sent ? <Alert kind="ok">Hvis adressen findes, har vi sendt et link til nulstilling. Linket gælder i en begrænset periode.</Alert> : (
          <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-space-md">
            <ErrorBox error={error} />
            <Field label="E-mail"><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Button type="submit" icon="send" disabled={pending} className="w-full h-12 rounded-lg">{pending ? "Sender…" : "Send nulstillingslink"}</Button>
          </form>
        )}
        <p className="mt-space-md font-body-sm text-body-sm text-on-surface-variant"><Link className="font-semibold text-primary underline" href="/login">Tilbage til login</Link></p>
      </AuthFrame>
  );
}
