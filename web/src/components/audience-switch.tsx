import Link from "@/i18n/link";
import { getT } from "@/i18n/server";

export type Audience = "erhverv" | "privat";

/** The thin ink bar at the very top of both sites (design canvas "Dialogbot – Erhverv vs. Privat"): two segments,
 *  "Til virksomheder – Dialogbot Erhverv" (blue square, active = Klods-blå) and "Til dig derhjemme – Dialogbot Privat"
 *  (orange dot, active = orange). Links go to / and /privat. Server component – reads its texts from common.json
 *  ("audience.*"), so it can sit in SiteHeader as well as in the Privat landing and app. */
export async function AudienceSwitch({ current }: { current: Audience }) {
  const t = await getT("common");
  const seg = "inline-flex items-center gap-2 min-h-9 px-4 text-[13px] leading-none no-underline whitespace-nowrap";
  const business = current === "erhverv";
  return (
    <nav aria-label={t("audience.label")} className="flex flex-wrap items-center justify-center bg-ink text-white">
      {business ? (
        <span aria-current="page" className={`${seg} font-semibold`} style={{ background: "#2456F6" }}>
          <span aria-hidden="true" className="inline-block w-3.5 h-3.5 rounded-[3px] bg-white" />{t("audience.business")}
        </span>
      ) : (
        <Link href="/" className={`${seg} text-white opacity-90 hover:opacity-100 hover:bg-white/10`}>
          <span aria-hidden="true" className="inline-block w-3.5 h-3.5 rounded-[3px]" style={{ background: "#2456F6" }} />{t("audience.business")}
        </Link>
      )}
      {!business ? (
        <span aria-current="page" className={`${seg} font-semibold`} style={{ background: "#E0521A" }}>
          <span aria-hidden="true" className="inline-block w-3.5 h-3.5 rounded-full bg-white" />{t("audience.private")}
        </span>
      ) : (
        <Link href="/privat" className={`${seg} text-white opacity-90 hover:opacity-100 hover:bg-white/10`}>
          <span aria-hidden="true" className="inline-block w-3.5 h-3.5 rounded-full" style={{ background: "#E0521A" }} />{t("audience.private")}
        </Link>
      )}
    </nav>
  );
}
