import type { Metadata, Viewport } from "next";
import "./globals.css";
import { SITE_DESCRIPTION, SITE_NAME, SITE_TITLE, SITE_URL } from "@/lib/site";

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

export const viewport: Viewport = { themeColor: "#00362d" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="da">
      <body className="bg-surface text-on-surface text-body-md antialiased">{children}</body>
    </html>
  );
}
