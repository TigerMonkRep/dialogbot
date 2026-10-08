import type { Metadata } from "next";
import { AdminShell } from "@/components/shell";
import { NOINDEX } from "@/lib/site";

export const metadata: Metadata = { robots: NOINDEX };
export default function Layout({ children }: { children: React.ReactNode }) { return <AdminShell>{children}</AdminShell>; }
