import type { Metadata } from "next";
import { GroupJoinPage } from "@/components/privat/public";
import { isLoggedIn } from "@/lib/api.server";
import { getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("privat");
  return { title: t("meta.groupJoin"), robots: { index: false } };
}

/** Group join link (dialogbot.app/g/K7Q2M9XA): people add themselves to someone's group – no contacts are imported. */
export default async function Page({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  return <GroupJoinPage code={code.toUpperCase()} loggedIn={await isLoggedIn()} />;
}
