import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getT } from "@/i18n/server";
import { PrivatStep } from "../privat-steps";

const TOTAL = 6;
const stepOf = (s: string) => (/^[1-9]$/.test(s) && Number(s) <= TOTAL ? Number(s) : null);

/** Step 1 is the indexable entry (/privat/start redirects here, see next.config.ts); the later steps are noindex. */
export async function generateMetadata({ params }: { params: Promise<{ step: string }> }): Promise<Metadata> {
  const n = stepOf((await params).step);
  const t = await getT("privat.funnel.meta");
  if (n === 1) return { title: t("title"), description: t("description"), alternates: { canonical: "/privat/start/1" } };
  return { title: t("stepTitle", { n: n ?? "" }), robots: { index: false, follow: false } };
}

export default async function Page({ params }: { params: Promise<{ step: string }> }) {
  const n = stepOf((await params).step);
  if (!n) notFound();
  return <PrivatStep step={n} />;
}
