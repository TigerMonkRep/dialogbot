"use client";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client";
import { ErrorBox, useSubmit } from "@/components/ui";

export type TelephonyCode = "not_started" | "awaiting_info" | "provisioning" | "ready_for_test" | "test_failed" | "active" | "paused";

/** The big on/off switch. It only flips between "active" and "paused" (the two states the backend lets a
 *  customer toggle); every other state shows an honest label and sends the user to the telephony setup. */
export function PowerToggle({ wsId, code, canManage }: { wsId: string; code: TelephonyCode; canManage: boolean }) {
  const router = useRouter();
  const on = code === "active";
  const toggleable = canManage && (code === "active" || code === "paused");
  const { run, pending, error } = useSubmit(async () => {
    await api(`/workspaces/${wsId}/telephony/${on ? "pause" : "activate"}`, { method: "POST" });
    router.refresh();
  });
  return (
    <div className="flex flex-col items-end gap-2">
      <button type="button" role="switch" aria-checked={on} aria-label="Tænd eller sluk Dialogbot" disabled={!toggleable || pending} onClick={() => run()}
        title={toggleable ? undefined : code === "active" || code === "paused" ? "Kun ejere og administratorer kan tænde og slukke" : "Telefonen skal sættes op, før Dialogbot kan tændes"}
        className={`inline-flex items-center w-[84px] h-11 p-1 rounded-full transition-colors disabled:cursor-not-allowed ${on ? "bg-accent justify-end" : "bg-muted justify-start"} ${toggleable ? "" : "opacity-60"}`}>
        <span className="w-9 h-9 rounded-full bg-paper" />
      </button>
      <ErrorBox error={error} />
    </div>
  );
}
