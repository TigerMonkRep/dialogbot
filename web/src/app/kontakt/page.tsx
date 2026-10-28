import type { Metadata } from "next";
import Link from "next/link";
import { COMPANY } from "@/components/legal-page";
import { HOURS, PHONE_DISPLAY, PHONE_INTL, PHONE_TEL, SiteChrome } from "@/components/site-chrome";
import { PhoneIcon, SmsIcon } from "@/components/site-icons";

export const metadata: Metadata = {
  title: "Kontakt og support | Dialogbot",
  description: "Sådan kontakter du Dialogbot om din konto, betaling eller dine data. Ring på 93 70 34 33 eller skriv til info@dialogbot.dk.",
  alternates: { canonical: "/kontakt" },
};

/** Kontakt — on the shared public chrome. Nummer, overskrift, tekst; one action (ring) first. */
export default function ContactPage() {
  const sections: [string, React.ReactNode][] = [
    ["E-mail", <p key="e">Skriv til <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>. Skriv gerne navnet på din virksomhed og den e-mail, du er logget ind med, så vi hurtigt kan finde din konto. Vi svarer på hverdage, som regel inden for én arbejdsdag.</p>],
    ["Telefon", <p key="t">Ring på <a href={PHONE_TEL}>{PHONE_INTL}</a> – {HOURS.toLowerCase()}.</p>],
    ["Post", <p key="p">{COMPANY.name}, CVR-nr. {COMPANY.cvr}, {COMPANY.address}.</p>],
    ["Betaling og fakturaer", <p key="b">Spørgsmål om en betaling eller en faktura fra Dialogbot: skriv til os, før du gør indsigelse hos din bank, så finder vi en løsning hurtigst. Dine fakturaer kan du altid se under Fakturering, når du er logget ind.</p>],
    ["Er du logget ind?", <p key="h">Så finder du svar på de fleste spørgsmål under Hjælp i appen, og du kan se din opsætning, dine samtaler og henvendelser direkte.</p>],
    ["Ambassadører", <p key="a">Spørgsmål om bonus, udbetalinger eller reglerne: skriv til samme adresse. Læs om programmet på <Link href="/ambassador/bliv">dialogbot.dk/ambassador/bliv</Link>.</p>],
    ["Persondata", <p key="d">Vil du have indsigt i, rettet eller slettet dine oplysninger, så læs <Link href="/privatliv">privatlivspolitikken</Link> og skriv til os.</p>],
  ];
  return (
    <SiteChrome>
      <section className="bg-panel border-b-2 border-ink">
        <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-12 sm:py-16 flex flex-wrap gap-10 items-start">
          <div className="flex-[1_1_420px] flex flex-col gap-4">
            <span className="eyebrow text-[13px] tracking-[1.5px]">Kontakt</span>
            <h1 className="m-0 font-display font-extrabold text-[clamp(34px,4.6vw,60px)] leading-[1.03] tracking-[-1.4px]">Kontakt og support</h1>
            <p className="m-0 text-lg leading-[1.55] text-ink-soft max-w-[620px]">Har du spørgsmål til din konto, en faktura, din assistent eller dine data, så ring eller skriv. Vi svarer på hverdage, som regel inden for én arbejdsdag.</p>
            <p className="m-0 text-sm text-muted">Opdateret 28. oktober 2026.</p>
          </div>
          <div className="flex-[1_1_300px] max-w-[460px] flex flex-col gap-3">
            <a href={PHONE_TEL} className="flex items-center gap-3.5 p-5 rounded-[20px] bg-white border-2 border-ink shadow-block text-ink no-underline">
              <span className="inline-flex w-12 h-12 rounded-xl bg-accent items-center justify-center shrink-0"><PhoneIcon size={24} stroke="#FFFFFF" /></span>
              <span className="flex flex-col"><span className="eyebrow">Ring · {HOURS}</span><span className="font-display font-extrabold text-2xl tracking-[-0.5px]">{PHONE_DISPLAY}</span></span>
            </a>
            <a href={`mailto:${COMPANY.email}`} className="flex items-center gap-3.5 p-5 rounded-[20px] bg-white border-2 border-ink text-ink no-underline hover:bg-panel">
              <span className="inline-flex w-12 h-12 rounded-xl bg-ink items-center justify-center shrink-0"><SmsIcon size={24} stroke="#FFFFFF" /></span>
              <span className="flex flex-col"><span className="eyebrow">Skriv</span><span className="font-display font-bold text-xl">{COMPANY.email}</span></span>
            </a>
          </div>
        </div>
      </section>
      <div className="max-w-[880px] mx-auto px-4 sm:px-6 py-12 sm:py-16 flex flex-col gap-5 w-full">
        {sections.map(([h, body], i) => (
          <section key={h} className="bg-white rounded-[20px] border-2 border-ink p-5 sm:p-6 flex gap-4">
            <span className="hidden sm:inline-flex w-10 h-10 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-xl shrink-0" aria-hidden>{i + 1}</span>
            <div className="min-w-0 flex-1 flex flex-col gap-2">
              <h2 className="m-0 font-display font-bold text-xl">{h}</h2>
              <div className="text-[15px] leading-normal text-ink-soft [&_a]:underline [&_a]:underline-offset-4 [&_a]:text-accent [&_p]:m-0">{body}</div>
            </div>
          </section>
        ))}
        <p className="m-0 text-sm text-muted">{COMPANY.name} · CVR-nr. {COMPANY.cvr} · {COMPANY.address}</p>
      </div>
    </SiteChrome>
  );
}
