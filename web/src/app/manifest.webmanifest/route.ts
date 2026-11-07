import type { MetadataRoute } from "next";
import { getLocale, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";

/** Web app manifest for the business app ("Føj til hjemmeskærm" → /app, the blue mark). Served from a route rather
 *  than the manifest.ts convention, so the /privat segment can point at its own manifest through metadata – a
 *  file-based root manifest would override that on every page.
 *
 *  id/scope /app/: the installed app stays inside the logged-in app (the marketing pages open in the browser), and
 *  the service worker public/sw-app.js has the same scope. Splash: white with the blue icon (background_color is the
 *  splash, the icon's own surface is the blue). Language follows the locale cookie, like Privat. */
async function manifest(): Promise<MetadataRoute.Manifest> {
  const locale = await getLocale();
  const t = await getT("common");
  const icon = { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" };
  return {
    id: "/app/",
    name: "Dialogbot",
    short_name: "Dialogbot",
    description: t("pwa.manifestErhverv"),
    lang: HTML_LANG[locale],
    start_url: "/app",
    scope: "/app/",
    display: "standalone",
    display_override: ["standalone"],
    orientation: "portrait",
    background_color: "#FFFFFF",
    theme_color: "#2456F6",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: t("pwa.shortcuts.calls"), url: "/app/opkald", icons: [icon] },
      { name: t("pwa.shortcuts.appointments"), url: "/app/aftaler", icons: [icon] },
      { name: t("pwa.shortcuts.campaigns"), url: "/app/kampagner", icons: [icon] },
    ],
    screenshots: [
      { src: "/screenshots/erhverv-today-narrow.png", sizes: "390x844", type: "image/png", form_factor: "narrow", label: t("pwa.screens.erhvervToday") },
      { src: "/screenshots/erhverv-install-narrow.png", sizes: "390x844", type: "image/png", form_factor: "narrow", label: t("pwa.screens.erhvervInstall") },
      { src: "/screenshots/erhverv-today-wide.png", sizes: "1280x800", type: "image/png", form_factor: "wide", label: t("pwa.screens.erhvervToday") },
    ],
  };
}

export async function GET() {
  return Response.json(await manifest(), { headers: { "content-type": "application/manifest+json", "cache-control": "public, max-age=3600" } });
}
