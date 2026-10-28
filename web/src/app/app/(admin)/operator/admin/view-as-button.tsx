"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

/** "Se som": opens a read-only, one-hour session as this person and goes to their view of the app. */
export function ViewAsButton({ userId, workspaceId, label = "Se som" }: { userId: string; workspaceId?: string; label?: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <span className="inline-flex flex-col items-start">
      <button disabled={busy} className="px-3 py-1.5 rounded-full border-2 border-ink bg-highlight text-ink text-[13px] font-semibold hover:brightness-95 disabled:opacity-60"
        onClick={async () => {
          setBusy(true); setErr(null);
          const r = await fetch("/api/admin/view-as", { method: "POST", headers: { "x-requested-with": "dialogbot", "content-type": "application/json" }, body: JSON.stringify({ user_id: userId, workspace_id: workspaceId ?? null }) });
          const b = await r.json().catch(() => ({}));
          if (!r.ok) { setErr(b.message ?? "Kunne ikke åbne visningen"); setBusy(false); return; }
          router.push(b.next ?? "/app/overview"); router.refresh();
        }}>{busy ? "Åbner…" : label}</button>
      {err && <span role="alert" className="text-[12px] text-danger mt-1">{err}</span>}
    </span>
  );
}
