import type { Metadata } from "next";
import { getT } from "@/i18n/server";
import { OfflinePage } from "@/components/offline-page";

/** The offline page of Dialogbot Privat – precached by public/sw.js and shown for navigations under /privat/ without
 *  net. Outside the (app) group on purpose: no session, no Privat shell. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("common");
  return { title: t("pwa.offlineTitle"), robots: { index: false, follow: false } };
}

export default function Page() { return <OfflinePage audience="privat" />; }
