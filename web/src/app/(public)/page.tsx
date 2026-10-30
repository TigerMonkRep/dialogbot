import Link from "next/link";
import { cookies } from "next/headers";
import type { Metadata } from "next";
import { COMPANY } from "@/components/legal-page";
import { SiteChrome } from "@/components/site-chrome";
import { ExplainerVideo } from "@/components/explainer-video";
import { videoStructuredData } from "@/lib/video";
import { ArrowIcon, CalendarIcon, ChatIcon, CheckIcon, PhoneIcon, PlayIcon, SendIcon, SmsIcon } from "@/components/site-icons";
import { API_BASE_URL, KNOWN_ACCOUNT_COOKIE, REFERRAL_COOKIE, SESSION_COOKIE } from "@/lib/config";
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";

/** The front page: one story, read top to bottom. What Dialogbot is (one sentence + the 70-second video), how it
 *  works (3 steps), what it does (4 tiles), a real call to listen to, the price, and at the end the two ways in:
 *  try it (/proev) or build it yourself (/byggevejledning). No "Vej A / Vej B" jargon: visitors did not understand it.
 *  No claims beyond the list prices; the ambassador banner is kept. */
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
  title: { absolute: "Dialogbot – AI-receptionist på dansk, der tager telefonen døgnet rundt" },
  description: "Dialogbot tager telefonen, når I ikke kan: en AI-receptionist på dansk, der svarer døgnet rundt, booker tider i jeres kalender og sender jer en besked om hvert opkald. Fra 2.495 kr./md.",
  alternates: { canonical: "/" },
  openGraph: { url: "/", title: "Dialogbot tager telefonen, når I ikke kan", images: ["/opengraph-image.png"] },
};

const container = "max-w-[1180px] mx-auto px-4 sm:px-6";
const eyebrow = "eyebrow text-[13px] tracking-[1.5px]";
const h2 = "m-0 font-display font-extrabold text-[clamp(30px,3.4vw,44px)] leading-[1.05] tracking-[-1px]";
const btnPrimary = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[17px]";
const btnOutline = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-white border-2 border-ink text-ink no-underline font-semibold text-[17px] hover:bg-panel";
const stepNo = "inline-flex w-14 h-14 rounded-[14px] bg-highlight items-center justify-center font-display font-extrabold text-[30px] shrink-0";
const tile = "inline-flex w-12 h-12 rounded-xl bg-accent items-center justify-center shrink-0";

function Bubble({ who, children }: { who: "D" | "K"; children: React.ReactNode }) {
  const bot = who === "D";
  return (
    <div className={`flex gap-2.5 items-end ${bot ? "" : "justify-end"}`}>
      {bot && <span className="flex-none w-8 h-8 rounded-full bg-accent inline-flex items-center justify-center font-display font-extrabold text-[13px] text-white">D</span>}
      <p className={`m-0 px-4 py-3 text-[15px] leading-normal max-w-[420px] ${bot ? "rounded-[16px_16px_16px_4px] bg-white border-2 border-ink" : "rounded-[16px_16px_4px_16px] bg-ink text-white"}`}>{children}</p>
      {!bot && <span className="flex-none w-8 h-8 rounded-full bg-highlight inline-flex items-center justify-center font-display font-extrabold text-[13px]">K</span>}
    </div>
  );
}

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

      {/* 1. HERO: what it is, in one sentence – and the video that explains it */}
      <section className="bg-white">
        <div className={`${container} pt-10 sm:pt-16 pb-12 sm:pb-16 flex flex-wrap gap-10 lg:gap-14 items-center`}>
          <div className="flex-[1_1_380px] min-w-0 flex flex-col gap-5">
            <span className={eyebrow}>AI-receptionist · på dansk · døgnet rundt</span>
            <h1 className="m-0 font-display font-extrabold text-[clamp(38px,5vw,64px)] leading-[1.02] tracking-[-1.6px]">Dialogbot tager telefonen, når I ikke kan.</h1>
            <p className="m-0 text-[18px] sm:text-[19px] leading-[1.55] text-ink-soft max-w-[540px]">En AI-receptionist på dansk, der svarer døgnet rundt, booker tider i jeres kalender og sender jer en besked om hvert opkald. I beholder jeres nummer. Fra 2.495 kr./md. ekskl. moms.</p>
            <div className="flex flex-wrap gap-3">
              <Link href="/proev" className={btnPrimary}>Prøv den – den ringer til dig<ArrowIcon size={18} /></Link>
              <div className="hidden sm:block"><ExplainerVideo variant="button" /></div>
            </div>
            <p className="m-0 text-sm text-muted">2 minutter, ingen tilmelding. Spørg den, som en kunde ville gøre.</p>
          </div>
          <div className="flex-[1_1_420px] min-w-0 max-w-[640px]"><ExplainerVideo variant="poster" /></div>
        </div>
      </section>

      {/* 2. HOW IT WORKS: three steps */}
      <section className="bg-panel border-y-2 border-ink">
        <div className={`${container} py-14 sm:py-20 flex flex-col gap-9`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>Sådan virker det</span>
            <h2 className={h2}>Kunden ringer. Dialogbot svarer. Du får besked.</h2>
          </div>
          <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr))]">
            {[
              ["1", "Kunden ringer – som altid", "På jeres eget nummer. Er I optaget eller har lukket, tager Dialogbot den inden for to sekunder og præsenterer sig som jeres receptionist.", <PhoneIcon key="p" size={30} stroke="#FFFFFF" />],
              ["2", "Den svarer og booker", "Ud fra de ydelser, priser og åbningstider, I selv har godkendt. Den gætter aldrig. Skal kunden have en tid, finder den en ledig i jeres kalender og sender SMS.", <CalendarIcon key="c" size={30} stroke="#FFFFFF" />],
              ["3", "Du får en besked", "Navn, nummer og hvad det drejede sig om – som SMS eller mail med det samme, og en samlet rapport hver dag. Er der noget, den ikke kan klare, tager den en besked til dig.", <SmsIcon key="s" size={30} stroke="#FFFFFF" />],
            ].map(([n, title, text, icon]) => (
              <article key={n as string} className="flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink">
                <div className="flex items-center gap-4">
                  <span className={stepNo}>{n as string}</span>
                  <span className={tile}>{icon}</span>
                </div>
                <h3 className="m-0 font-display font-extrabold text-[24px] leading-[1.1] tracking-[-0.4px]">{title as string}</h3>
                <p className="m-0 text-[16px] leading-[1.55] text-ink-soft">{text as string}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* 3. WHAT IT DOES: four tiles */}
      <section className="bg-white">
        <div className={`${container} py-14 sm:py-20 flex flex-col gap-9`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>Det kan den</span>
            <h2 className={h2}>Fire ting, én receptionist</h2>
          </div>
          <div className="grid gap-5 [grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr))]">
            {[
              ["Tager telefonen", "Døgnet rundt, på dansk, med en stemme I selv vælger. Siger ærligt, at den er en digital assistent, hvis kunden spørger.", <PhoneIcon key="1" size={24} stroke="#FFFFFF" />],
              ["Booker aftaler", "Finder ledige tider i Google Kalender eller Microsoft 365, booker, flytter og aflyser – og sender bekræftelse på SMS.", <CalendarIcon key="2" size={24} stroke="#FFFFFF" />],
              ["Svarer på hjemmesiden", "Den samme viden som webchat på jeres side – én kodelinje, så er den på.", <ChatIcon key="3" size={24} stroke="#FFFFFF" />],
              ["Ringer kunder op", "Følger op på tilbud eller minder om service – kun til kunder, der har sagt ja. 4 kr. pr. opkald + 2 kr. pr. minut.", <SendIcon key="4" size={24} stroke="#FFFFFF" />],
            ].map(([title, text, icon]) => (
              <div key={title as string} className="flex flex-col gap-3 p-5 rounded-2xl bg-panel border-[1.5px] border-ink">
                <span className={tile}>{icon}</span>
                <span className="font-display font-bold text-[20px] leading-tight">{title as string}</span>
                <span className="text-[15px] leading-[1.5] text-ink-soft">{text as string}</span>
              </div>
            ))}
          </div>
          <p className="m-0 text-[15px] text-ink-soft">Alt, den siger, bygger på viden I selv har godkendt – og enhver ændring viser den jer først: før → efter, «Godkend?».</p>
        </div>
      </section>

      {/* 4. HEAR A CALL */}
      <section id="demo" className="bg-panel border-y-2 border-ink scroll-mt-6">
        <div className={`${container} py-14 sm:py-20 flex flex-wrap gap-12 items-center`}>
          <div className="flex-[1_1_380px] min-w-0 flex flex-col gap-4">
            <span className={eyebrow}>Hør et opkald</span>
            <h2 className={h2}>Sådan lyder det, når Dialogbot tager telefonen</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">Et opkald til en tømrer. Prøv den selv – så ringer den til dig og tager imod dig, som var du en kunde.</p>
            <Link href="/proev" className={`${btnPrimary} self-start min-h-14 px-6`}><PlayIcon size={20} />Prøv den – den ringer til dig</Link>
          </div>
          <div className="flex-[1_1_380px] min-w-0 flex flex-col gap-3 p-5 sm:p-6 rounded-[20px] bg-white border-2 border-ink">
            <div className="flex items-center justify-between gap-3 text-[13px] font-semibold text-muted tracking-[1px] uppercase"><span>Opkald · Tømrerfirma (eksempel)</span><span>0:48</span></div>
            <Bubble who="D">Du har ringet til Nørgaard Tømrer, det er Dialogbot. Hvad kan jeg hjælpe med?</Bubble>
            <Bubble who="K">Hej, jeg skal have skiftet et vindue. Kan I komme og kigge i næste uge?</Bubble>
            <Bubble who="D">Det kan vi godt. Der er ledigt tirsdag kl. 9 eller torsdag kl. 14. Hvad passer bedst?</Bubble>
            <Bubble who="K">Tirsdag, tak.</Bubble>
            <div className="flex items-center gap-2 mt-1.5 px-3 py-2.5 rounded-[10px] bg-panel border-[1.5px] border-ink text-[13px] font-semibold"><CheckIcon size={16} stroke="#2456F6" />Aftale booket: tirsdag kl. 9 · SMS sendt til dig og kunden</div>
          </div>
        </div>
      </section>

      {/* 5. PRICE */}
      <section id="pris" className="bg-white scroll-mt-6">
        <div className={`${container} py-14 sm:py-20 flex flex-col gap-9`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>Pris</span>
            <h2 className={h2}>Ét abonnement. Ingen pris pr. henvendelse.</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">Alle priser er ekskl. moms. Ingen binding – opsigelse måned til måned.</p>
          </div>
          <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr))]">
            <article className="flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink shadow-block">
              <span className="font-display font-bold text-xl">Abonnement</span>
              <div className="flex items-baseline gap-2 flex-wrap"><span className="text-lg font-semibold text-ink-soft">Fra</span><span className="font-display font-extrabold text-[48px] tracking-[-1.5px] leading-none">2.495</span><span className="text-lg font-semibold text-ink-soft">kr./md.</span></div>
              <span className="text-[15px] text-ink-soft">Telefon, booking og webchat er med – inkl. 300 minutters indgående opkald om måneden. Gør-det-selv-opsætning er med.</span>
            </article>
            <article className="flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink">
              <span className="font-display font-bold text-xl">Udgående kampagneopkald</span>
              <div className="flex items-baseline gap-2 flex-wrap"><span className="font-display font-extrabold text-[48px] tracking-[-1.5px] leading-none">4</span><span className="text-lg font-semibold text-ink-soft">kr. pr. opkald + 2 kr. pr. minut</span></div>
              <span className="text-[15px] text-ink-soft">Kun hvis I vil have Dialogbot til at ringe ud. Ubesvaret: 4 kr. Tre minutters samtale: 10 kr. I ser den højeste pris, før I starter.</span>
            </article>
            <article className="flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink">
              <span className="font-display font-bold text-xl">Opsætning fra vores specialister</span>
              <div className="flex items-baseline gap-2 flex-wrap"><span className="font-display font-extrabold text-[48px] tracking-[-1.5px] leading-none">5.000</span><span className="text-lg font-semibold text-ink-soft">kr. én gang</span></div>
              <span className="text-[15px] text-ink-soft">Skræddersyet opsætning og integration til jeres egne systemer – kalender, CRM, bookingsystem. Kun hvis I ikke vil gøre det selv.</span>
            </article>
          </div>
          <Link href="/priser" className="self-start text-[15px] font-semibold text-ink underline underline-offset-4 inline-flex items-center min-h-11">Alle detaljer om prisen →</Link>
        </div>
      </section>

      {/* 6. GET STARTED: the two ways in, in plain words */}
      <section className="bg-panel border-t-2 border-ink">
        <div className={`${container} py-14 sm:py-20 flex flex-col gap-8`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>Kom i gang</span>
            <h2 className={h2}>Hør den først – eller byg den selv på 30 minutter</h2>
          </div>
          <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr))]">
            <Link href="/proev" className="group flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink shadow-block text-ink no-underline">
              <span className="inline-flex self-start items-center gap-2 px-3 py-1.5 rounded-full bg-highlight text-[13px] font-semibold tracking-[1px] uppercase">2 min · ingen tilmelding</span>
              <span className="font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.5px]">Prøv den – den ringer til dig</span>
              <span className="text-[16px] leading-[1.5] text-ink-soft">Skriv til Peter i chatten eller tryk «Ja, ring til mig». Så ringer Dialogbot op og tager imod dig som din egen receptionist.</span>
              <span className={`${btnPrimary} mt-auto group-hover:bg-accent-deep`}>Prøv den nu<ArrowIcon size={18} /></span>
            </Link>
            <Link href="/byggevejledning" className="group flex flex-col gap-4 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink text-ink no-underline">
              <span className="inline-flex self-start items-center gap-2 px-3 py-1.5 rounded-full bg-panel border-[1.5px] border-ink text-[13px] font-semibold tracking-[1px] uppercase">3 trin · ca. 30 min</span>
              <span className="font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.5px]">Byg den selv</span>
              <span className="text-[16px] leading-[1.5] text-ink-soft">Byggevejledningen viser trin for trin, hvad du skal bruge, og hvad der sker – ingen teknik, ingen kode.</span>
              <span className={`${btnOutline} mt-auto`}>Åbn byggevejledningen<ArrowIcon size={18} /></span>
            </Link>
          </div>
          <p className="m-0 text-[15px] text-ink-soft">Vil I hellere have det gjort? Vores specialister sætter den op for 5.000 kr. ekskl. moms, skræddersyet til jeres systemer.</p>
        </div>
      </section>
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
        { "@type": "Offer", name: "Abonnement – fra", price: "2495", priceCurrency: "DKK", description: "Fra, pr. måned ekskl. moms" },
        { "@type": "Offer", name: "Udgående kampagneopkald", price: "4", priceCurrency: "DKK", description: "Pr. udgående opkald ekskl. moms, plus 2 kr. pr. påbegyndt samtaleminut" },
        { "@type": "Offer", name: "Opsætning fra Dialogbots specialister", price: "5000", priceCurrency: "DKK", description: "Én gang, ekskl. moms – skræddersyet opsætning og integration til egne systemer. Gør-det-selv-opsætning er med i abonnementet." },
      ] },
    { "@context": "https://schema.org", ...videoStructuredData(SITE_URL) },
  ];
}
