import type { Metadata } from "next";
import Link from "next/link";
import { LogoMark } from "@/components/ui";
import { Ico } from "@/components/privat/icons";
import { getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("privat");
  return { title: t("meta.landingTitle"), description: t("meta.landingDescription") };
}

/** Public landing for Dialogbot Privat. Not a localized marketing page: the language follows the cookie, like the app. */
export default async function PrivatLanding() {
  const t = await getT("privat");
  return (
    <div className="min-h-dvh flex flex-col bg-panel text-ink">
      <header className="flex items-center gap-2.5 px-4 sm:px-6 py-3 min-h-16 border-b-2 border-ink bg-paper">
        <Link href="/privat" className="flex items-center gap-2.5 min-h-[44px]" aria-label="Dialogbot Privat">
          <LogoMark size={36} />
          <span className="font-display font-extrabold text-[22px] tracking-[-0.3px]">Dialogbot</span>
          <span className="text-[13px] font-semibold text-muted border-[1.5px] border-line rounded-full px-2 py-0.5">{t("brand.privat")}</span>
        </Link>
        <span className="flex-1" />
        <Link href={`/login?next=${encodeURIComponent("/privat/dag")}`} className="inline-flex items-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper font-semibold text-[15px] hover:bg-panel">{t("landing.login")}</Link>
      </header>
      <main className="flex-1 w-full max-w-[1248px] mx-auto px-5 py-7 lg:px-12 lg:py-14 grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-16 items-center">
        <div className="flex flex-col gap-4">
          <p className="eyebrow m-0 !text-accent">Dialogbot {t("brand.privat")}</p>
          <h1 className="m-0 font-display font-extrabold text-[40px] leading-[1.05] tracking-[-1px] lg:text-[68px] lg:leading-[1.02] lg:tracking-[-1.5px]">{t("landing.title")}</h1>
          <p className="m-0 text-[18px] leading-normal text-ink-soft">{t("landing.lead")}</p>
          <div className="flex flex-col gap-2.5 mt-2">
            <Link href="/privat/dag" className="inline-flex items-center justify-center w-full max-w-[360px] min-h-[52px] px-5 rounded-xl border-2 border-ink bg-accent text-white text-[16px] font-semibold hover:bg-accent-deep">{t("landing.cta")}</Link>
            <p className="m-0 text-[13px] text-muted">{t("landing.note")}</p>
          </div>
        </div>
        <div className="rounded-[18px] border-2 border-ink bg-paper p-4 lg:p-7 shadow-block flex flex-col gap-2.5">
          <p className="eyebrow m-0">{t("landing.exampleLabel")}</p>
          <div className="self-end max-w-[85%] bg-ink text-paper rounded-[16px_16px_4px_16px] px-3.5 py-2.5 text-[15px] leading-[1.4]">{t("landing.exampleAsk")}</div>
          <div className="rounded-[18px] border-2 border-dashed border-ink px-3.5 py-3 flex flex-col gap-1.5">
            <span className="eyebrow text-[11px]">{t("landing.proposalLabel")}</span>
            <span className="text-[15px] font-semibold">{t("landing.proposalTitle")}</span>
            <span className="text-[13px] text-muted">{t("landing.proposalText")}</span>
          </div>
          <div className="rounded-[18px] border-2 border-success bg-success-soft px-3.5 py-3 flex gap-2.5 items-center">
            <span className="text-success"><Ico name="check" size={22} stroke={2.4} /></span>
            <span className="text-[15px] font-semibold">{t("landing.confirmed")}</span>
          </div>
        </div>
      </main>
    </div>
  );
}
