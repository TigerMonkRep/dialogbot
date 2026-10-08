import type { Metadata } from "next";
import { NOINDEX } from "@/lib/site";

/** Not for Google: the page is a client component, so title and noindex live here. */
export const metadata: Metadata = { title: "Log ind", description: "Log ind på dit Dialogbot-arbejdsrum.", robots: NOINDEX };

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
