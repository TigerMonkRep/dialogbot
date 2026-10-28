import { redirect } from "next/navigation";
import { setupStatus } from "@/lib/setup.server";
import { requireWorkspace } from "@/lib/workspace.server";

/** The old «personlig plan» is gone: the three steps under /opsaetning replace it. This address stays for old links. */
export default async function SetupRedirect() {
  const ws = await requireWorkspace();
  const st = await setupStatus(ws.id, ws.role);
  redirect(st.done ? "/app" : `/opsaetning/${st.next}`);
}
