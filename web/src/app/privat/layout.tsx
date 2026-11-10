import type { Metadata, Viewport } from "next";
import { InstallCapture } from "@/components/install-app";
import { StandaloneChrome } from "@/components/standalone";

/** Everything under /privat (the landing page, the funnel and the app) is Dialogbot Privat: its own manifest (start_url
 *  /privat/dag) and the orange home-screen icon, so «Føj til hjemmeskærm» from any Privat page gives the Privat app. */
export const viewport: Viewport = { themeColor: "#C4461A", viewportFit: "cover" };

export const metadata: Metadata = {
  manifest: "/privat/manifest.webmanifest",
  icons: { apple: "/icons/privat-apple-icon-180.png" },
  appleWebApp: { title: "Dialogbot", capable: true, statusBarStyle: "default" },
};

export default function PrivatLayout({ children }: { children: React.ReactNode }) {
  // InstallCapture catches the browser's install prompt early, so a later «Download app» (Konto, Min dag) is one tap.
  // StandaloneChrome marks the installed app (scope /privat/ also covers the landing and the funnel), so globals.css
  // can hide the public header/footer there.
  return <>{children}<InstallCapture /><StandaloneChrome /></>;
}
