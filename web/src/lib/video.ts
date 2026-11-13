import type { T } from "@/i18n/translate";
import type { Locale } from "@/i18n/config";

/** The explainer (~90 s) in web/public/video/, one version per language: its own voiceover, screens and burned-in
 *  captions (made from web/video/ – see its README). The human texts (title, poster alt, description) live in
 *  messages/<locale>/site.json under "video". */
const DURATION: Record<Locale, number> = { da: 83, en: 86, de: 91, es: 90, fr: 93, it: 91, no: 85, sv: 84, us: 86 };

export function videoFor(locale: Locale) {
  const base = `/video/dialogbot-${locale}`;
  return {
    src: `${base}.mp4`,
    poster: `${base}-poster.jpg`,
    thumb: `${base}-thumb.jpg`,
    captions: `${base}.vtt`,
    durationIso: `PT1M${DURATION[locale] - 60}S`,
  };
}

export const VIDEO_UPLOAD_DATE = "2026-11-03T22:00:00+01:00";

/** schema.org VideoObject for the front page's structured data. `t` is the "site" translator. */
export function videoStructuredData(origin: string, t: T, locale: Locale, inLanguage: string) {
  const v = videoFor(locale);
  return {
    "@type": "VideoObject", name: t("video.title"), description: t("video.description"), inLanguage,
    thumbnailUrl: [`${origin}${v.poster}`], contentUrl: `${origin}${v.src}`,
    uploadDate: VIDEO_UPLOAD_DATE, duration: v.durationIso,
  };
}
