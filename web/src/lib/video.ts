/** The 70-second explainer in web/public/video/. Shared by the player (client) and the structured data (server). */
export const VIDEO = {
  src: "/video/dialogbot-forklaret.mp4",
  poster: "/video/dialogbot-forklaret-poster.jpg",
  thumb: "/video/dialogbot-forklaret-thumb.jpg",
  captions: "/video/dialogbot-forklaret-da.vtt",
  title: "Se, hvad Dialogbot kan",
  description: "Dialogbot forklaret på 70 sekunder: tager telefonen, booker tider, svarer på hjemmesiden – og du godkender alt, den må sige.",
  durationIso: "PT1M10S",
  uploadDate: "2026-10-29",
};

/** schema.org VideoObject for the front page's structured data. */
export function videoStructuredData(origin: string) {
  return {
    "@type": "VideoObject", name: VIDEO.title, description: VIDEO.description, inLanguage: "da",
    thumbnailUrl: [`${origin}${VIDEO.poster}`], contentUrl: `${origin}${VIDEO.src}`,
    uploadDate: VIDEO.uploadDate, duration: VIDEO.durationIso,
  };
}
