import type { MetadataRoute } from "next";

/** Web app manifest: "Føj til hjemmeskærm" uses the robot logo as the app icon. */
export default function manifest(): MetadataRoute.Manifest {
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
