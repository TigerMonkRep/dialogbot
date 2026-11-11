import Link from "next/link";
import { getT } from "@/i18n/server";
import { PRIMARY, PrivatProblem, SECONDARY } from "@/components/privat/not-found-frame";

/** An unknown /privat/… address (app/privat/[...rest]) or a notFound() in a Privat page: the orange Privat 404 in the
 *  visitor's language with the way back – not Next's English default (F-JP-11). */
export default async function PrivatNotFound() {
  const t = await getT("privat");
  return (
    <PrivatProblem title={t("problem.notFoundTitle")} text={t("problem.notFoundText")}>
      <Link href="/privat/dag" className={PRIMARY}>{t("problem.toDay")}</Link>
      <Link href="/privat" className={SECONDARY}>{t("problem.toHome")}</Link>
    </PrivatProblem>
  );
}
