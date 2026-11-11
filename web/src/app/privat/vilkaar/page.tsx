import type { Metadata } from "next";
import { Blocks, COMPANY, LegalPage, type RichSection } from "@/components/legal-page";
import { getRaw, getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("legal.privatTerms");
  return { title: t("meta.title"), description: t("meta.description") };
}

/** Terms of sale for Dialogbot Privat (consumers). Prices are {p…} tokens filled in per market from prices.json
 *  (lib/markets.ts), like the business terms on /vilkaar. Texts: messages/<locale>/legal.json → privatTerms (Danish
 *  is the binding version); `privatTerms.version` = app/modules/privat/market.py TERMS_VERSION (Stripe Checkout). */
export default async function PrivatTermsPage() {
  const t = await getT("legal.privatTerms");
  const raw = await getRaw();
  const sections = raw<RichSection[]>("legal.privatTerms.sections");
  return (
    <LegalPage audience="privat" label={t("label")} title={t("title")} updated={t("updated")}
      intro={t("intro", { name: COMPANY.name, cvr: COMPANY.cvr, address: COMPANY.address })}
      sections={sections.map((s) => [s.title, <Blocks key={s.title} blocks={s.body} ulClassName="list-disc pl-5 flex flex-col gap-1" />])} />
  );
}
