import type { Metadata } from "next";
import { getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("privat");
  return { title: t("meta.app"), robots: { index: false } };
}

/** A household app (/privat/apps/<key>): rendered by the Privat shell (the store screen opens the app sheet). The
 *  app's reminders link here. */
export default function Page() { return null; }
