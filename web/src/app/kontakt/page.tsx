import type { Metadata } from "next";
import Link from "@/i18n/link";
import { getLocale, getT } from "@/i18n/server";
import { COMPANY } from "@/components/legal-page";
import { SiteChrome } from "@/components/site-chrome";
import { phoneFor } from "@/lib/contact";
import { PhoneIcon, SmsIcon } from "@/components/site-icons";
import { alternatesFor } from "@/lib/site";

const PATH = "/kontakt";

export async function generateMetadata(): Promise<Metadata> {
  const [t, locale] = await Promise.all([getT("landing.contact.meta"), getLocale()]);
  return { title: t("title"), description: t("description"), alternates: alternatesFor(PATH, locale) };
}

/** Kontakt — on the shared public chrome. Nummer, overskrift, tekst; one action (ring) first. */
export default async function ContactPage() {
  const [t, tc] = await Promise.all([getT("landing.contact"), getT("common")]);
  const hours = tc("chrome.hours");
  const ph = phoneFor(await getLocale());
  const s = (key: string) => t(`sections.${key}`);
  const sections: [string, React.ReactNode][] = [
    [s("email.title"), <p key="e">{s("email.a")}<a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>{s("email.b")}</p>],
    [s("phone.title"), <p key="t">{s("phone.a")}<a href={ph.tel}>{ph.intl}</a>{s("phone.b")}{hours.toLowerCase()}.</p>],
    [s("post.title"), <p key="p">{COMPANY.name}, {t("cvrNo")} {COMPANY.cvr}, {COMPANY.address}.</p>],
    [s("billing.title"), <p key="b">{s("billing.p")}</p>],
    [s("loggedIn.title"), <p key="h">{s("loggedIn.p")}</p>],
    [s("ambassadors.title"), <p key="a">{s("ambassadors.a")}<Link href="/ambassador/bliv">dialogbot.dk/ambassador/bliv</Link>{s("ambassadors.b")}</p>],
    [s("data.title"), <p key="d">{s("data.a")}<Link href="/privatliv">{s("data.link")}</Link>{s("data.b")}</p>],
  ];
  return (
    <SiteChrome>
      <section className="bg-panel border-b-2 border-ink">
        <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-12 sm:py-16 flex flex-wrap gap-10 items-start">
          <div className="flex-[1_1_420px] flex flex-col gap-4">
            <span className="eyebrow text-[13px] tracking-[1.5px]">{t("eyebrow")}</span>
            <h1 className="m-0 font-display font-extrabold text-[clamp(34px,4.6vw,60px)] leading-[1.03] tracking-[-1.4px]">{t("title")}</h1>
            <p className="m-0 text-lg leading-[1.55] text-ink-soft max-w-[620px]">{t("lead")}</p>
            <p className="m-0 text-sm text-muted">{t("updated")}</p>
          </div>
          <div className="flex-[1_1_300px] max-w-[460px] flex flex-col gap-3">
            <a href={ph.tel} className="flex items-center gap-3.5 p-5 rounded-[20px] bg-white border-2 border-ink shadow-block text-ink no-underline">
              <span className="inline-flex w-12 h-12 rounded-xl bg-accent items-center justify-center shrink-0"><PhoneIcon size={24} stroke="#FFFFFF" /></span>
              <span className="flex flex-col"><span className="eyebrow">{t("call")} · {hours}</span><span className="font-display font-extrabold text-2xl tracking-[-0.5px]">{ph.local ? ph.display : ph.intl}</span></span>
            </a>
            <a href={`mailto:${COMPANY.email}`} className="flex items-center gap-3.5 p-5 rounded-[20px] bg-white border-2 border-ink text-ink no-underline hover:bg-panel">
              <span className="inline-flex w-12 h-12 rounded-xl bg-ink items-center justify-center shrink-0"><SmsIcon size={24} stroke="#FFFFFF" /></span>
              <span className="flex flex-col"><span className="eyebrow">{t("write")}</span><span className="font-display font-bold text-xl">{COMPANY.email}</span></span>
            </a>
          </div>
        </div>
      </section>
      <div className="max-w-[880px] mx-auto px-4 sm:px-6 py-12 sm:py-16 flex flex-col gap-5 w-full">
        {sections.map(([h, body], i) => (
          <section key={h} className="bg-white rounded-[20px] border-2 border-ink p-5 sm:p-6 flex gap-4">
            <span className="hidden sm:inline-flex w-10 h-10 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-xl shrink-0" aria-hidden>{i + 1}</span>
            <div className="min-w-0 flex-1 flex flex-col gap-2">
              <h2 className="m-0 font-display font-bold text-xl">{h}</h2>
              <div className="text-[15px] leading-normal text-ink-soft [&_a]:underline [&_a]:underline-offset-4 [&_a]:text-accent [&_p]:m-0">{body}</div>
            </div>
          </section>
        ))}
        <p className="m-0 text-sm text-muted">{COMPANY.name} · {t("cvrNo")} {COMPANY.cvr} · {COMPANY.address}</p>
      </div>
    </SiteChrome>
  );
}
