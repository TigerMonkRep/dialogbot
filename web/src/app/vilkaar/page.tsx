import type { Metadata } from "next";
import { Blocks, COMPANY, LegalPage, type RichSection } from "@/components/legal-page";
import { getRaw, getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("legal.terms");
  return { title: t("meta.title"), description: t("meta.description") };
}

/** Terms of service for business customers (B2B). Prices match the billing code (app/modules/billing).
 *  Texts: messages/<locale>/legal.json → terms (Danish is the legally binding version). */
export default async function TermsPage() {
  const t = await getT("legal.terms");
  const raw = await getRaw();
  const sections = raw<RichSection[]>("legal.terms.sections");
  return (
    <LegalPage label={t("label")} title={t("title")} updated={t("updated")}
      intro={t("intro", { name: COMPANY.name, cvr: COMPANY.cvr, address: COMPANY.address })}
      sections={sections.map((s) => [s.title, <Blocks key={s.title} blocks={s.body} ulClassName="list-disc pl-5 flex flex-col gap-1" />])} />
  );
}
