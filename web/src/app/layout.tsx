import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Dialogbot",
  description: "AI-reception, callback og kampagner for danske virksomheder",
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
