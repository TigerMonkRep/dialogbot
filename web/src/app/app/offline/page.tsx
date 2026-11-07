import type { Metadata } from "next";
import { getT } from "@/i18n/server";
import { OfflinePage } from "@/components/offline-page";

/** The offline page of the business app – precached by public/sw-app.js and shown for navigations under /app/
 *  without net. Outside the (admin) group on purpose: no backend, no shell, nothing that needs a connection. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("common");
  return { title: t("pwa.offlineTitle"), robots: { index: false, follow: false } };
}

export default function Page() { return <OfflinePage audience="erhverv" />; }
