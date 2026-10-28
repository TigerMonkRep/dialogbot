import Link from "next/link";
import type { Metadata } from "next";
import { EMAIL, PHONE_DISPLAY, PHONE_TEL, SiteChrome } from "@/components/site-chrome";
import { ArrowIcon, CalendarIcon, ChartIcon, ChatIcon, CheckIcon, ChevronIcon, ClockIcon, PhoneIcon, PlayIcon, PlusIcon, SendIcon, SmsIcon } from "@/components/site-icons";
import { SITE_URL } from "@/lib/site";

/** Byggevejledningen — the landing page (design-reference/byggevejledning/Main.dc.html): hero with the "Trin 1 af 3"
 *  card, the 3 steps with parts boxes, result A–D, the six bricks, integrations, the two prices, demo transcript,
 *  FAQ and the dark CTA. "Klar" is only claimed for Google Kalender, Microsoft 365 and SMS/e-mail. */
export const metadata: Metadata = {
  title: "Byg din AI-receptionist i 3 trin – byggevejledning",
  description: "Byggevejledningen til Dialogbot: hvad du skal bruge, hvad den kan, hvad den koster – og de 3 trin til din egen AI-receptionist på dansk. Fra 1.495 kr./md. eller 149 kr. pr. godkendt henvendelse.",
  alternates: { canonical: "/byggevejledning" },
  openGraph: { url: "/byggevejledning", title: "Byg din AI-receptionist i 3 trin | Dialogbot", images: ["/opengraph-image.png"] },
};

const NAV: [string, string][] = [["#trin", "Sådan bygger du"], ["#klodser", "Klodserne"], ["#systemer", "Passer til dit system"], ["#pris", "Pris"], ["#demo", "Hør en demo"]];

const FAQ: [string, string][] = [
  ["Lyder det som en robot?", "Nej. Dialogbot taler naturligt dansk og præsenterer sig altid som en digital receptionist, så kunden ved, hvem de taler med. Hør demoen ovenfor."],
  ["Skal jeg skifte telefonnummer?", "Nej. Du beholder dit nummer og viderestiller det – enten altid, eller kun når du ikke tager den. Vi viser dig hvordan i trin 3."],
  ["Hvad hvis den ikke kan svare?", "Så tager den en besked med navn, nummer og ærinde og sender den til dig med det samme. Den gætter aldrig på priser eller aftaler, I ikke har givet den."],
  ["Er jeg bundet?", "Nej. Fast pris kan opsiges måned til måned, og pr. henvendelse har ingen fast udgift."],
];

const container = "max-w-[1180px] mx-auto px-4 sm:px-6";
const eyebrow = "eyebrow text-[13px] tracking-[1.5px]";
const h2 = "m-0 font-display font-extrabold text-[clamp(32px,3.6vw,46px)] leading-[1.05] tracking-[-1px]";
const btnPrimary = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[17px]";
const btnOutline = "inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-white border-2 border-ink text-ink no-underline font-semibold text-[17px] hover:bg-panel";
const stepNo = "inline-flex w-14 h-14 rounded-[14px] bg-highlight items-center justify-center font-display font-extrabold text-[30px] shrink-0";
const partsBox = "border-[1.5px] border-ink rounded-xl px-3.5 py-3 flex flex-col gap-2";
const tile = "inline-flex w-12 h-12 rounded-xl bg-accent items-center justify-center shrink-0";

function StepCard({ n, title, parts, text, children }: { n: string; title: string; parts: string[]; text: string; children: React.ReactNode }) {
  return (
    <article className="border-2 border-ink rounded-[20px] p-6 flex flex-col gap-[18px] bg-white">
      <div className="flex items-center gap-3.5">
        <span className={stepNo}>{n}</span>
        <h3 className="m-0 font-display font-bold text-[22px] leading-[1.15]">{title}</h3>
      </div>
      <div className="h-[150px] rounded-[14px] bg-panel relative overflow-hidden">{children}</div>
      <div className={partsBox}>
        <span className={eyebrow.replace("text-[13px]", "text-xs")}>Du skal bruge</span>
        <ul className="m-0 p-0 list-none flex flex-col gap-1.5 text-[15px]">
          {parts.map((p) => <li key={p} className="flex gap-2.5"><b className="font-display font-extrabold min-w-7">1×</b>{p}</li>)}
        </ul>
      </div>
      <p className="m-0 text-[15px] leading-normal text-ink-soft">{text}</p>
    </article>
  );
}

function Brick({ icon, title, text, badge }: { icon: React.ReactNode; title: string; text: string; badge?: string }) {
  return (
    <div className="flex flex-col gap-3.5 p-[22px] rounded-2xl border-2 border-ink bg-white">
      <div className="flex items-center justify-between">
        <span className={tile}>{icon}</span>
        {badge && <span className="text-xs font-semibold tracking-[1.5px] uppercase px-2.5 py-1 rounded-full bg-highlight">{badge}</span>}
      </div>
      <span className="font-display font-bold text-xl">{title}</span>
      <span className="text-[15px] leading-normal text-ink-soft">{text}</span>
    </div>
  );
}

function System({ icon, name, status, ready, dark }: { icon: React.ReactNode; name: string; status: string; ready?: boolean; dark?: boolean }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3.5 rounded-[14px] border-2 border-ink bg-white">
      <span className={`inline-flex w-9 h-9 rounded-[10px] items-center justify-center flex-none ${dark ? "bg-ink" : "bg-accent"}`}>{icon}</span>
      <div className="flex flex-col"><span className="font-semibold text-[15px]">{name}</span><span className={`text-xs font-semibold tracking-[1px] uppercase ${ready ? "text-success" : "text-muted"}`}>{status}</span></div>
    </div>
  );
}

function Check() { return <CheckIcon size={20} stroke="#2456F6" className="flex-none" />; }

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

export default function Page() {
  const jsonLd = [
    { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: FAQ.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })) },
    { "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement: [
      { "@type": "ListItem", position: 1, name: "Dialogbot", item: SITE_URL },
      { "@type": "ListItem", position: 2, name: "Byggevejledning", item: `${SITE_URL}/byggevejledning` }] },
  ];
  return (
    <SiteChrome current="byggevejledning" nav={NAV} chatOpen>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />

      {/* HERO */}
      <section id="top" className="bg-panel border-b-2 border-ink">
        <div className={`${container} pt-12 pb-14 sm:pt-16 sm:pb-[72px] flex flex-wrap gap-12 items-center`}>
          <div className="flex-[1_1_420px] min-w-0 flex flex-col gap-6">
            <div className="inline-flex items-center gap-2.5 self-start bg-white border-2 border-ink rounded-full py-1.5 pr-3.5 pl-1.5 text-sm font-semibold">
              <span className="inline-flex w-7 h-7 rounded-full bg-highlight items-center justify-center font-display font-extrabold text-[15px]">3</span>
              <span>trin · ca. 30 minutter · ingen teknik</span>
            </div>
            <h1 className="m-0 font-display font-extrabold text-[clamp(40px,5.2vw,68px)] leading-[1.02] tracking-[-1.5px]">Byg din egen AI-receptionist.<br />Trin for trin.</h1>
            <p className="m-0 text-[19px] leading-[1.55] max-w-[520px] text-ink-soft">Dialogbot tager telefonen, svarer på webchat og booker aftaler for din virksomhed – på dansk, døgnet rundt. Du følger vejledningen, vi sætter klodserne sammen med dig.</p>
            <div className="flex flex-wrap gap-3">
              <Link href="/proev" className={btnPrimary}>Prøv den nu – den ringer til dig<ArrowIcon size={18} /></Link>
              <a href="#demo" className={btnOutline}><PlayIcon size={18} />Hør Dialogbot tage telefonen</a>
            </div>
            <p className="m-0 text-sm text-muted">Fra 1.495 kr./md. eller 149 kr. pr. godkendt henvendelse · ekskl. moms</p>
          </div>

          {/* Hero illustration: a manual step card */}
          <div className="flex-[1_1_380px] min-w-0 flex justify-center">
            <div className="w-full max-w-[460px] bg-white border-2 border-ink rounded-[20px] p-5 sm:p-6 flex flex-col gap-5 shadow-block">
              <div className="flex items-center gap-3.5">
                <span className={stepNo}>1</span>
                <div className="flex flex-col">
                  <span className="eyebrow">Trin 1 af 3</span>
                  <span className="font-display font-bold text-xl">Fortæl os om din virksomhed</span>
                </div>
              </div>
              <div className={partsBox}>
                <span className="eyebrow">Du skal bruge</span>
                <div className="flex flex-wrap gap-2">
                  {["telefonnummer", "åbningstider", "hvad I laver"].map((p) => (
                    <span key={p} className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-panel text-sm font-medium"><b className="font-display font-extrabold">1×</b>{p}</span>
                  ))}
                </div>
              </div>
              <div className="relative h-[200px] rounded-[14px] bg-panel overflow-hidden" aria-hidden>
                <div className="absolute left-[8%] bottom-0 w-[120px] h-[170px] border-[3px] border-b-0 border-ink rounded-t-[22px] bg-white" />
                <div className="absolute left-[calc(8%+30px)] bottom-[146px] w-[60px] h-1.5 rounded-[3px] bg-ink" />
                <div className="absolute left-[calc(8%+20px)] bottom-[92px] w-20 h-10 rounded-[10px] bg-accent" />
                <div className="absolute left-[calc(8%+20px)] bottom-11 w-20 h-10 rounded-[10px] bg-highlight" />
                <div className="absolute left-[calc(8%+20px)] -bottom-1 w-20 h-10 rounded-t-[10px] bg-ink" />
                <svg className="absolute left-[calc(8%+140px)] top-[34px] hidden min-[400px]:block" width="64" height="28" viewBox="0 0 64 28" fill="none" stroke="#14213D" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M60 14H6M14 4 4 14l10 10" /></svg>
                <div className="absolute right-[6%] top-[22px] w-[120px] h-[52px] border-[3px] border-ink rounded-[14px] bg-white hidden min-[400px]:flex items-center justify-center font-display font-bold text-[15px]">Man–fre 8–17</div>
                <div className="absolute right-[calc(6%+100px)] top-[74px] w-0 h-0 border-l-[10px] border-r-[10px] border-t-[12px] border-l-transparent border-r-transparent border-t-ink hidden min-[400px]:block" />
                <div className="absolute right-[6%] top-[104px] w-[120px] h-[52px] border-[3px] border-ink rounded-[14px] bg-white hidden min-[400px]:flex items-center justify-center font-display font-bold text-[15px]">+45 …</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* STEPS */}
      <section id="trin" className="bg-white scroll-mt-6">
        <div className={`${container} py-16 sm:py-20 flex flex-col gap-10`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>Byggevejledning</span>
            <h2 className={h2}>Sådan bygger du den – i 3 trin</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">Ingen apps at installere, ingen kode. Hvert trin viser præcis, hvad du skal bruge, og hvad der sker.</p>
          </div>
          <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr))]">
            <StepCard n="1" title="Fortæl os om din virksomhed" parts={["dit telefonnummer", "åbningstider", "det, I oftest bliver spurgt om"]} text="Udfyld en kort formular – eller fortæl det til os i telefonen. Det tager 5 minutter.">
              <div aria-hidden>
                <div className="absolute left-6 top-[22px] w-[150px] h-[106px] border-[3px] border-ink rounded-[14px] bg-white flex flex-col gap-2.5 p-3.5">
                  <div className="h-2.5 rounded-[5px] bg-ink w-[70%]" /><div className="h-2.5 rounded-[5px] bg-line w-[90%]" /><div className="h-2.5 rounded-[5px] bg-line w-[55%]" />
                </div>
                <svg className="absolute left-[190px] top-[62px]" width="52" height="24" viewBox="0 0 52 24" fill="none" stroke="#14213D" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M4 12h42M38 4l8 8-8 8" /></svg>
                <div className="absolute right-6 top-10 w-[70px] h-[70px] rounded-2xl bg-accent flex items-center justify-center"><ChatIcon size={34} stroke="#FFFFFF" /></div>
              </div>
            </StepCard>
            <StepCard n="2" title="Vi bygger og tester sammen" parts={["videomøde med os", "prøveopkald til din nye receptionist"]} text="Vi sætter stemme, svar og booking op, mens du ser på. Du ringer selv og hører, at det virker.">
              <div aria-hidden>
                <div className="absolute left-[34px] top-[50px] w-[90px] h-[50px] rounded-xl bg-accent" />
                <div className="absolute left-[124px] top-[50px] w-4 h-[50px] bg-accent rounded-r-lg" />
                <svg className="absolute left-[150px] top-[62px]" width="40" height="26" viewBox="0 0 40 26" fill="none" stroke="#14213D" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M36 13H4M12 5 4 13l8 8" /></svg>
                <div className="absolute left-[200px] top-[50px] w-[90px] h-[50px] rounded-xl bg-highlight" />
                <div className="absolute left-[200px] top-[62px] w-3.5 h-[26px] bg-panel rounded-r-md" />
                <div className="absolute right-5 bottom-3.5 px-2.5 py-1.5 rounded-full bg-white border-2 border-ink font-display font-bold text-[13px]">ca. 30 min</div>
              </div>
            </StepCard>
            <StepCard n="3" title="Tænd – og gå tilbage til arbejdet" parts={["viderestilling af dit nummer (vi viser hvordan)"]} text="Fra nu af får du en SMS eller e-mail, hver gang der er en aftale eller en besked til dig.">
              <div aria-hidden>
                <div className="absolute left-[30px] top-[30px] w-[120px] h-14 rounded-full bg-accent flex items-center justify-end p-1.5"><div className="w-11 h-11 rounded-full bg-white" /></div>
                <div className="absolute left-9 top-24 font-display font-bold text-sm">Dialogbot: TIL</div>
                <div className="absolute right-7 top-[30px] flex flex-col gap-2">
                  <div className="flex items-center gap-2 px-3 py-2 rounded-[10px] bg-white border-2 border-ink text-[13px] font-semibold"><PhoneIcon size={16} width={2.4} />Opkald besvaret</div>
                  <div className="flex items-center gap-2 px-3 py-2 rounded-[10px] bg-white border-2 border-ink text-[13px] font-semibold"><CalendarIcon size={16} width={2.4} />Aftale booket</div>
                </div>
              </div>
            </StepCard>
          </div>
        </div>
      </section>

      {/* RESULT */}
      <section className="bg-panel border-y-2 border-ink">
        <div className={`${container} py-16 sm:py-[72px] flex flex-col gap-8`}>
          <div className="flex flex-wrap items-end gap-x-10 gap-y-4">
            <div className="flex flex-col gap-3 max-w-[560px] flex-[1_1_360px]">
              <span className={eyebrow}>Færdigt resultat</span>
              <h2 className={h2}>Sådan ser et opkald ud, når den er bygget</h2>
            </div>
            <p className="m-0 text-base leading-[1.55] text-ink-soft flex-[1_1_320px] max-w-[440px]">Hvert opkald følger den samme simple linje. Du ser alle henvendelser i ét overblik og kan altid rette, hvad Dialogbot må sige.</p>
          </div>
          <ol className="m-0 p-0 list-none flex flex-wrap gap-4 items-stretch">
            {([
              ["A", "Kunden ringer", "Også uden for åbningstid, når du er på en opgave eller har kunder i butikken."],
              ["B", "Dialogbot svarer", "På dansk, med jeres navn, priser og åbningstider – og uden at lade kunden vente."],
              ["C", "Booker eller tager besked", "Ledige tider i din kalender, eller en besked med navn, nummer og ærinde."],
              ["D", "Du får besked", "SMS eller e-mail med det samme. Du ringer tilbage, når det passer dig."],
            ] as [string, string, string][]).map(([l, t, d], i) => {
              const dark = i === 3;
              return (
                <li key={l} className={`flex-[1_1_220px] flex flex-col gap-3 p-5 rounded-2xl border-2 border-ink ${dark ? "bg-ink text-white" : "bg-white"}`}>
                  <span className="inline-flex w-10 h-10 rounded-[10px] bg-highlight text-ink items-center justify-center font-display font-extrabold text-xl">{l}</span>
                  <span className="font-display font-bold text-lg">{t}</span>
                  <span className={`text-sm leading-normal ${dark ? "text-line" : "text-ink-soft"}`}>{d}</span>
                </li>
              );
            })}
          </ol>
        </div>
      </section>

      {/* PARTS */}
      <section id="klodser" className="bg-white scroll-mt-6">
        <div className={`${container} py-16 sm:py-20 flex flex-col gap-10`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>Klodserne i sættet</span>
            <h2 className={h2}>Vælg de klodser, du har brug for</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">Start med telefonen. Klik flere på, efterhånden som du får brug for dem – de passer sammen.</p>
          </div>
          <div className="grid gap-5 [grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr))]">
            <Brick icon={<PhoneIcon size={24} stroke="#FFFFFF" />} title="Telefon" badge="Start her" text="Besvarer alle opkald på dansk med jeres navn. Stiller videre til dig, når det haster." />
            <Brick icon={<ChatIcon size={24} stroke="#FFFFFF" width={2.2} />} title="Webchat" text="En lille chat på din hjemmeside, der svarer med det samme og samler kontaktoplysninger." />
            <Brick icon={<CalendarIcon size={24} stroke="#FFFFFF" />} title="Booking" text="Finder ledige tider i din kalender og bekræfter aftalen til kunden på SMS." />
            <Brick icon={<SmsIcon size={24} stroke="#FFFFFF" />} title="SMS-svar" text="Ubesvarede opkald får en SMS med det samme, så kunden ved, I vender tilbage." />
            <Brick icon={<SendIcon size={24} stroke="#FFFFFF" />} title="Kampagner" text="Ring eller skriv til dine eksisterende kunder – fx om tid til service eller nyt tilbud. Du godkender altid først." />
            <Brick icon={<ChartIcon size={24} stroke="#FFFFFF" />} title="Overblik" text="Alle opkald, chats og aftaler ét sted. Se hvad der blev sagt, og hvad der mangler svar." />
          </div>
        </div>
      </section>

      {/* INTEGRATIONS */}
      <section id="systemer" className="bg-white border-t-2 border-ink scroll-mt-6">
        <div className={`${container} py-16 sm:py-[72px] flex flex-wrap gap-10 items-start`}>
          <div className="flex-[1_1_320px] flex flex-col gap-3 max-w-[460px]">
            <span className={eyebrow}>Passer til dit system</span>
            <h2 className={h2}>Klodserne passer på det, I allerede bruger</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">Kalender, CRM eller bookingsystem – Dialogbot skriver aftaler og beskeder derhen, hvor I plejer at kigge. Bruger I noget, vi ikke har koblet på endnu, siger vi det ærligt og bygger det ind under opsætningen.</p>
          </div>
          <div className="flex-[1_1_460px] flex flex-col gap-3.5">
            <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(200px,100%),1fr))]">
              <System icon={<CalendarIcon size={18} stroke="#FFFFFF" />} name="Google Kalender" status="Klar" ready />
              <System icon={<CalendarIcon size={18} stroke="#FFFFFF" />} name="Microsoft 365 / Outlook" status="Klar" ready />
              <System icon={<ChartIcon size={18} stroke="#FFFFFF" />} name="Dit CRM" status="Kobles på i opsætningen" dark />
              <System icon={<ClockIcon size={18} stroke="#FFFFFF" />} name="Dit bookingsystem" status="Kobles på i opsætningen" dark />
              <System icon={<SmsIcon size={18} stroke="#FFFFFF" />} name="SMS og e-mail" status="Klar · virker altid" ready dark />
              <Link href="/proev" className="flex items-center gap-3 px-4 py-3.5 rounded-[14px] border-2 border-dashed border-ink bg-panel text-ink no-underline hover:bg-panel-deep">
                <span className="inline-flex w-9 h-9 rounded-[10px] bg-white border-2 border-ink items-center justify-center flex-none"><PlusIcon size={18} /></span>
                <span className="flex flex-col"><span className="font-semibold text-[15px]">Noget andet?</span><span className="text-xs text-muted">Spørg chatten – den noterer det</span></span>
              </Link>
            </div>
            <p className="m-0 text-[13px] leading-normal text-muted">«Klar» betyder, at det virker i dag. Alt andet kobler vi på sammen med dig – og indtil det virker, får du altid aftaler og beskeder på SMS og e-mail.</p>
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section id="pris" className="bg-panel border-y-2 border-ink scroll-mt-6">
        <div className={`${container} py-16 sm:py-20 flex flex-col gap-10`}>
          <div className="flex flex-col gap-3 max-w-[640px]">
            <span className={eyebrow}>Pris</span>
            <h2 className={h2}>Vælg dit sæt. To priser, ingen overraskelser.</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">Alle priser er ekskl. moms. Opsætningen gør vi sammen på ca. 30 minutter – den koster 0 kr.</p>
          </div>
          <div className="grid gap-6 max-w-[860px] [grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr))]">
            <article className="flex flex-col gap-5 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink shadow-block">
              <div className="flex items-center gap-3">
                <span className="inline-flex w-11 h-11 rounded-xl bg-highlight items-center justify-center font-display font-extrabold text-[22px]">A</span>
                <span className="font-display font-bold text-xl">Fast pris</span>
              </div>
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="font-display font-extrabold text-[52px] tracking-[-1.5px] leading-none">1.495</span>
                <span className="text-lg font-semibold text-ink-soft">kr./md.</span>
              </div>
              <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-[15px]">
                <li className="flex gap-2.5 items-start"><Check />Ubegrænset antal opkald og chats</li>
                <li className="flex gap-2.5 items-start"><Check />Alle klodser inkluderet</li>
                <li className="flex gap-2.5 items-start"><Check />Opsigelse måned til måned</li>
              </ul>
              <a href="#kontakt" className={`${btnPrimary} text-base`}>Vælg fast pris</a>
              <span className="text-[13px] text-muted">Bedst, hvis I får mere end ca. 10 henvendelser om måneden.</span>
            </article>
            <article className="flex flex-col gap-5 p-6 sm:p-7 rounded-[20px] bg-white border-2 border-ink">
              <div className="flex items-center gap-3">
                <span className="inline-flex w-11 h-11 rounded-xl bg-highlight items-center justify-center font-display font-extrabold text-[22px]">B</span>
                <span className="font-display font-bold text-xl">Pr. henvendelse</span>
              </div>
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="font-display font-extrabold text-[52px] tracking-[-1.5px] leading-none">149</span>
                <span className="text-lg font-semibold text-ink-soft">kr. pr. godkendt henvendelse</span>
              </div>
              <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-[15px]">
                <li className="flex gap-2.5 items-start"><Check />Ingen fast månedspris</li>
                <li className="flex gap-2.5 items-start"><Check />Du godkender hver henvendelse, før den tæller</li>
                <li className="flex gap-2.5 items-start"><Check />Skift til fast pris når som helst</li>
              </ul>
              <a href="#kontakt" className={`${btnOutline} text-base`}>Vælg pr. henvendelse</a>
              <span className="text-[13px] text-muted">Bedst, hvis I vil prøve det af uden fast udgift.</span>
            </article>
          </div>
        </div>
      </section>

      {/* DEMO */}
      <section id="demo" className="bg-white scroll-mt-6">
        <div className={`${container} py-16 sm:py-20 flex flex-wrap gap-12 items-center`}>
          <div className="flex-[1_1_380px] min-w-0 flex flex-col gap-4">
            <span className={eyebrow}>Demo</span>
            <h2 className={h2}>Hør Dialogbot tage telefonen</h2>
            <p className="m-0 text-[17px] leading-[1.55] text-ink-soft">Sådan lyder et opkald til en tømrer. Prøv den selv – så ringer den til dig og tager imod dig som en kunde.</p>
            <Link href="/proev" className={`${btnPrimary} self-start min-h-14 px-6`}><PlayIcon size={20} />Prøv den – den ringer til dig</Link>
          </div>
          <div className="flex-[1_1_380px] min-w-0 flex flex-col gap-3 p-5 sm:p-6 rounded-[20px] bg-panel border-2 border-ink">
            <div className="flex items-center justify-between gap-3 text-[13px] font-semibold text-muted tracking-[1px] uppercase"><span>Opkald · Tømrerfirma (eksempel)</span><span>0:48</span></div>
            <Bubble who="D">Du har ringet til Nørgaard Tømrer, det er Dialogbot. Hvad kan jeg hjælpe med?</Bubble>
            <Bubble who="K">Hej, jeg skal have skiftet et vindue. Kan I komme og kigge i næste uge?</Bubble>
            <Bubble who="D">Det kan vi godt. Der er ledigt tirsdag kl. 9 eller torsdag kl. 14. Hvad passer bedst?</Bubble>
            <div className="flex items-center gap-2 mt-1.5 px-3 py-2.5 rounded-[10px] bg-white border-[1.5px] border-ink text-[13px] font-semibold"><CheckIcon size={16} stroke="#2456F6" />Aftale booket: tirsdag kl. 9 · SMS sendt til dig og kunden</div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="bg-white border-t-2 border-ink">
        <div className={`${container} py-16 sm:py-[72px] flex flex-wrap gap-10`}>
          <div className="flex-[1_1_300px] flex flex-col gap-3">
            <span className={eyebrow}>Spørgsmål</span>
            <h2 className="m-0 font-display font-extrabold text-[clamp(28px,3vw,38px)] leading-[1.1] tracking-[-0.8px]">Det, de fleste spørger om først</h2>
          </div>
          <div className="flex-[2_1_460px] flex flex-col border-t-2 border-ink">
            {FAQ.map(([q, a]) => (
              <details key={q} className="faq border-b-2 border-ink">
                <summary className="flex items-center justify-between gap-4 py-5 font-display font-bold text-[19px] min-h-11">{q}<ChevronIcon size={22} className="chev flex-none" /></summary>
                <p className="m-0 mb-5 text-base leading-[1.55] text-ink-soft max-w-[620px]">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section id="kontakt" className="bg-ink text-white scroll-mt-6">
        <div className={`${container} py-16 sm:py-20 flex flex-wrap gap-10 items-center justify-between`}>
          <div className="flex-[1_1_420px] flex flex-col gap-3.5">
            <h2 className="m-0 font-display font-extrabold text-[clamp(32px,4vw,52px)] leading-[1.03] tracking-[-1.2px]">Klar til trin 1?</h2>
            <p className="m-0 text-lg leading-[1.55] text-line max-w-[520px]">Ring til os, så bygger vi den sammen. Eller skriv, så ringer vi tilbage inden for åbningstiden.</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <a href={PHONE_TEL} className="inline-flex items-center gap-2.5 min-h-14 px-6 rounded-[14px] bg-highlight hover:bg-highlight-deep text-ink no-underline font-display font-bold text-lg"><PhoneIcon size={20} width={2.4} />{PHONE_DISPLAY}</a>
            <a href={`mailto:${EMAIL}`} className="inline-flex items-center gap-2.5 min-h-14 px-6 rounded-[14px] border-2 border-white text-white no-underline font-semibold text-[17px] hover:bg-white/10">Skriv til os</a>
          </div>
        </div>
      </section>
    </SiteChrome>
  );
}
