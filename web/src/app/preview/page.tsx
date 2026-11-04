import type { Metadata } from "next";
import Link from "@/i18n/link";
import { getT } from "@/i18n/server";
import { redirect } from "next/navigation";
import { COMPANY } from "@/components/legal-page";
import { LogoMark } from "@/components/site-chrome";
import { gateEnabled } from "@/lib/preview-gate";
import { safeNext } from "@/lib/safe-next";
import { UnlockForm, WaitlistForm } from "./forms";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("site");
  return { title: t("preview.meta.title"), description: t("preview.meta.description") };
}

/** P00 — the invitation-code gate in the Byggevejledning design: one centred 2 px ink card with the logo, the
 *  yellow "0" step square, the code field and the blue button; the waitlist below it.
 *  Honest: no invented metrics, no demo code on the page, no audio sample that does not exist.
 *  No link to "/" on this page: a prefetch of "/" without the cookie would cache the redirect back here. */
export default async function PreviewPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  const target = safeNext(next, "/");
  // Gate switched off: the real landing page is public, so old /preview links go straight there.
  if (!gateEnabled()) redirect(target);
  const t = await getT("site");
  return (
    <div className="min-h-dvh bg-panel text-ink flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-white">{t("preview.skip")}</a>
      <main id="main" className="flex-1 w-full max-w-[560px] mx-auto px-4 sm:px-6 py-10 md:py-16 flex flex-col gap-6">
        <section aria-labelledby="laas-op" className="rounded-[20px] bg-white border-2 border-ink p-6 md:p-8 flex flex-col gap-6 shadow-block">
          <div className="flex items-center justify-between gap-4">
            <span className="inline-flex items-center gap-2.5 text-ink"><LogoMark size={36} /><span className="font-display font-extrabold tracking-[-0.3px] text-[22px]">Dialogbot</span></span>
            <span className="inline-flex items-center min-h-6 px-2.5 rounded-full bg-highlight text-ink text-[11px] font-semibold uppercase tracking-[0.12em]">{t("preview.badge")}</span>
          </div>
          <h1 id="laas-op" className="m-0 font-display font-extrabold text-[clamp(24px,3vw,30px)] leading-[1.1] tracking-[-0.5px]">{t("preview.title")}</h1>
          <p className="m-0 text-[15px] leading-normal text-ink-soft">{t("preview.lead")}</p>
          <UnlockForm next={target} />
          <p className="m-0 text-[13px] leading-normal text-muted">{t("preview.codesBefore")}<Link href="/login" className="text-accent font-semibold underline underline-offset-4">{t("preview.codesLink")}</Link>{t("preview.codesAfter")}</p>
        </section>

        <section id="venteliste" aria-labelledby="venteliste-h" className="rounded-[20px] bg-white border-2 border-ink p-6 md:p-8 flex flex-col gap-5 scroll-mt-6">
          <div className="flex flex-col gap-1">
            <span className="eyebrow">{t("preview.waitlistEyebrow")}</span>
            <h2 id="venteliste-h" className="m-0 font-display font-extrabold text-[22px] leading-[1.15] tracking-[-0.3px]">{t("preview.waitlistTitle")}</h2>
            <p className="m-0 text-[15px] leading-normal text-ink-soft">{t("preview.waitlistLead")}</p>
          </div>
          <WaitlistForm />
        </section>
      </main>
      <footer className="border-t-2 border-ink bg-white">
        <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-6 flex flex-wrap items-center justify-between gap-x-8 gap-y-3 text-sm text-muted">
          <span>{COMPANY.name} · CVR {COMPANY.cvr} · {COMPANY.address}</span>
          <nav aria-label={t("preview.footerNav")} className="flex flex-wrap gap-x-6 gap-y-2 items-center">
            {([["/privatliv", t("preview.footer.privacy")], ["/vilkaar", t("preview.footer.terms")], ["/kontakt", t("preview.footer.contact")], ["/login", t("preview.footer.login")]] as [string, string][]).map(([h, l]) => (
              <Link key={h} href={h} className="text-ink no-underline hover:text-accent inline-flex items-center min-h-11 sm:min-h-0">{l}</Link>
            ))}
          </nav>
        </div>
      </footer>
    </div>
  );
}
