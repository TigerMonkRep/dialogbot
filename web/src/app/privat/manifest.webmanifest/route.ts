import { getLocale, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";

/** Separate web app manifest for Dialogbot Privat. The root manifest (src/app/manifest.ts) stays the business app's
 *  (start_url /app); the /privat pages link this one instead, so «Føj til hjemmeskærm» from Privat opens Min dag and the
 *  home-screen app (needed for push on iPhone) stays inside /privat/. */
export async function GET() {
  const t = await getT("privat");
  const c = await getT("common");
  const locale = await getLocale();
  const icon = { src: "/icons/privat-icon-192.png", sizes: "192x192", type: "image/png" };
  return Response.json({
    id: "/privat/",
    name: "Dialogbot Privat",
    short_name: "Dialogbot",
    description: t("meta.landingDescription"),
    lang: HTML_LANG[locale],
    start_url: "/privat/dag",
    scope: "/privat/",
    display: "standalone",
    display_override: ["standalone"],
    orientation: "portrait",
    // Splash: cream paper with the orange icon (the icon's own surface is the orange).
    background_color: "#FFFBF5",
    theme_color: "#E0521A",
    icons: [  // the orange Privat mark – opaque, so no launcher paints the corners black
      { src: "/icons/privat-icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/privat-icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/privat-icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    // Long-press shortcuts: Min dag, a new task (the conversation is where tasks are made) and Opgaver. There is no
    // separate «Lister» route – lists live inside Opgaver.
    shortcuts: [
      { name: c("pwa.shortcuts.day"), url: "/privat/dag", icons: [icon] },
      { name: c("pwa.shortcuts.newTask"), url: "/privat/samtale", icons: [icon] },
      { name: c("pwa.shortcuts.tasks"), url: "/privat/opgaver", icons: [icon] },
    ],
    screenshots: [
      { src: "/screenshots/privat-day-narrow.png", sizes: "390x844", type: "image/png", form_factor: "narrow", label: c("pwa.screens.privatDay") },
      { src: "/screenshots/privat-install-narrow.png", sizes: "390x844", type: "image/png", form_factor: "narrow", label: c("pwa.screens.privatInstall") },
      { src: "/screenshots/privat-day-wide.png", sizes: "1280x800", type: "image/png", form_factor: "wide", label: c("pwa.screens.privatDay") },
    ],
  }, { headers: { "content-type": "application/manifest+json", "cache-control": "public, max-age=3600" } });
}
