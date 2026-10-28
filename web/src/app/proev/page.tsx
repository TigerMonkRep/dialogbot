import type { Metadata } from "next";
import { SiteChrome } from "@/components/site-chrome";
import { ProevChat } from "./proev-chat";

/** Prøv den — Vej A (design-reference/byggevejledning/Proev.dc.html): the chat asks company, line of business and
 *  phone number, then the real demo-call endpoint rings the visitor. The page is a server component for metadata;
 *  the conversation lives in proev-chat.tsx. The floating chat widget is off here: this page IS the chat. */
export const metadata: Metadata = {
  title: "Prøv Dialogbot – snak med den, så ringer den til dig",
  description: "Ingen formular, ingen tilmelding. Fortæl chatten, hvad din virksomhed hedder og hvad I laver – så ringer Dialogbot til dig og tager imod dig som din egen receptionist.",
  alternates: { canonical: "/proev" },
  openGraph: { url: "/proev", title: "Prøv Dialogbot – den ringer til dig | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SiteChrome current="proev" chat={false} bg="bg-panel" compactFooter>
      <div className="max-w-[1180px] w-full mx-auto px-4 sm:px-6 pt-10 sm:pt-12 pb-[72px] flex flex-col gap-10">
        <div className="flex flex-col gap-3.5 max-w-[760px]">
          <span className="eyebrow text-[13px] tracking-[1.5px]">Trin 0 · før du bygger noget</span>
          <h1 className="m-0 font-display font-extrabold text-[clamp(38px,5vw,64px)] leading-[1.02] tracking-[-1.5px]">Snak med den. Så ringer den til dig – som din egen receptionist.</h1>
          <p className="m-0 text-lg leading-[1.55] text-ink-soft max-w-[620px]">Ingen formular, ingen tilmelding. Fortæl chatten, hvad din virksomhed hedder, og hvad I laver. Så ringer Dialogbot til dig og tager imod dig, som var du en kunde.</p>
        </div>
        <ProevChat />
      </div>
    </SiteChrome>
  );
}
