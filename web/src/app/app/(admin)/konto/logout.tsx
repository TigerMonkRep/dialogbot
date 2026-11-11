"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useT } from "@/i18n/client";
import { clearSwPages } from "@/lib/sw-register";

export function LogoutButton() {
  const router = useRouter();
  const t = useT("app");
  const [busy, setBusy] = useState(false);
  return (
    <button type="button" disabled={busy} className="inline-flex items-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper text-danger text-[14px] font-semibold hover:bg-danger-soft disabled:opacity-60"
      onClick={async () => {
        setBusy(true);
        await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } });
        await clearSwPages();
        router.push("/login"); router.refresh();
      }}>{t("account.logout")}</button>
  );
}
