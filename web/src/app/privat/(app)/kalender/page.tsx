import type { Metadata } from "next";
import { getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("privat");
  return { title: t("meta.calendar"), robots: { index: false } };
}

/** Kalender app: rendered by the Privat shell (the store screen opens the app sheet). Google/Microsoft send the user
 *  back here after giving access. */
export default function Page() { return null; }
