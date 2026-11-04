import { getT } from "@/i18n/server";

/** Separate web app manifest for Dialogbot Privat. The root manifest (src/app/manifest.ts) stays the business app's
 *  (start_url /app); the /privat pages link this one instead, so «Føj til hjemmeskærm» from Privat opens Min dag and the
 *  home-screen app (needed for push on iPhone) stays inside /privat/. */
export async function GET() {
  const t = await getT("privat");
  return Response.json({
    id: "/privat/",
    name: "Dialogbot Privat",
    short_name: "Dialogbot",
    description: t("meta.landingDescription"),
    start_url: "/privat/dag",
    scope: "/privat/",
    display: "standalone",
    background_color: "#FFFBF5",
    theme_color: "#E0521A",
    icons: [  // the orange Privat mark – opaque, so no launcher paints the corners black
      { src: "/icons/privat-icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/privat-icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/privat-icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  }, { headers: { "content-type": "application/manifest+json", "cache-control": "public, max-age=3600" } });
}
