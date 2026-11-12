import { redirect } from "next/navigation";
import { setupStatus } from "@/lib/setup.server";
import { stepHref } from "@/lib/setup-steps";
import { requireWorkspace } from "@/lib/workspace.server";

/** The old «personlig plan» is gone: the guide under /opsaetning replaces it. This address stays for old links. */
export default async function SetupRedirect() {
  const ws = await requireWorkspace();
  const st = await setupStatus(ws.id, ws.role);
  redirect(st.done ? "/app" : stepHref(st.next));
}
