"use client"; // Error boundaries must be Client Components
import Link from "next/link";
import { useEffect } from "react";
import { useT } from "@/i18n/client";
import { PRIMARY, PrivatProblem, SECONDARY } from "@/components/privat/not-found-frame";

/** A render error in a Privat page: the orange Privat page in the user's language with «Prøv igen» and the way back,
 *  not Next's «Application error» (F-JP-11). */
export default function PrivatError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  const t = useT("privat");
  useEffect(() => { console.error(error); }, [error]);
  return (
    <PrivatProblem title={t("problem.errorTitle")} text={t("problem.errorText")}>
      <button type="button" onClick={() => retry()} className={PRIMARY}>{t("problem.retry")}</button>
      <Link href="/privat/dag" className={SECONDARY}>{t("problem.toDay")}</Link>
    </PrivatProblem>
  );
}
