import { AdminFrame, NotOperator, load } from "../shared";
import { DiscountCodes, type Code } from "./client";

/** Rabatkoder: the one place operators create something in the admin. A code is for Erhverv (a line on the monthly
 *  invoice), Privat (applied on Stripe Checkout) or both. */
export default async function DiscountCodesPage() {
  const data = await load<{ items: Code[]; stripe: boolean }>("/operator/admin/rabatkoder");
  if (!data) return <NotOperator />;
  return (
    <AdminFrame active="/app/operator/admin/rabatkoder" title="Rabatkoder" eyebrow="Admin"
      intro="Lav en kode til Erhverv, Privat eller begge. Erhverv: kunden skriver koden under Konto, og rabatten står som en linje på månedsfakturaen. Privat: koden bruges på betalingssiden (Stripe) – enten tastet dér eller via et link med ?kode=.">
      <DiscountCodes initial={data.items} stripe={data.stripe} />
    </AdminFrame>
  );
}
