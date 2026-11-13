import type { Metadata } from "next";
import { SiteChrome } from "@/components/site-chrome";
import { InstallCapture } from "@/components/install-app";
import { ProevChat } from "./proev-chat";
import { getLocale, getT } from "@/i18n/server";
import { phoneFor } from "@/lib/contact";
import { PhoneIcon } from "@/components/site-icons";

/** Prøv den — Vej A (design-reference/byggevejledning/Proev.dc.html): the chat asks company, line of business and
 *  phone number, then the real demo-call endpoint rings the visitor. The page is a server component for metadata;
 *  the conversation lives in proev-chat.tsx. The floating chat widget is off here: this page IS the chat. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("site");
  return {
    title: t("proev.meta.title"),
    description: t("proev.meta.description"),
    alternates: { canonical: "/proev" },
    openGraph: { url: "/proev", title: t("proev.meta.ogTitle"), images: ["/opengraph-image.png"] },
  };
}

/** The US edition has no callback: the visitor rings the demo line and Dialogbot's own assistant answers in English.
 *  (A call the visitor places needs no consent box and no SMS code; a call we place to a US number would.) The
 *  texts are English only because this block exists on /us only. */
function DemoLine({ display, tel }: { display: string; tel: string }) {
  return (
    <section className="max-w-[760px] flex flex-col gap-5 p-6 sm:p-8 rounded-[24px] bg-white border-2 border-ink shadow-block">
      <h2 className="m-0 font-display font-extrabold text-[clamp(26px,3.2vw,36px)] leading-[1.08] tracking-[-0.8px]">Call the demo line and hear it answer</h2>
      <p className="m-0 text-lg leading-[1.55] text-ink-soft">Our own AI receptionist picks up, day and night. Ask it what you would ask a receptionist: what Dialogbot does, what it costs, how setup works. It takes about 90 seconds, and there is no signup.</p>
      <a href={tel} className="self-start inline-flex items-center gap-3 min-h-14 px-6 rounded-[14px] bg-accent hover:bg-accent-deep text-white no-underline font-display font-bold text-2xl tabular-nums"><PhoneIcon size={24} stroke="#FFFFFF" />{display}</a>
      <p className="m-0 text-sm text-muted">You are speaking with a digital assistant, and the call is transcribed.</p>
    </section>
  );
}

export default async function Page() {
  const t = await getT("site");
  const ph = phoneFor(await getLocale());
  const usLine = ph.local && ph.tel.startsWith("tel:+1");
  return (
    <SiteChrome current="proev" chat={false} bg="bg-panel" compactFooter>
      <div className="max-w-[1180px] w-full mx-auto px-4 sm:px-6 pt-10 sm:pt-12 pb-[72px] flex flex-col gap-10">
        <div className="flex flex-col gap-3.5 max-w-[760px]">
          <span className="eyebrow text-[13px] tracking-[1.5px]">{t("proev.eyebrow")}</span>
          <h1 className="m-0 font-display font-extrabold text-[clamp(38px,5vw,64px)] leading-[1.02] tracking-[-1.5px]">{usLine ? "Call it. Hear how your phone could be answered." : t("proev.title")}</h1>
          <p className="m-0 text-lg leading-[1.55] text-ink-soft max-w-[620px]">{usLine ? "No form and no signup. Call our demo line and talk to the same AI receptionist that would answer for your business." : t("proev.lead")}</p>
        </div>
        {usLine ? <DemoLine display={ph.display} tel={ph.tel} /> : <ProevChat />}
      </div>
      {/* Catches the install prompt on load, so the install step after the demo call is one tap. */}
      <InstallCapture />
    </SiteChrome>
  );
}
