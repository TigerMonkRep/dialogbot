import type { Metadata, Viewport } from "next";
import Script from "next/script";
import "./globals.css";
import { SITE_NAME, SITE_URL } from "@/lib/site";
import { SiteAnalytics } from "@/components/site-analytics";
import { I18nProvider } from "@/i18n/client";
import { DEFAULT_LOCALE, HTML_LANG, OG_LOCALE } from "@/i18n/config";
import { getLocale, getRaw, getT, messagesFor } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const t = await getT("landing");
  const raw = await getRaw();
  const title = t("meta.title");
  const description = t("meta.description");
  return {
    metadataBase: new URL(SITE_URL),
    title: { default: title, template: `%s | ${SITE_NAME}` },
    description,
    applicationName: SITE_NAME,
    keywords: raw<string[]>("landing.meta.keywords"),
    openGraph: { type: "website", locale: OG_LOCALE[locale], siteName: SITE_NAME, url: SITE_URL, title, description },
    twitter: { card: "summary_large_image", title, description },
    verification: process.env.GOOGLE_SITE_VERIFICATION ? { google: process.env.GOOGLE_SITE_VERIFICATION } : undefined,
    appleWebApp: { title: "Dialogbot", capable: true, statusBarStyle: "black-translucent" },
    manifest: "/manifest.webmanifest",
  };
}

export const viewport: Viewport = { themeColor: "#2456F6" };

// Travelpayouts Drive: the partner programme's site script, required by Travelpayouts before the partner dashboard
// (API token, marker) opens for a website project. It only acts on travel content, so it is inert on this site.
// `beforeInteractive` in the root layout puts it in <head>, where Travelpayouts' installation check looks for it.
const TRAVELPAYOUTS_DRIVE = `(function () {
var script = document.createElement("script");
script.async = 1;
script.setAttribute("data-cmp-ab","2");
script.src = 'https://emrldtp.cc/NTk2Mjc3.js?t=596277';
document.head.appendChild(script);
})();`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={HTML_LANG[locale]}>
      <Script id="travelpayouts-drive" strategy="beforeInteractive" data-cmp-ab="2" data-cfasync="false" data-no-defer="1">
        {TRAVELPAYOUTS_DRIVE}
      </Script>
      <body className="bg-paper text-ink text-body-md antialiased">
        <I18nProvider locale={locale} messages={messagesFor(locale)} fallback={messagesFor(DEFAULT_LOCALE)}>
          {children}
          <SiteAnalytics />
        </I18nProvider>
      </body>
    </html>
  );
}
