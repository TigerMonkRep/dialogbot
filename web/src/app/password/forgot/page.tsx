"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, Card, ErrorBox, Field, Input, useSubmit } from "@/components/ui";

export default function ForgotPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const { run, pending, error } = useSubmit(async () => { await api("/auth/password/forgot", { method: "POST", body: JSON.stringify({ email }) }); setSent(true); });
  return (
    <main className="mx-auto max-w-md px-4 py-12">
      <h1 className="mb-6 text-2xl font-extrabold text-primary-dark">Nulstil adgangskode</h1>
      <Card>
        {sent ? <Alert kind="ok">Hvis adressen findes, har vi sendt et link til nulstilling. Linket gælder i en begrænset periode.</Alert> : (
          <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-4">
            <ErrorBox error={error} />
            <Field label="E-mail"><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Button type="submit" disabled={pending} className="w-full">Send link</Button>
          </form>
        )}
        <p className="mt-4 text-sm text-muted"><Link className="underline" href="/login">Tilbage til login</Link></p>
      </Card>
    </main>
  );
}
