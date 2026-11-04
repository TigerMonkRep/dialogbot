import type { Metadata, Viewport } from "next";

/** Everything under /privat (the landing page, the funnel and the app) is Dialogbot Privat: its own manifest (start_url
 *  /privat/dag) and the orange home-screen icon, so «Føj til hjemmeskærm» from any Privat page gives the Privat app. */
export const viewport: Viewport = { themeColor: "#E0521A" };

export const metadata: Metadata = {
  manifest: "/privat/manifest.webmanifest",
  icons: { apple: "/icons/privat-apple-icon-180.png" },
  appleWebApp: { title: "Dialogbot", capable: true, statusBarStyle: "default" },
};

export default function PrivatLayout({ children }: { children: React.ReactNode }) {
  return children;
}
