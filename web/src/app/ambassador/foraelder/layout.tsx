import type { Metadata } from "next";
import { NOINDEX } from "@/lib/site";

/** Not for Google: the page is a client component, so title and noindex live here. */
export const metadata: Metadata = { title: "Forældregodkendelse", description: "En forælder godkender, at deres barn må være Dialogbot-ambassadør.", robots: NOINDEX };

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
