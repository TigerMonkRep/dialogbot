"use client";
import Link from "@/i18n/link";
import { useT } from "@/i18n/client";

/** «Sæt op selv»: the way out of the guide (every viewport) – to the ordinary settings pages, where everything can be set
 *  up by hand; what is done there counts in the guide's steps too. «I dag» then shows «Ikke færdig · Fortsæt» as the way
 *  back instead of sending the person to the steps. Remembered for 30 days. */
export function SetupLater({ className = "" }: { className?: string }) {
  const t = useT("setup.later");
  return (
    <Link href="/app/indstillinger" className={`underline underline-offset-2 ${className}`} onClick={() => { document.cookie = "db_setup_later=1; path=/; max-age=2592000; samesite=lax"; }}>{t("link")}</Link>
  );
}
