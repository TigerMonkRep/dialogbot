"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Button } from "@/components/ui";

export function RunChecks({ wsId }: { wsId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <span className="flex items-center gap-2 text-xs text-muted">
      {msg}
      <Button variant="secondary" disabled={pending} onClick={async () => {
        setPending(true);
        try { const r = await api<{ results: { check_key: string; status: string }[]; skipped: unknown[] }>(`/workspaces/${wsId}/setup/checks/run-all`, { method: "POST" }); setMsg(`${r.results.filter((x) => x.status === "passed").length}/${r.results.length} bestået, ${r.skipped.length} kræver integration`); router.refresh(); }
        catch (e) { setMsg((e as { message: string }).message); } finally { setPending(false); }
      }}>{pending ? "Kører…" : "Kør alle tjek"}</Button>
    </span>
  );
}

export function SkipButton({ wsId, taskKey, unskip }: { wsId: string; taskKey: string; unskip?: boolean }) {
  const router = useRouter();
  return <Button variant="ghost" className="border border-line" onClick={async () => { try { await api(`/workspaces/${wsId}/setup/tasks/${taskKey}/${unskip ? "unskip" : "skip"}`, { method: "POST" }); router.refresh(); } catch (e) { alert((e as { message: string }).message); } }}>{unskip ? "Fortryd spring" : "Spring over"}</Button>;
}
