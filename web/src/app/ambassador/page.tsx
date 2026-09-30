import { redirect } from "next/navigation";
import { backend } from "@/lib/api.server";
import type { Customer, Entry, Payout, Profile } from "./shared";
import { Portal } from "./portal";

/** The ambassador's own page: link and code, customers, ledger, payouts, payout details and marketing texts. */
export default async function AmbassadorPage() {
  const me = await backend<Profile | { enrolled: false }>("/ambassador/me");
  if (!me.enrolled) redirect("/ambassador/bliv");
  const [customers, ledger, payouts] = await Promise.all([
    backend<{ items: Customer[] }>("/ambassador/me/customers"),
    backend<{ items: Entry[] }>("/ambassador/me/ledger"),
    backend<{ items: Payout[] }>("/ambassador/me/payouts"),
  ]);
  return <Portal me={me} customers={customers.items} ledger={ledger.items} payouts={payouts.items} />;
}
