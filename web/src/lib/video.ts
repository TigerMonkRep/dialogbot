import type { T } from "@/i18n/translate";

/** The 70-second explainer in web/public/video/. Shared by the player (client) and the structured data (server).
 *  The human texts (title, poster alt, description) live in messages/<locale>/site.json under "video". The video
 *  itself and its burned-in captions are Danish. */
export const VIDEO = {
  src: "/video/dialogbot-forklaret.mp4",
  poster: "/video/dialogbot-forklaret-poster.jpg",
  thumb: "/video/dialogbot-forklaret-thumb.jpg",
  captions: "/video/dialogbot-forklaret-da.vtt",
  durationIso: "PT1M10S",
  uploadDate: "2026-10-29T09:00:00+01:00",
};

/** schema.org VideoObject for the front page's structured data. `t` is the "site" translator. */
export function videoStructuredData(origin: string, t: T) {
  return {
    "@type": "VideoObject", name: t("video.title"), description: t("video.description"), inLanguage: "da",
    thumbnailUrl: [`${origin}${VIDEO.poster}`], contentUrl: `${origin}${VIDEO.src}`,
    uploadDate: VIDEO.uploadDate, duration: VIDEO.durationIso,
  };
}
