import { redirect } from "next/navigation";
import { setupStatus } from "@/lib/setup.server";
import { stepHref, stepsFor } from "@/lib/setup-steps";
import { requireWorkspace } from "@/lib/workspace.server";

/** Old address of «trin 3 – Test & tænd»: the channel steps and Betaling replace it. Goes to the first channel step that
 *  is not done – or Betaling (where it goes live) when the channels are set up. */
export default async function Old3() {
  const ws = await requireWorkspace();
  const st = await setupStatus(ws.id, ws.role);
  const channels = stepsFor(st.goals).filter((k) => k === "telefon" || k === "chat");
  const open = channels.find((k) => st.steps.find((s) => s.key === k)?.state !== "done");
  redirect(stepHref(open ?? "betaling"));
}
