import Link from "next/link";
import { SiteChrome, EMAIL, PHONE_DISPLAY, PHONE_TEL } from "./site-chrome";
import { ArrowIcon, CheckIcon, ChevronIcon, PhoneIcon, PlayIcon } from "./site-icons";
import { SITE_URL } from "@/lib/site";

export type SeoSection = { title: string; body: React.ReactNode };
export type SeoFaq = [string, string];

/** Shared frame for the keyword landing pages (AI-receptionist, AI-telefonsvarer, chatbot, priser, viden) in the
 *  "Byggevejledning" design: eyebrow + Outfit h1 on the panel surface, numbered sections as 2 px ink cards, FAQ as
 *  <details>, dark CTA. Server component. Every claim is something Dialogbot does today. */
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
    {
      "@context": "https://schema.org", "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Dialogbot", item: SITE_URL },
        ...(article ? [{ "@type": "ListItem", position: 2, name: "Viden", item: `${SITE_URL}/viden` }] : []),
        { "@type": "ListItem", position: article ? 3 : 2, name: kicker, item: `${SITE_URL}${path}` },
      ],
    },
    ...(article ? [{
      "@context": "https://schema.org", "@type": "Article", headline: title, description: lead, inLanguage: "da-DK",
      datePublished: article.published, dateModified: article.published, mainEntityOfPage: `${SITE_URL}${path}`,
      image: `${SITE_URL}/opengraph-image.png`,
      author: { "@type": "Organization", name: "Dialogbot", url: SITE_URL },
      publisher: { "@type": "Organization", name: "Dialogbot", logo: { "@type": "ImageObject", url: `${SITE_URL}/icon.png` } },
    }] : []),
  ];
  const container = "max-w-[1180px] mx-auto px-4 sm:px-6";
  return (
    <SiteChrome>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />

      {/* Hero on the step surface */}
      <section className="bg-panel border-b-2 border-ink">
        <div className={`${container} py-12 sm:py-16 flex flex-wrap gap-10 items-start`}>
          <div className="flex-[1_1_460px] min-w-0 flex flex-col gap-4">
            <nav aria-label="Brødkrumme" className="eyebrow text-[13px] tracking-[1.5px] flex flex-wrap items-center gap-2">
              <Link href="/" className="text-muted no-underline hover:text-ink">Dialogbot</Link><span aria-hidden>/</span>
              {article && <><Link href="/viden" className="text-muted no-underline hover:text-ink">Viden</Link><span aria-hidden>/</span></>}
              <span className="text-ink">{kicker}</span>
            </nav>
            <h1 className="m-0 font-display font-extrabold text-[clamp(34px,4.6vw,60px)] leading-[1.03] tracking-[-1.4px] text-balance">{title}</h1>
            <p className="m-0 text-lg leading-[1.55] text-ink-soft max-w-[620px]">{lead}</p>
            <div className="flex flex-wrap gap-3 pt-1">
              <Link href="/proev" className="inline-flex items-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[17px]"><PlayIcon size={18} />Prøv den – den ringer til dig</Link>
              <Link href="/byggevejledning" className="inline-flex items-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-white border-2 border-ink text-ink no-underline font-semibold text-[17px] hover:bg-panel">Se byggevejledningen<ArrowIcon size={18} /></Link>
            </div>
          </div>
          <div className="flex-[1_1_300px] min-w-0 max-w-[460px] bg-white border-2 border-ink rounded-[20px] p-5 sm:p-6 flex flex-col gap-3 shadow-block">
            <span className="eyebrow">Kort fortalt</span>
            <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-[15px] leading-snug">
              {points.map((p) => <li key={p} className="flex items-start gap-2.5"><CheckIcon size={20} stroke="#2456F6" className="flex-none mt-0.5" />{p}</li>)}
            </ul>
          </div>
        </div>
      </section>

      {/* Numbered sections: nummer, overskrift, tekst */}
      <div className={`${container} py-12 sm:py-16 flex flex-col gap-6 max-w-[880px]`}>
        {sections.map((s, i) => (
          <section key={s.title} className="border-2 border-ink rounded-[20px] bg-white p-5 sm:p-7 flex flex-col gap-4">
            <div className="flex items-center gap-3.5">
              <span className="inline-flex w-10 h-10 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-xl shrink-0">{i + 1}</span>
              <h2 className="m-0 font-display font-bold text-[22px] sm:text-[26px] leading-[1.15] tracking-[-0.4px] text-balance">{s.title}</h2>
            </div>
            <div className="text-[17px] leading-[1.55] text-ink-soft flex flex-col gap-3 [&_strong]:text-ink [&_a]:text-accent [&_a]:underline [&_a]:underline-offset-4 [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:flex [&_ul]:flex-col [&_ul]:gap-1.5 [&_p]:m-0">{s.body}</div>
          </section>
        ))}

        <section aria-labelledby="faq-title" className="flex flex-col gap-3 pt-6">
          <span className="eyebrow text-[13px] tracking-[1.5px]">Spørgsmål</span>
          <h2 id="faq-title" className="m-0 font-display font-extrabold text-[clamp(28px,3vw,38px)] leading-[1.1] tracking-[-0.8px]">Ofte stillede spørgsmål</h2>
          <div className="flex flex-col border-t-2 border-ink mt-2">
            {faq.map(([q, a]) => (
              <details key={q} className="faq border-b-2 border-ink">
                <summary className="flex items-center justify-between gap-4 py-5 font-display font-bold text-[19px] min-h-11">{q}<ChevronIcon size={22} className="chev flex-none" /></summary>
                <p className="m-0 mb-5 text-base leading-[1.55] text-ink-soft max-w-[680px]">{a}</p>
              </details>
            ))}
          </div>
        </section>
      </div>

      {/* Dark CTA */}
      <section className="bg-ink text-white border-t-2 border-ink">
        <div className={`${container} py-14 sm:py-16 flex flex-wrap gap-8 items-center justify-between`}>
          <div className="flex-[1_1_420px] flex flex-col gap-3">
            <h2 className="m-0 font-display font-extrabold text-[clamp(30px,3.6vw,46px)] leading-[1.05] tracking-[-1px] text-balance">Hør Dialogbot tage telefonen – på din egen telefon</h2>
            <p className="m-0 text-lg leading-[1.55] text-line max-w-[520px]">Fortæl chatten, hvad din virksomhed hedder og hvad I laver, så ringer assistenten dig op og viser, hvordan den ville tage telefonen for jer.</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href="/proev" className="inline-flex items-center gap-2.5 min-h-14 px-6 rounded-[14px] bg-highlight hover:bg-highlight-deep text-ink no-underline font-display font-bold text-lg"><PhoneIcon size={20} width={2.4} />Ring mig op nu</Link>
            <a href={PHONE_TEL} className="inline-flex items-center gap-2.5 min-h-14 px-6 rounded-[14px] border-2 border-white text-white no-underline font-semibold text-[17px] hover:bg-white/10">{PHONE_DISPLAY}</a>
          </div>
          <p className="basis-full m-0 text-sm text-line">Eller skriv til <a href={`mailto:${EMAIL}`} className="text-white underline underline-offset-4">{EMAIL}</a>. Fra 1.495 kr./md. eller 149 kr. pr. godkendt henvendelse · ekskl. moms.</p>
        </div>
      </section>
    </SiteChrome>
  );
}
