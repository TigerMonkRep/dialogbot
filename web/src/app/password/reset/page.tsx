"use client";
import Link from "@/i18n/link";
import { useT } from "@/i18n/client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, useSubmit } from "@/components/ui";
import { AuthAside, AuthFrame } from "@/components/auth-frame";
import { PasswordField } from "@/components/password-field";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const router = useRouter();
  const t = useT("auth");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const { run, pending, error } = useSubmit(async () => {
    await api("/auth/password/reset", { method: "POST", body: JSON.stringify({ token, password }) });
    // The reset revokes every session server-side; drop the now-dead cookie too, so /login is not skipped.
    await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } });
    router.push("/login?reset=1");
  });
  if (!token) return <Alert>{t("reset.missingToken")}</Alert>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-3">
      <ErrorBox error={error} />
      {error?.code === "token_expired" && <Link className="text-body-sm underline" href="/password/forgot">{t("reset.orderNew")}</Link>}
      <PasswordField label={t("reset.newPassword")} value={password} onChange={setPassword} error={fieldError(error, "password")} />
      <PasswordField label={t("reset.confirmPassword")} value={confirm} onChange={setConfirm} withRules={false} placeholder={t("reset.confirmPlaceholder")} error={confirm && confirm !== password ? t("reset.mismatch") : undefined} />
      <Button type="submit" icon="check_circle" disabled={pending || !password || password !== confirm} className="w-full h-12 rounded-lg">{pending ? t("reset.submitting") : t("reset.submit")}</Button>
    </form>
  );
}

export default function ResetPage() {
  const t = useT("auth");
  return (
    <AuthFrame icon="key" title={t("reset.title")} subtitle={t("reset.subtitle")} aside={<AuthAside icon="history" title={t("reset.asideTitle")}>{t("reset.asideText")} <Link className="font-semibold text-ink underline" href="/password/forgot">{t("reset.asideLink")}</Link></AuthAside>}><Suspense><ResetForm /></Suspense></AuthFrame>
  );
}
