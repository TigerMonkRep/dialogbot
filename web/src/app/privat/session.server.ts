import "server-only";
import { backend, isLoggedIn } from "@/lib/api.server";
import type { Session } from "@/components/privat/store";

type Ws = { id: string; name: string; kind?: string };
type Me = { display_name: string; email: string };

/** Who is looking at Dialogbot Privat. Business workspaces (not kind "personal") give the «Virksomhed / Privat» switch. */
export async function privatSession(): Promise<Session> {
  if (!(await isLoggedIn())) return { loggedIn: false, name: null, email: null, businessWsId: null };
  try {
    const [me, ws] = await Promise.all([backend<Me>("/auth/me"), backend<Ws[]>("/workspaces").catch(() => [] as Ws[])]);
    const business = ws.find((w) => w.kind !== "personal");
    return { loggedIn: true, name: me.display_name || null, email: me.email, businessWsId: business?.id ?? null };
  } catch {
    return { loggedIn: true, name: null, email: null, businessWsId: null };
  }
}
