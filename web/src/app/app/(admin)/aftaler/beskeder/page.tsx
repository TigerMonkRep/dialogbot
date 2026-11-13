import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { getT } from "@/i18n/server";
import { LOCALE_NAMES, type Locale } from "@/i18n/config";
import { SmsToggle } from "./sms-toggle";

type Item = {
  variant: string; audience: "customer" | "owner"; label: string;
  sms: { text: string; chars: number; encoding: string; segments: number } | null;
  email: { subject: string; preheader: string | null; html: string; text: string; from_name: string };
};
type Messages = { lang: string; default_lang: string; languages: string[]; source: "sample" | "booking"; business: string; sends_nothing: boolean; items: Item[];
  sending: { email: boolean; sms_enabled: boolean; reminder_hours: number; version: number } };

const chip = (on: boolean) => `inline-flex items-center min-h-[44px] px-4 rounded-full border-[1.5px] border-ink text-[14px] font-semibold ${on ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`;

/** E07 – «Beskeder om aftaler»: every booking message (customer SMS + e-mail in the business's name, the owner's
 *  e-mails) in the eight languages, rendered by the API from the real templates. The preview sends nothing; the card
 *  «Sådan sendes beskederne» says what goes out automatically and holds the SMS opt-in (off by default). */
export default async function BookingMessagesPage({ searchParams }: { searchParams: Promise<{ sprog?: string; besked?: string; aftale?: string }> }) {
  const ws = await requireWorkspace();
  const t = await getT("app");
  if (ws.role === "reader") return <p className="rounded-2xl border-2 border-ink bg-paper p-6 text-[15px] text-ink-soft">{t("bookings.staffOnly")}</p>;
  const { sprog, besked, aftale } = await searchParams;
  const q = new URLSearchParams();
  if (sprog && /^[a-z]{2}$/.test(sprog)) q.set("lang", sprog);
  if (aftale && /^[0-9a-f-]{36}$/.test(aftale)) q.set("booking_id", aftale);
  const m = await backend<Messages>(`/workspaces/${ws.id}/bookings/messages${q.size ? `?${q}` : ""}`);
  const cur = m.items.find((x) => x.variant === besked) ?? m.items[0];
  const href = (p: { sprog?: string; besked?: string }) => {
    const s = new URLSearchParams({ sprog: p.sprog ?? m.lang, besked: p.besked ?? cur.variant });
    if (aftale) s.set("aftale", aftale);
    return `/app/aftaler/beskeder?${s}`;
  };
  const groups: [string, Item[]][] = [[t("bookings.messages.toCustomer"), m.items.filter((x) => x.audience === "customer")],
    [t("bookings.messages.toYou"), m.items.filter((x) => x.audience === "owner")]];
  return (
    <div className="flex flex-col gap-5 min-w-0">
      <div className="flex flex-col gap-1.5">
        <Link href="/app/aftaler" className="text-[14px] font-semibold text-accent hover:underline self-start">← {t("bookings.messages.back")}</Link>
        <span className="eyebrow">{t("bookings.messages.eyebrow")}</span>
        <h1 className="font-display font-extrabold text-[26px] sm:text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{t("bookings.messages.title")}</h1>
        <p className="text-[15px] leading-relaxed text-ink-soft max-w-[680px]">{t("bookings.messages.intro")}</p>
      </div>
      <p role="note" className="rounded-xl bg-highlight px-4 py-3 text-[14px] font-semibold text-ink max-w-[680px]">{t("bookings.messages.noSend")}
        <span className="block font-normal mt-1">{t("bookings.messages.status")}</span></p>

      <section aria-labelledby="sending-title" className="flex flex-col gap-3 rounded-2xl border-2 border-ink bg-paper p-5 max-w-[680px]">
        <h2 id="sending-title" className="font-display font-extrabold text-[20px] text-ink">{t("bookings.messages.sending.title")}</h2>
        <ul className="flex flex-col gap-2 text-[14px] leading-relaxed text-ink-soft list-disc pl-5">
          <li>{t("bookings.messages.sending.email")}</li>
          <li>{t("bookings.messages.sending.reminder")}</li>
          <li>{t("bookings.messages.sending.owner")}</li>
        </ul>
        <SmsToggle wsId={ws.id} enabled={m.sending.sms_enabled} canManage={ws.role === "owner" || ws.role === "admin"} />
      </section>

      <nav aria-label={t("bookings.messages.language")} className="flex flex-col gap-2">
        <span className="eyebrow">{t("bookings.messages.language")}</span>
        <div className="flex flex-wrap gap-2">{m.languages.map((l) => (
          <Link key={l} href={href({ sprog: l })} hrefLang={l} aria-current={l === m.lang ? "true" : undefined} className={chip(l === m.lang)}>{LOCALE_NAMES[l as Locale] ?? l}</Link>))}</div>
      </nav>

      <div className="flex flex-wrap gap-6 items-start">
        <nav aria-label={t("bookings.messages.variantsAria")} className="flex-[1_1_260px] max-w-[360px] min-w-0 flex flex-col gap-4">
          {groups.map(([title, items]) => (
            <div key={title} className="flex flex-col gap-2">
              <span className="eyebrow">{title}</span>
              <ol className="flex flex-col gap-2">{items.map((x) => {
                const n = m.items.indexOf(x) + 1;
                const on = x.variant === cur.variant;
                return (
                  <li key={x.variant}>
                    <Link href={href({ besked: x.variant })} aria-current={on ? "page" : undefined}
                      className={`flex items-start gap-3 rounded-xl border-[1.5px] border-ink px-3 py-2.5 min-h-[44px] ${on ? "bg-panel" : "bg-paper hover:bg-panel"}`}>
                      <span className={`inline-flex shrink-0 items-center justify-center w-8 h-8 rounded-lg font-display font-extrabold text-[15px] ${on ? "bg-highlight text-ink" : "border-[1.5px] border-ink text-ink"}`}>{n}</span>
                      <span className="min-w-0"><span className="block text-[15px] font-semibold text-ink">{t(`bookings.messages.label.${x.variant}`)}</span>
                        <span className="block text-[13px] text-muted">{t(`bookings.messages.desc.${x.variant}`)}</span></span>
                    </Link>
                  </li>);
              })}</ol>
            </div>))}
        </nav>

        <section aria-label={t(`bookings.messages.label.${cur.variant}`)} className="flex-[999_1_460px] min-w-0 flex flex-col gap-5">
          <p className="text-[13px] text-muted">{m.source === "booking" ? t("bookings.messages.booking") : t("bookings.messages.sample")}</p>
          <div className="flex flex-col gap-2 rounded-2xl border-2 border-ink bg-paper p-5">
            <span className="eyebrow">{t("bookings.messages.sms")}</span>
            {cur.sms ? (
              <>
                <p className="text-[13px] text-muted">{t("bookings.messages.fromLabel")}: {m.business}</p>
                <p data-testid="sms-preview" className="rounded-2xl rounded-tl-sm bg-panel border-[1.5px] border-line px-4 py-3 text-[15px] leading-relaxed text-ink max-w-[420px] break-words">{cur.sms.text}</p>
                <p className="text-[13px] text-muted">{t("bookings.messages.smsMeta", { chars: cur.sms.chars, segments: cur.sms.segments, encoding: cur.sms.encoding })}</p>
              </>
            ) : <p className="text-[14px] text-ink-soft">{t("bookings.messages.noSms")}</p>}
          </div>
          <div className="flex flex-col gap-2 rounded-2xl border-2 border-ink bg-paper p-5 shadow-block min-w-0">
            <span className="eyebrow">{t("bookings.messages.email")}</span>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[14px] min-w-0">
              <dt className="text-muted">{t("bookings.messages.fromLabel")}</dt><dd className="text-ink break-words">{cur.email.from_name}</dd>
              <dt className="text-muted">{t("bookings.messages.subject")}</dt><dd data-testid="email-subject" className="text-ink font-semibold break-words">{cur.email.subject}</dd>
            </dl>
            <iframe title={t("bookings.messages.frame")} sandbox="" srcDoc={cur.email.html} className="w-full h-[720px] rounded-xl border-[1.5px] border-line bg-panel" />
          </div>
        </section>
      </div>
    </div>
  );
}
