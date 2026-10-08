import Link from "next/link";
import { COMPANY } from "./legal-page";
import { Icon } from "./ui";
import { breadcrumbList } from "./json-ld";
import { LANDING_PAGES, SITE_URL } from "@/lib/site";
import { INDUSTRIES } from "@/lib/industries";

export type SeoSection = { title: string; body: React.ReactNode };
export type SeoFaq = [string, string];

/** Shared frame for the keyword landing pages (AI-receptionist, AI-telefonsvarer, chatbot). Server component.
 *  Every claim is something Dialogbot does today; the page ends with the call-me demo and sign-up. */
export function SeoPage({ path, kicker, title, lead, points, sections, faq, article }: {
  path: string; kicker: string; title: string; lead: string; points: string[]; sections: SeoSection[]; faq: SeoFaq[];
  /** A guide under /viden: adds Article structured data and puts "Viden" in the breadcrumb. */
  article?: { published: string };
}) {
  const jsonLd = [
    {
      "@context": "https://schema.org", "@type": "FAQPage",
      mainEntity: faq.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })),
    },
    breadcrumbList(article ? [["Viden", "/viden"], [kicker, path]] : [[kicker, path]]),
    ...(article ? [{
      "@context": "https://schema.org", "@type": "Article", headline: title, description: lead, inLanguage: "da-DK",
      datePublished: article.published, dateModified: article.published, mainEntityOfPage: `${SITE_URL}${path}`,
      image: `${SITE_URL}/opengraph-image.png`,
      author: { "@type": "Organization", name: "Dialogbot", url: SITE_URL },
      publisher: { "@type": "Organization", name: "Dialogbot", logo: { "@type": "ImageObject", url: `${SITE_URL}/icon.png` } },
    }] : []),
  ];
  return (
    <div className="min-h-dvh bg-surface flex flex-col">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <header className="sticky top-0 z-50 bg-surface/90 backdrop-blur-xl shadow-[0_1px_8px_rgba(22,78,67,0.06)]">
        <div className="h-16 max-w-6xl mx-auto px-4 sm:px-6 flex items-center justify-between gap-space-md">
          <Link href="/" className="flex items-center gap-space-sm">
            <span className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-on-primary"><Icon name="support_agent" size={20} /></span>
            <span className="font-headline-sm text-headline-sm text-primary font-bold tracking-tight">Dialogbot</span>
          </Link>
          <nav className="hidden lg:flex items-center gap-space-lg font-label-lg text-label-lg" aria-label="Løsninger">
            {LANDING_PAGES.map((p) => (
              <Link key={p.href} href={p.href} aria-current={p.href === path ? "page" : undefined}
                className={p.href === path ? "text-primary font-bold" : "text-on-surface-variant hover:text-on-surface"}>{p.label}</Link>
            ))}
          </nav>
          <Link href="/#demo" className="inline-flex items-center gap-1.5 bg-secondary-fixed text-on-secondary-fixed font-label-lg text-label-lg font-bold px-space-md py-2 rounded-full"><Icon name="call" size={18} />Bliv ringet op</Link>
        </div>
      </header>

      <main id="main" className="flex-1">
        <section className="bg-primary text-on-primary">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 py-14 lg:py-20 grid lg:grid-cols-12 gap-space-xl items-center">
            <div className="lg:col-span-7 flex flex-col gap-space-md">
              <span className="font-label-md text-label-md uppercase tracking-[0.18em] text-secondary-fixed">{kicker}</span>
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-balance leading-[1.02]">{title}</h1>
              <p className="font-body-lg text-body-lg text-on-primary-container max-w-2xl">{lead}</p>
              <div className="flex flex-col sm:flex-row gap-space-sm pt-space-sm">
                <Link href="/#demo" className="inline-flex items-center justify-center gap-space-xs bg-secondary-fixed hover:bg-secondary-fixed-dim text-on-secondary-fixed font-label-lg text-label-lg font-bold px-gutter-lg py-space-md rounded-full shadow-md"><Icon name="call" size={20} />Bliv ringet op – hør det selv</Link>
                <Link href="/signup" className="inline-flex items-center justify-center gap-space-xs bg-on-primary/10 hover:bg-on-primary/20 text-on-primary font-label-lg text-label-lg px-gutter-lg py-space-md rounded-full">Start opsætning<Icon name="arrow_forward" size={18} /></Link>
              </div>
            </div>
            <ul className="lg:col-span-5 flex flex-col gap-space-sm bg-on-primary/10 rounded-2xl p-space-lg">
              {points.map((p) => (
                <li key={p} className="flex items-start gap-space-sm font-body-md text-body-md"><Icon name="check_circle" size={22} filled className="text-secondary-fixed mt-0.5 shrink-0" />{p}</li>
              ))}
            </ul>
          </div>
        </section>

        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-14 lg:py-20 flex flex-col gap-space-xl">
          {sections.map((s) => (
            <section key={s.title} className="flex flex-col gap-space-sm">
              <h2 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg font-bold text-primary tracking-tight text-balance">{s.title}</h2>
              <div className="font-body-lg text-body-lg text-on-surface-variant flex flex-col gap-space-sm [&_strong]:text-on-surface [&_a]:underline [&_a]:text-primary [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:flex [&_ul]:flex-col [&_ul]:gap-1">{s.body}</div>
            </section>
          ))}

          <section aria-labelledby="faq-title" className="flex flex-col gap-space-sm">
            <h2 id="faq-title" className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg font-bold text-primary tracking-tight">Ofte stillede spørgsmål</h2>
            <div className="flex flex-col gap-space-sm">
              {faq.map(([q, a]) => (
                <details key={q} className="group bg-surface-container-lowest rounded-xl p-space-md shadow-sm">
                  <summary className="cursor-pointer list-none flex items-center justify-between gap-space-md font-label-lg text-label-lg font-bold text-on-surface">{q}<Icon name="expand_more" size={22} className="text-primary transition-transform group-open:rotate-180" /></summary>
                  <p className="mt-space-sm font-body-md text-body-md text-on-surface-variant">{a}</p>
                </details>
              ))}
            </div>
          </section>

          <section className="rounded-[2rem] bg-primary text-on-primary p-space-lg sm:p-space-xl text-center flex flex-col items-center gap-space-md">
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-balance">Hør Dialogbot tage telefonen – på din egen telefon</h2>
            <p className="font-body-lg text-body-lg text-on-primary-container max-w-xl">Vælg en stemme og din branche, så ringer assistenten dig op på under et minut og viser, hvordan den ville tage telefonen for jer.</p>
            <Link href="/#demo" className="inline-flex items-center gap-space-sm bg-secondary-fixed text-on-secondary-fixed font-headline-sm text-headline-sm font-bold py-4 px-10 rounded-full shadow-lg"><Icon name="call" size={24} />Ring mig op nu<Icon name="arrow_forward" size={22} /></Link>
          </section>
        </div>
      </main>

      <footer className="bg-surface-container-low">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-space-xl flex flex-col md:flex-row md:items-center justify-between gap-space-md font-body-sm text-body-sm text-on-surface-variant">
          <span>{COMPANY.name} · dansk AI-receptionist · CVR-nr. {COMPANY.cvr}</span>
          <nav className="flex flex-wrap gap-x-space-md gap-y-1" aria-label="Sider">
            <Link href="/" className="hover:text-on-surface">Forside</Link>
            {LANDING_PAGES.map((p) => <Link key={p.href} href={p.href} className="hover:text-on-surface">{p.label}</Link>)}
            <Link href="/kontakt" className="hover:text-on-surface">Kontakt</Link>
            <Link href="/privatliv" className="hover:text-on-surface">Privatliv</Link>
            <Link href="/vilkaar" className="hover:text-on-surface">Vilkår</Link>
          </nav>
        </div>
        <nav className="max-w-6xl mx-auto px-4 sm:px-6 pb-space-xl flex flex-wrap gap-x-space-md gap-y-1 font-body-sm text-body-sm text-on-surface-variant" aria-label="Brancher">
          {INDUSTRIES.map((i) => <Link key={i.slug} href={`/ai-receptionist/${i.slug}`} className="hover:text-on-surface">AI-receptionist til {i.name}</Link>)}
        </nav>
      </footer>
    </div>
  );
}
