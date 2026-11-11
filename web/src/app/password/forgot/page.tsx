"use client";
import Link from "@/i18n/link";
import { useT } from "@/i18n/client";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button,  ErrorBox, Field, Input, useSubmit } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { isPrivatContext, nextQuery, privatNext } from "@/lib/privat-next";

/** ?next=<Privat route> (from the Privat login): the orange frame, and `next` goes to the API so the reset mail is the
 *  Privat mail and its link returns there (F-JP-02). A Privat-only account gets the Privat mail without it too. */
function Forgot() {
  const t = useT("auth");
  const params = useSearchParams();
  const next = privatNext(params.get("next"));
  const privat = isPrivatContext(params);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const { run, pending, error } = useSubmit(async () => { await api("/auth/password/forgot", { method: "POST", body: JSON.stringify({ email, ...(next ? { next } : {}) }) }); setSent(true); });
  return (
    <AuthFrame icon="key" audience={privat ? "privat" : "erhverv"} title={t("forgot.title")} subtitle={t("forgot.subtitle")}>
        {sent ? <Alert kind="ok">{t("forgot.sent")}</Alert> : (
          <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-3">
            <ErrorBox error={error} />
            <Field label={t("fields.email")}><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Button type="submit" icon="send" disabled={pending} className="w-full h-12 rounded-lg">{pending ? t("forgot.submitting") : t("forgot.submit")}</Button>
          </form>
        )}
        <p className="mt-3 text-body-sm text-ink-soft"><Link className="font-semibold text-ink underline" href={`/login${nextQuery(next, "?")}`}>{t("forgot.backToLogin")}</Link></p>
      </AuthFrame>
  );
}

export default function ForgotPage() {
  return <Suspense><Forgot /></Suspense>;
}
