import type { Metadata } from "next";
import { getT } from "@/i18n/server";
import CATALOG from "@/lib/privat/addons-catalog.json";

export async function generateMetadata({ params }: { params: Promise<{ key: string }> }): Promise<Metadata> {
  const t = await getT("privat");
  const { key } = await params;
  const name = (CATALOG as { key: string; name: string }[]).find((a) => a.key === key)?.name;
  return { title: name ? `${name} · ${t("store.title")}` : t("store.metaTitle"), robots: { index: false } };
}

/** An app in Butikken (/privat/butik/<key>), before it is switched on – rendered by the Privat shell. */
export default function Page() { return null; }
