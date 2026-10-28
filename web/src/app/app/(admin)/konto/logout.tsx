"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

export function LogoutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <button type="button" disabled={busy} className="inline-flex items-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper text-danger text-[14px] font-semibold hover:bg-danger-soft disabled:opacity-60"
      onClick={async () => {
        setBusy(true);
        await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } });
        router.push("/login"); router.refresh();
      }}>Log ud</button>
  );
}
