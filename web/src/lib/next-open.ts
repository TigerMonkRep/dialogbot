import { HTML_LANG, type Locale } from "@/i18n/config";

const TZ = "Europe/Copenhagen";
const day = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);

/** When a queued demo call comes (`scheduled_for` / `next_open` from the API), in Copenhagen time: «i dag» / «i morgen»
 *  (the caller's translated words) or the weekday, plus the time «08:00». */
export function nextOpenLabel(iso: string, locale: Locale, words: { today: string; tomorrow: string }, now = new Date()) {
  const at = new Date(iso);
  const tomorrow = new Date(now.getTime() + 24 * 3600 * 1000);
  const when = day(at) === day(now) ? words.today : day(at) === day(tomorrow) ? words.tomorrow
    : new Intl.DateTimeFormat(HTML_LANG[locale], { timeZone: TZ, weekday: "long" }).format(at);
  const time = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false }).format(at);
  return { when, time };
}
