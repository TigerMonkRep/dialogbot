import type { Metadata } from "next";
import { SiteChrome } from "@/components/site-chrome";
import { InstallCapture } from "@/components/install-app";
import { ProevChat } from "./proev-chat";
import { getT } from "@/i18n/server";

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

export default async function Page() {
  const t = await getT("site");
  return (
    <SiteChrome current="proev" chat={false} bg="bg-panel" compactFooter>
      <div className="max-w-[1180px] w-full mx-auto px-4 sm:px-6 pt-10 sm:pt-12 pb-[72px] flex flex-col gap-10">
        <div className="flex flex-col gap-3.5 max-w-[760px]">
          <span className="eyebrow text-[13px] tracking-[1.5px]">{t("proev.eyebrow")}</span>
          <h1 className="m-0 font-display font-extrabold text-[clamp(38px,5vw,64px)] leading-[1.02] tracking-[-1.5px]">{t("proev.title")}</h1>
          <p className="m-0 text-lg leading-[1.55] text-ink-soft max-w-[620px]">{t("proev.lead")}</p>
        </div>
        <ProevChat />
      </div>
      {/* Catches the install prompt on load, so the install step after the demo call is one tap. */}
      <InstallCapture />
    </SiteChrome>
  );
}
