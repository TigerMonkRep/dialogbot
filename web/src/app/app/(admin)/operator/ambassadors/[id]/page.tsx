import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import type { Customer, Entry, Payout, Profile } from "@/app/ambassador/shared";
import { AmbassadorDetail } from "./client";

export type OpDetail = Profile & { motivation: string; rules_version: string; rules_accepted_at: string; customers: Customer[]; ledger: Entry[]; payouts: Payout[] };

export default async function OperatorAmbassadorPage({ params }: { params: Promise<{ id: string }> }) {
  await requireWorkspace();
  const { id } = await params;
  let a: OpDetail;
  let all: { items: { id: string; full_name: string; status: string }[] };
  try {
    [a, all] = await Promise.all([backend<OpDetail>(`/operator/ambassadors/${id}`), backend<{ items: { id: string; full_name: string; status: string }[] }>("/operator/ambassadors")]);
  } catch {
    return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Ambassadøren findes ikke, eller du er ikke operatør.</p>;
  }
  return (
    <section className="flex flex-col gap-space-lg">
      <Link href="/app/operator/ambassadors" className="font-label-md text-label-md text-primary underline">← Alle ambassadører</Link>
      <AmbassadorDetail a={a} others={all.items.filter((x) => x.id !== a.id && x.status === "active")} />
    </section>
  );
}
