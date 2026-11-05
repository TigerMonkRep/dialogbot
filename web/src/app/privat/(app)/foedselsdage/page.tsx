import type { Metadata } from "next";
import { getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("privat");
  return { title: t("meta.birthdays"), robots: { index: false } };
}

/** Fødselsdage app: rendered by the Privat shell (the store screen opens the app sheet). The reminder links here. */
export default function Page() { return null; }
