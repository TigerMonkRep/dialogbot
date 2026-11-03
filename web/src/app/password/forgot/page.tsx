"use client";
import Link from "@/i18n/link";
import { useT } from "@/i18n/client";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button,  ErrorBox, Field, Input, useSubmit } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";

export default function ForgotPage() {
  const t = useT("auth");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const { run, pending, error } = useSubmit(async () => { await api("/auth/password/forgot", { method: "POST", body: JSON.stringify({ email }) }); setSent(true); });
  return (
    <AuthFrame icon="key" title={t("forgot.title")} subtitle={t("forgot.subtitle")}>
        {sent ? <Alert kind="ok">{t("forgot.sent")}</Alert> : (
          <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-3">
            <ErrorBox error={error} />
            <Field label={t("fields.email")}><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Button type="submit" icon="send" disabled={pending} className="w-full h-12 rounded-lg">{pending ? t("forgot.submitting") : t("forgot.submit")}</Button>
          </form>
        )}
        <p className="mt-3 text-body-sm text-ink-soft"><Link className="font-semibold text-ink underline" href="/login">{t("forgot.backToLogin")}</Link></p>
      </AuthFrame>
  );
}
