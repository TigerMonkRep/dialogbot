"use client";
import { useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { ErrorBox } from "@/components/ui";
import { LanguageSwitcher } from "@/components/language-switcher";
import { useT } from "@/i18n/client";
import type { Locale } from "@/i18n/config";

/** «Sprog»: the app language. The switcher sets the cookie and re-renders; the choice is also saved on the user
 *  (PATCH /auth/me {locale}) so e-mails and other devices follow it. */
export function LanguageSection() {
  const t = useT("app");
  const [error, setError] = useState<ApiError | null>(null);
  const save = (locale: Locale) => {
    setError(null);
    api("/auth/me", { method: "PATCH", body: JSON.stringify({ locale }) }).catch((e) => setError(e as ApiError));
  };
  return (
    <div className="flex flex-col gap-2 px-5 py-5 rounded-2xl bg-paper border-2 border-ink">
      <span className="eyebrow">{t("account.language.title")}</span>
      <p className="text-[14px] text-ink-soft">{t("account.language.sub")}</p>
      <LanguageSwitcher className="self-start" onSaved={save} />
      <ErrorBox error={error} />
    </div>
  );
}
