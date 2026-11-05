import type { Metadata } from "next";
import { getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("privat");
  return { title: t("meta.bills"), robots: { index: false } };
}

/** Regninger app: rendered by the Privat shell (the store screen opens the app sheet). The reminder links here. */
export default function Page() { return null; }
