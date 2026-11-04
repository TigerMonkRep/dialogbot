import type { Metadata } from "next";
import { getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("privat");
  return { title: t("meta.chat"), robots: { index: false } };
}

/** Rendered by the Privat shell in the layout (it reads the path). */
export default function Page() { return null; }
