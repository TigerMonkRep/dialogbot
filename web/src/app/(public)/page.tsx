import Link from "next/link";
import { cookies } from "next/headers";
import type { Metadata } from "next";
import { COMPANY } from "@/components/legal-page";
import { SiteChrome } from "@/components/site-chrome";
import { ArrowIcon, BuildArrowIcon, PhoneIcon } from "@/components/site-icons";
import { API_BASE_URL, KNOWN_ACCOUNT_COOKIE, REFERRAL_COOKIE, SESSION_COOKIE } from "@/lib/config";
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";

/** Indgang — the front page in the "Byggevejledning" design (design-reference/byggevejledning/Indgang.dc.html):
 *  two doors. Vej A hears the receptionist (/proev), Vej B reads how it is built (/byggevejledning).
 *  No claims beyond the two list prices; the ambassador banner is kept from the previous front page. */
type Recommender = { first_name: string; headline: string; code: string; customer_discount_bp: number };

/** The ambassador who sent this visitor (cookie set by /a/{slug}); null when none or no longer active, and
 *  never for someone who already has an account (logged in now, or has logged in from this browser before). */
async function recommender(): Promise<Recommender | null> {
  const store = await cookies();
  if (store.get(SESSION_COOKIE)?.value || store.get(KNOWN_ACCOUNT_COOKIE)?.value) return null;
  const ref = store.get(REFERRAL_COOKIE)?.value;
  if (!ref) return null;
  try {
    const r = await fetch(`${API_BASE_URL}/api/v1/public/ambassadors/${encodeURIComponent(ref)}`, { cache: "no-store" });
    return r.ok ? ((await r.json()) as Recommender) : null;
  } catch { return null; }
}

export const metadata: Metadata = {
  title: { absolute: "Dialogbot – Hvor vil du starte? Din AI-receptionist på dansk" },
  description: "Dialogbot er din AI-receptionist på dansk, døgnet rundt. Vælg din vej: hør den tage telefonen for din virksomhed på 2 minutter, eller læs byggevejledningen – 3 trin, ca. 30 minutter.",
  alternates: { canonical: "/" },
  openGraph: { url: "/", title: "Dialogbot – Hvor vil du starte?", images: ["/opengraph-image.png"] },
};

const door = "group flex flex-col gap-[22px] p-6 sm:p-8 rounded-3xl bg-white border-2 border-ink shadow-block text-ink no-underline min-h-[420px] transition-[transform,box-shadow] duration-150 hover:-translate-x-[3px] hover:-translate-y-[3px] hover:[box-shadow:11px_11px_0_var(--color-ink)] focus-visible:outline-4 focus-visible:outline-accent focus-visible:outline-offset-4";
const stage = "flex-1 relative min-h-[170px] rounded-2xl bg-panel flex items-center justify-center overflow-hidden";

export default async function Home() {
  const rec = await recommender();
  return (
    <SiteChrome compactFooter={false}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData()) }} />
      {rec && (
        <section aria-label="Anbefaling" className="bg-highlight border-b-2 border-ink">
          <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-3 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-6">
            <span className="w-10 h-10 rounded-full bg-ink text-highlight flex items-center justify-center font-display font-extrabold text-lg shrink-0" aria-hidden>{rec.first_name.slice(0, 1)}</span>
            <div className="flex-1 min-w-0 text-ink">
              <p className="font-semibold text-[15px]">{rec.first_name} har anbefalet Dialogbot til dig – du får {rec.customer_discount_bp / 100} % rabat på din første måned.</p>
              {rec.headline && <p className="text-sm">&ldquo;{rec.headline}&rdquo;</p>}
              <p className="text-xs text-ink-soft">{rec.first_name} er Dialogbot-ambassadør og får en bonus, hvis du bliver kunde. Rabatten kommer automatisk, når du opretter dig herfra.</p>
            </div>
            <Link href="/signup" className="inline-flex items-center justify-center gap-2 min-h-11 bg-ink text-white font-semibold text-[15px] px-5 rounded-xl no-underline">Kom i gang<ArrowIcon size={16} /></Link>
          </div>
        </section>
      )}

      <div className="max-w-[1180px] w-full mx-auto px-4 sm:px-6 pt-10 sm:pt-14 pb-16 flex flex-col gap-9">
        <div className="flex flex-col gap-3 items-center text-center">
          <span className="eyebrow text-[13px] tracking-[1.5px]">Din AI-receptionist – på dansk, døgnet rundt</span>
          <h1 className="m-0 font-display font-extrabold text-[clamp(40px,5.4vw,70px)] leading-none tracking-[-1.8px]">Hvor vil du starte?</h1>
          <p className="m-0 text-lg leading-normal text-ink-soft max-w-[560px]">To veje, samme mål. Vælg den, der passer dig – du kan altid skifte med knappen øverst.</p>
        </div>

        {/* The two doors */}
        <div className="grid gap-7 items-stretch [grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr))]">
          {/* Vej A: hear it */}
          <Link href="/proev" className={door}>
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-highlight text-[13px] font-semibold tracking-[1px] uppercase">2 min · ingen tilmelding</span>
              <span className="font-display font-extrabold text-[13px] tracking-[1.5px] uppercase text-muted">Vej A</span>
            </div>
            <div className={stage}>
              <div className="relative w-[110px] h-[110px] flex items-center justify-center">
                <span aria-hidden className="ringwave absolute inset-0 rounded-full border-[3px] border-accent" />
                <span className="w-[84px] h-[84px] rounded-full bg-accent inline-flex items-center justify-center"><PhoneIcon size={38} stroke="#FFFFFF" /></span>
              </div>
              <div className="absolute left-5 bottom-[18px] flex items-end gap-2">
                <span className="flex-none w-[26px] h-[26px] rounded-full bg-accent inline-flex items-center justify-center font-display font-extrabold text-xs text-white">D</span>
                <span className="px-3 py-2 rounded-[12px_12px_12px_4px] bg-white border-2 border-ink text-[13px] font-medium">Skal jeg ringe til dig nu?</span>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <span className="font-display font-extrabold text-[30px] leading-[1.05] tracking-[-0.6px]">Hør den først</span>
              <span className="text-base leading-normal text-ink-soft">Snak med chatten – så ringer den til dig som din egen receptionist. Spørg som en kunde ville gøre.</span>
            </div>
            <span className="inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-accent group-hover:bg-accent-deep text-white font-semibold text-[17px]">Prøv den nu<ArrowIcon size={18} /></span>
          </Link>

          {/* Vej B: see how it is built */}
          <Link href="/byggevejledning" className={door}>
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-panel border-[1.5px] border-ink text-[13px] font-semibold tracking-[1px] uppercase">3 trin · ca. 30 min</span>
              <span className="font-display font-extrabold text-[13px] tracking-[1.5px] uppercase text-muted">Vej B</span>
            </div>
            <div className={`${stage} gap-2 sm:gap-3.5 px-3`}>
              {["1", "2", "3"].map((n, i) => (
                <span key={n} className="contents">
                  {i > 0 && <BuildArrowIcon className="text-ink shrink-0 w-6 sm:w-[30px]" />}
                  <span className="inline-flex w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-highlight items-center justify-center font-display font-extrabold text-[30px] sm:text-[34px] shrink-0">{n}</span>
                </span>
              ))}
              <div className="absolute right-5 bottom-[18px] px-2.5 py-1.5 rounded-full bg-white border-2 border-ink font-display font-bold text-[13px]">Tændt</div>
            </div>
            <div className="flex flex-col gap-2">
              <span className="font-display font-extrabold text-[30px] leading-[1.05] tracking-[-0.6px]">Se, hvordan den bygges</span>
              <span className="text-base leading-normal text-ink-soft">Byggevejledningen: hvad du skal bruge, hvad den kan, hvad den koster – og de 3 trin til din egen.</span>
            </div>
            <span className="inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-white border-2 border-ink text-ink font-semibold text-[17px] group-hover:bg-panel">Åbn byggevejledningen<ArrowIcon size={18} /></span>
          </Link>
        </div>

        {/* Both paths converge */}
        <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-3 px-6 py-[18px] rounded-2xl border-[1.5px] border-ink bg-white">
          <span className="inline-flex items-center gap-2 text-sm font-semibold"><span aria-hidden className="w-[22px] h-3 rounded bg-accent" />Vej A</span>
          <svg aria-hidden width="34" height="20" viewBox="0 0 34 20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-ink"><path d="M3 10h26M23 4l6 6-6 6" /></svg>
          <span className="inline-flex items-center gap-2 px-3.5 py-2 rounded-[10px] bg-ink text-white font-display font-bold text-sm">Din egen receptionist – tændt</span>
          <svg aria-hidden width="34" height="20" viewBox="0 0 34 20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-ink"><path d="M31 10H5M11 4l-6 6 6 6" /></svg>
          <span className="inline-flex items-center gap-2 text-sm font-semibold"><span aria-hidden className="w-[22px] h-3 rounded bg-highlight" />Vej B</span>
          <span className="basis-full text-center text-[13px] text-muted">Begge veje ender samme sted. Den, der ringer til dig i vej A, er den samme, der guider dig i vej B.</span>
        </div>

        {/* Undecided? ask the assistant */}
        <div className="flex flex-wrap items-center justify-center gap-3">
          <span className="inline-flex w-8 h-8 rounded-full bg-accent items-center justify-center font-display font-extrabold text-[13px] text-white">D</span>
          <span className="text-[15px] text-ink-soft">I tvivl?</span>
          <Link href="/proev" className="text-[15px] font-semibold text-ink underline underline-offset-4 inline-flex items-center min-h-11">Spørg chatten – den anbefaler en vej på 10 sekunder</Link>
        </div>
        <p className="m-0 text-center text-sm text-muted">Fra 1.495 kr./md. eller 149 kr. pr. godkendt henvendelse · ekskl. moms</p>
      </div>
    </SiteChrome>
  );
}

/** schema.org data for Google: the company, the site and the product with its two list prices. */
function structuredData() {
  const org = { "@type": "Organization", "@id": `${SITE_URL}/#organization`, name: SITE_NAME, url: SITE_URL,
    logo: `${SITE_URL}/icon.png`, email: COMPANY.email, telephone: "+4593703433", vatID: `DK${COMPANY.cvr}`,
    address: { "@type": "PostalAddress", streetAddress: "Abildgade 18", postalCode: "8200", addressLocality: "Aarhus", addressCountry: "DK" } };
  return [
    { "@context": "https://schema.org", ...org },
    { "@context": "https://schema.org", "@type": "WebSite", "@id": `${SITE_URL}/#website`, url: SITE_URL, name: SITE_NAME,
      inLanguage: "da-DK", publisher: { "@id": `${SITE_URL}/#organization` } },
    { "@context": "https://schema.org", "@type": "SoftwareApplication", name: "Dialogbot", applicationCategory: "BusinessApplication",
      operatingSystem: "Web", description: SITE_DESCRIPTION, inLanguage: "da", url: SITE_URL,
      publisher: { "@id": `${SITE_URL}/#organization` },
      offers: [
        { "@type": "Offer", name: "Model A – fast pris", price: "1495", priceCurrency: "DKK", description: "Pr. måned ekskl. moms" },
        { "@type": "Offer", name: "Model B – pr. henvendelse", price: "149", priceCurrency: "DKK", description: "Pr. godkendt henvendelse ekskl. moms" },
      ] },
  ];
}
