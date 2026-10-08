import type { Metadata } from "next";
import { AppShell } from "@/components/shell";
import { NOINDEX } from "@/lib/site";

export const metadata: Metadata = { robots: NOINDEX };
export default function Layout({ children }: { children: React.ReactNode }) { return <AppShell>{children}</AppShell>; }
