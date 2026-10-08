import type { Metadata } from "next";
import { NOINDEX } from "@/lib/site";

/** Not for Google: the page is a client component, so title and noindex live here. */
export const metadata: Metadata = { title: "Opret konto", description: "Opret en konto, og sæt din AI-receptionist op sammen med os.", robots: NOINDEX };

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
