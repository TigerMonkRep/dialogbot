import type { Metadata, Viewport } from "next";
import "./globals.css";
import { SITE_DESCRIPTION, SITE_NAME, SITE_TITLE, SITE_URL } from "@/lib/site";
import { SiteAnalytics } from "@/components/site-analytics";
import { I18nProvider } from "@/i18n/client";
import { DEFAULT_LOCALE, HTML_LANG } from "@/i18n/config";
import { getLocale, messagesFor } from "@/i18n/server";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: SITE_TITLE, template: `%s | ${SITE_NAME}` },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  keywords: ["Dialogbot", "AI-receptionist", "AI receptionist", "AI-telefonsvarer", "AI telefon", "AI-telefonassistent",
    "chatbot", "chatbot til hjemmeside", "telefonpasning", "digital receptionist", "telefonsvarer til virksomheder"],
  openGraph: { type: "website", locale: "da_DK", siteName: SITE_NAME, url: SITE_URL, title: SITE_TITLE, description: SITE_DESCRIPTION },
  twitter: { card: "summary_large_image", title: SITE_TITLE, description: SITE_DESCRIPTION },
  verification: process.env.GOOGLE_SITE_VERIFICATION ? { google: process.env.GOOGLE_SITE_VERIFICATION } : undefined,
  appleWebApp: { title: "Dialogbot", capable: true, statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = { themeColor: "#2456F6" };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={HTML_LANG[locale]}>
      <body className="bg-paper text-ink text-body-md antialiased">
        <I18nProvider locale={locale} messages={messagesFor(locale)} fallback={messagesFor(DEFAULT_LOCALE)}>
          {children}
        </I18nProvider>
        <SiteAnalytics />
      </body>
    </html>
  );
}
