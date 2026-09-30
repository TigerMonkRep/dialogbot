import Link from "next/link";
import { backend } from "@/lib/api.server";
import { PayoutStatement } from "../statement";
import type { Statement } from "../../shared";

/** The ambassador's settlement note (afregningsbilag) for one payout. */
export default async function PayoutPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = await backend<Statement>(`/ambassador/me/payouts/${id}`);
  return (
    <div className="space-y-space-md">
      <Link href="/ambassador" className="font-label-md text-label-md text-primary underline">← Tilbage til min side</Link>
      <PayoutStatement s={s} />
    </div>
  );
}
