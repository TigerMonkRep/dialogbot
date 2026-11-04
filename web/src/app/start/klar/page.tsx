import type { Metadata } from "next";
import { getT } from "@/i18n/server";
import { Klar } from "./klar";

/** The reveal: «Hun ringer nu». Needs the session the code step just created; never indexed. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("site.funnel.erhverv.klar");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default function Page() { return <Klar />; }
