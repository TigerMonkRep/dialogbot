import type { MetadataRoute } from "next";

/** Web app manifest for the business app ("Føj til hjemmeskærm" → /app, the blue mark). Served from a route rather
 *  than the manifest.ts convention, so the /privat segment can point at its own manifest through metadata – a
 *  file-based root manifest would override that on every page. */
function manifest(): MetadataRoute.Manifest {
  return {
    name: "Dialogbot",
    short_name: "Dialogbot",
    description: "AI-reception, callback og kampagner for danske virksomheder",
    lang: "da",
    start_url: "/app",
    scope: "/",
    display: "standalone",
    background_color: "#2456F6",
    theme_color: "#2456F6",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}

export function GET() {
  return Response.json(manifest(), { headers: { "content-type": "application/manifest+json", "cache-control": "public, max-age=3600" } });
}
