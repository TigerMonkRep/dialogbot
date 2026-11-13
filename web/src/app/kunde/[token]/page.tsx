import type { Metadata } from "next";
import { getT } from "@/i18n/server";
import { API_BASE_URL } from "@/lib/config";
import { CallbackManager, type CallbackView } from "./manage";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("widget");
  return { title: t("customer.callback.metaTitle"), robots: { index: false, follow: false } };
}

/** W09: the business's customer cancels the call back they asked for in the chat and sets their communication
 *  preference (do-not-call for campaigns). The secure token from the chat is the only key; no login. */
export default async function CustomerCallbackPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const r = await fetch(`${API_BASE_URL}/api/v1/public/customer/callback/${encodeURIComponent(token)}`, { cache: "no-store" });
  const state = r.ok ? "ok" : r.status === 410 ? "expired" : r.status === 404 ? "invalid" : "error";
  const view: CallbackView | null = r.ok ? await r.json() : null;
  return <CallbackManager token={token} state={state} initial={view} />;
}
