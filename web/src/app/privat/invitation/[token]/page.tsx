import type { Metadata } from "next";
import { Suspense } from "react";
import { InvitationPage } from "@/components/privat/public";
import { isLoggedIn } from "@/lib/api.server";
import { getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("privat");
  return { title: t("meta.invite"), robots: { index: false } };
}

/** Public invite to a shared list: value first (title, who, how many), then a calm Dialogbot card. */
export default async function Page({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <Suspense><InvitationPage token={token} loggedIn={await isLoggedIn()} /></Suspense>;
}
