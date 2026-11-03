import type { Metadata, Viewport } from "next";
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
  };
}

export const viewport: Viewport = { themeColor: "#2456F6" };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={HTML_LANG[locale]}>
      <body className="bg-paper text-ink text-body-md antialiased">
        <I18nProvider locale={locale} messages={messagesFor(locale)} fallback={messagesFor(DEFAULT_LOCALE)}>
          {children}
          <SiteAnalytics />
        </I18nProvider>
      </body>
    </html>
  );
}
