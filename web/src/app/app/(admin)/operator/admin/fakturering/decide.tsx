"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { ErrorBox, useSubmit } from "@/components/ui";

/** Approve or reject one complaint about a call (operator). */
export function DecideDispute({ id }: { id: string }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const decide = useSubmit(async (decision: "approve" | "reject") => {
    await api(`/operator/admin/disputes/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, note }) });
    router.refresh();
  });
  return (
    <div className="flex flex-col gap-2">
      <label className="sr-only" htmlFor={`note-${id}`}>Note til afgørelsen</label>
      <input id={`note-${id}`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (valgfri)" className="min-h-[44px] px-3 rounded-xl bg-paper border-2 border-ink" />
      <div className="flex flex-wrap gap-2">
        <button type="button" className="min-h-[44px] px-4 rounded-xl bg-ink text-paper font-semibold disabled:opacity-50" disabled={decide.pending} onClick={() => decide.run("approve")}>Godkend</button>
        <button type="button" className="min-h-[44px] px-4 rounded-xl border-2 border-ink font-semibold disabled:opacity-50" disabled={decide.pending} onClick={() => decide.run("reject")}>Afvis</button>
      </div>
      <ErrorBox error={decide.error} />
    </div>
  );
}
