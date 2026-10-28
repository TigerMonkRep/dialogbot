import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { COMPANY } from "@/components/legal-page";
import { LogoMark } from "@/components/site-chrome";
import { StepNumber } from "@/components/lego";
import { gateEnabled } from "@/lib/preview-gate";
import { safeNext } from "@/lib/safe-next";
import { UnlockForm, WaitlistForm } from "./forms";

export const metadata: Metadata = {
  title: "Dialogbot – privat preview",
  description: "Dialogbot er en dansk AI-assistent til telefon, webchat og opfølgning. Skriv dig op til tidlig adgang.",
};

/** P00 — the invitation-code gate in the Byggevejledning design: one centred 2 px ink card with the logo, the
 *  yellow "0" step square, the code field and the blue button; the waitlist below it.
 *  Honest: no invented metrics, no demo code on the page, no audio sample that does not exist.
 *  No link to "/" on this page: a prefetch of "/" without the cookie would cache the redirect back here. */
export default async function PreviewPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  const target = safeNext(next, "/");
  // Gate switched off: the real landing page is public, so old /preview links go straight there.
  if (!gateEnabled()) redirect(target);
  return (
    <div className="min-h-dvh bg-panel text-ink flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-white">Spring til indhold</a>
      <main id="main" className="flex-1 w-full max-w-[560px] mx-auto px-4 sm:px-6 py-10 md:py-16 flex flex-col gap-6">
        <section aria-labelledby="laas-op" className="rounded-[20px] bg-white border-2 border-ink p-6 md:p-8 flex flex-col gap-6 shadow-block">
          <div className="flex items-center justify-between gap-4">
            <span className="inline-flex items-center gap-2.5 text-ink"><LogoMark size={36} /><span className="font-display font-extrabold tracking-[-0.3px] text-[22px]">Dialogbot</span></span>
            <span className="inline-flex items-center min-h-6 px-2.5 rounded-full bg-highlight text-ink text-[11px] font-semibold uppercase tracking-[0.12em]">Privat preview</span>
          </div>
          <div className="flex items-center gap-3.5">
            <StepNumber value="0" />
            <div className="flex flex-col gap-1">
              <span className="eyebrow">Trin 0 · Før du bygger</span>
              <h1 id="laas-op" className="m-0 font-display font-extrabold text-[clamp(24px,3vw,30px)] leading-[1.1] tracking-[-0.5px]">Lås op med forhåndskode</h1>
            </div>
          </div>
          <p className="m-0 text-[15px] leading-normal text-ink-soft">Dialogbot er en dansk AI-receptionist til telefon, webchat og opfølgning. Vi finpudser detaljerne før offentlig åbning. Indtast den invitationskode, du har fået, for at se forsiden og oprette en konto.</p>
          <UnlockForm next={target} />
          <p className="m-0 text-[13px] leading-normal text-muted">Koder udleveres til pilotvirksomheder og udvalgte partnere. Har du allerede en konto, så <Link href="/login" className="text-accent font-semibold underline underline-offset-4">log ind</Link>.</p>
        </section>

        <section id="venteliste" aria-labelledby="venteliste-h" className="rounded-[20px] bg-white border-2 border-ink p-6 md:p-8 flex flex-col gap-5 scroll-mt-6">
          <div className="flex flex-col gap-1">
            <span className="eyebrow">Ingen kode?</span>
            <h2 id="venteliste-h" className="m-0 font-display font-extrabold text-[22px] leading-[1.15] tracking-[-0.3px]">Skriv dig op til tidlig adgang</h2>
            <p className="m-0 text-[15px] leading-normal text-ink-soft">Få besked i din indbakke, så snart vi åbner for nye virksomheder. Ingen spam – kun besked ved åbning, og du kan slette dig når som helst.</p>
          </div>
          <WaitlistForm />
        </section>
      </main>
      <footer className="border-t-2 border-ink bg-white">
        <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-6 flex flex-wrap items-center justify-between gap-x-8 gap-y-3 text-sm text-muted">
          <span>{COMPANY.name} · CVR {COMPANY.cvr} · {COMPANY.address}</span>
          <nav aria-label="Sidefod" className="flex flex-wrap gap-x-6 gap-y-2 items-center">
            {([["/privatliv", "Privatliv"], ["/vilkaar", "Handelsbetingelser"], ["/kontakt", "Kontakt"], ["/login", "Log ind for teamet"]] as [string, string][]).map(([h, l]) => (
              <Link key={h} href={h} className="text-ink no-underline hover:text-accent inline-flex items-center min-h-11 sm:min-h-0">{l}</Link>
            ))}
          </nav>
        </div>
      </footer>
    </div>
  );
}
