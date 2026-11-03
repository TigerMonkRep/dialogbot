import type { Metadata } from "next";
import { Blocks, LegalPage, type RichSection } from "@/components/legal-page";
import { getRaw, getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("legal.privacy");
  return { title: t("meta.title"), description: t("meta.description") };
}

/** Privacy policy. Keep it limited to what the product actually does (see docs and the code).
 *  Texts: messages/<locale>/legal.json → privacy (Danish is the legally binding version). */
export default async function PrivacyPage() {
  const t = await getT("legal.privacy");
  const raw = await getRaw();
  const sections = raw<RichSection[]>("legal.privacy.sections");
  return (
    <LegalPage label={t("label")} title={t("title")} updated={t("updated")} intro={t("intro")}
      sections={sections.map((s) => [s.title, <Blocks key={s.title} blocks={s.body} ulClassName="list-disc pl-5 flex flex-col gap-1" />])} />
  );
}
