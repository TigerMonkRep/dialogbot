"use client";
/** Kalender app (/privat/kalender, and inside the app sheet when it is on): connect Google or Outlook, or make the
 *  private subscription link (iPhone and every other calendar), and see the upcoming appointments with
 *  «Tilføj til kalender» (.ics). The link is shown once; the backend keeps only a hash of it. */
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import { icsHref, type CalendarProvider, type CalendarState } from "@/lib/privat/api";
import { Eyebrow, Pill } from "./bits";
import { Ico } from "./icons";
import { usePrivat } from "./store";

const PROVIDERS: [CalendarProvider, string][] = [["google", "calendar.google"], ["microsoft", "calendar.outlook"]];

export function CalendarPanel() {
  const t = useT("privat");
  const { api } = usePrivat();
  const [st, setSt] = useState<CalendarState | null>(null);
  const [link, setLink] = useState<{ url: string; webcal_url: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setSt(await api.calendar()); } catch (e) { setErr((e as ApiError).message); }
  }, [api]);
  useEffect(() => {
    void load();
    // Back from Google/Microsoft: /privat/kalender?connected=google_calendar or ?error=…
    const q = new URLSearchParams(window.location.search);
    if (q.get("connected")) setNote(t("calendar.connected"));
    if (q.get("error")) setErr(t("calendar.connectFailed"));
  }, [load, t]);

  const run = async (fn: () => Promise<unknown>) => {
    setErr(null);
    try { await fn(); await load(); } catch (e) { setErr((e as ApiError).message); }
  };
  const connect = (p: CalendarProvider) => run(async () => { const { url } = await api.connectCalendar(p); window.location.assign(url); });
  const makeLink = () => run(async () => { setCopied(false); setLink(await api.newCalendarFeed()); });
  const copy = async () => { if (!link) return; try { await navigator.clipboard.writeText(link.url); setCopied(true); } catch { /* the field can be selected by hand */ } };

  if (!st) return err ? <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p> : <p className="m-0 text-[14px] text-muted">{t("calendar.loading")}</p>;
  return (
    <div className="flex flex-col gap-4" data-testid="calendar-panel">
      {note && <p role="status" className="m-0 text-[14px] font-semibold text-success">{note}</p>}
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}

      <section className="rounded-[18px] border-[1.5px] border-ink bg-panel p-3.5 flex flex-col gap-2.5" aria-labelledby="cal-direct">
        <Eyebrow><span id="cal-direct">{t("calendar.direct")}</span></Eyebrow>
        <p className="m-0 text-[14px] text-ink-soft">{t("calendar.directText")}</p>
        {PROVIDERS.map(([p, label]) => {
          const s = st.providers[p];
          return (
            <div key={p} className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-[15px] flex-1 min-w-0">{t(label)}{s.connected && s.account_label ? ` · ${s.account_label}` : ""}</span>
              {s.connected ? (
                <>
                  <Pill tone="ok">{t("calendar.isConnected")}</Pill>
                  <Button variant="outline" className="rounded-full border-2" onClick={() => void run(() => api.disconnectCalendar(p))}>{t("calendar.disconnect")}</Button>
                </>
              ) : s.available ? (
                <Button className="rounded-full" onClick={() => void connect(p)}>{t("calendar.connect")}</Button>
              ) : (
                <Pill tone="soon">{t("calendar.notYet")}</Pill>
              )}
              {s.error && <p className="m-0 w-full text-[13px] text-danger">{s.error}</p>}
            </div>
          );
        })}
      </section>

      <section className="rounded-[18px] border-[1.5px] border-ink bg-paper p-3.5 flex flex-col gap-2.5" aria-labelledby="cal-feed">
        <Eyebrow><span id="cal-feed">{t("calendar.feed")}</span></Eyebrow>
        <p className="m-0 text-[14px] text-ink-soft">{t("calendar.feedText")}</p>
        {link ? (
          <div className="flex flex-col gap-2">
            <input readOnly value={link.url} aria-label={t("calendar.feedLink")} onFocus={(e) => e.currentTarget.select()}
              className="w-full rounded-xl border-2 border-ink bg-panel px-3 py-2 text-[13px] font-mono" />
            <div className="flex gap-2 flex-wrap">
              <Button className="rounded-full" onClick={() => void copy()}>{copied ? t("calendar.copied") : t("calendar.copy")}</Button>
              <a href={link.webcal_url} className="inline-flex items-center min-h-[44px] px-4 rounded-full border-2 border-ink font-semibold text-[15px] hover:bg-panel">{t("calendar.openApple")}</a>
            </div>
            <p className="m-0 text-[13px] text-muted">{t("calendar.feedOnce")}</p>
            <details className="text-[14px]">
              <summary className="cursor-pointer font-semibold min-h-[44px] flex items-center">{t("calendar.howTo")}</summary>
              <ul className="m-0 mt-1 pl-5 flex flex-col gap-1.5 text-[14px]">
                <li>{t("calendar.howIphone")}</li>
                <li>{t("calendar.howGoogle")}</li>
                <li>{t("calendar.howOutlook")}</li>
              </ul>
            </details>
          </div>
        ) : (
          <div className="flex gap-2 flex-wrap items-center">
            {st.feed.active && <Pill tone="ok">{t("calendar.feedActive")}</Pill>}
            <Button variant={st.feed.active ? "outline" : undefined} className={`rounded-full ${st.feed.active ? "border-2" : ""}`} onClick={() => void makeLink()}>
              {st.feed.active ? t("calendar.feedNew") : t("calendar.feedMake")}
            </Button>
            {st.feed.active && <Button variant="outline" className="rounded-full border-2" onClick={() => void run(() => api.dropCalendarFeed())}>{t("calendar.feedStop")}</Button>}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2" aria-labelledby="cal-upcoming">
        <h3 id="cal-upcoming" className="m-0 text-[15px] font-semibold font-body">{t("calendar.upcoming")}</h3>
        {st.appointments.length === 0 ? <p className="m-0 text-[14px] text-muted">{t("calendar.none")}</p> : (
          <ul className="m-0 p-0 list-none flex flex-col gap-2">
            {st.appointments.map((a) => (
              <li key={a.id} className="rounded-[16px] border-[1.5px] border-ink bg-paper p-3 flex flex-col gap-1">
                <span className="font-semibold text-[15px] [overflow-wrap:anywhere]">{a.title}</span>
                <span className="text-[14px] text-ink-soft">{a.when_text}{a.location ? ` · ${a.location}` : ""}</span>
                <span className="flex gap-2 flex-wrap mt-1">
                  <a href={icsHref(a)} download className="inline-flex items-center gap-1.5 min-h-[40px] px-3 rounded-full border-2 border-ink text-[14px] font-semibold hover:bg-panel">
                    <Ico name="calendar" size={16} />{t("calendar.addToCalendar")}
                  </a>
                  <Button variant="outline" className="rounded-full border-2" onClick={() => void run(() => api.removeAppointment(a.id))}>{t("calendar.remove")}</Button>
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="m-0 text-[13px] text-muted">{t("calendar.removeNote")}</p>
      </section>
    </div>
  );
}
