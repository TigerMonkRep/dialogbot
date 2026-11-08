import type { Metadata } from "next";
import { getT } from "@/i18n/server";
import CATALOG from "@/lib/privat/addons-catalog.json";

export async function generateMetadata({ params }: { params: Promise<{ key: string }> }): Promise<Metadata> {
  const t = await getT("privat");
  const { key } = await params;
  const name = (CATALOG as { key: string; name: string }[]).find((a) => a.key === key)?.name;
  return { title: name ?? t("meta.app"), robots: { index: false } };
}

/** An app's own page (/privat/apps/<key>) – rendered by the Privat shell. The app's reminders link here. */
export default function Page() { return null; }
