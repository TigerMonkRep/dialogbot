import Link from "@/i18n/link";
import { getT } from "@/i18n/server";
import { backend } from "@/lib/api.server";
import { PayoutStatement } from "../statement";
import type { Statement } from "../../shared";

/** The ambassador's settlement note (afregningsbilag) for one payout. */
export default async function PayoutPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const t = await getT("auth");
  const s = await backend<Statement>(`/ambassador/me/payouts/${id}`);
  return (
    <div className="flex flex-col gap-4 items-start">
      <Link href="/ambassador" className="inline-flex items-center gap-1.5 min-h-[44px] text-[15px] font-semibold text-ink no-underline hover:text-accent"><span aria-hidden>←</span>{t("ambassador.statement.back")}</Link>
      <PayoutStatement s={s} />
    </div>
  );
}
