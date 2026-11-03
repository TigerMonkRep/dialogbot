import Link from "next/link";
import { Icon } from "@/components/ui";
import { getT } from "@/i18n/server";

/** Help sections: icon, key and the items (key, link); texts are `app.help.<section>.title` and `app.help.<section>.<item>.q|a`. */
const SECTIONS: { icon: string; id: string; items: [string, string?][] }[] = [
  { icon: "rocket_launch", id: "start", items: [["guide", "/app/setup"], ["fetch", "/onboarding/business"]] },
  { icon: "menu_book", id: "knowledge", items: [["approved", "/app/viden"], ["prices", "/app/viden"], ["edit", "/app/viden"]] },
  { icon: "support_agent", id: "reception", items: [["script", "/app/indstillinger?ark=hilsen"], ["phone", "/app/indstillinger?ark=telefoni"], ["webchat", "/app/indstillinger?ark=webchat"]] },
  { icon: "contact_support", id: "leads", items: [["tasks", "/app/opkald?f=to_you"], ["billing", "/app/konto"]] },
  { icon: "group", id: "team", items: [["roles", "/app/konto"], ["log", "/app/indstillinger?ark=log"]] },
];

/** Help: short answers to the common questions, each linking to where it is done. */
export default async function HelpPage() {
  const t = await getT("app");
  return (
    <section className="flex flex-col gap-4 max-w-4xl">
      <div>
        <span className="eyebrow">{t("shell.help")}</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{t("help.title")}</h1>
      </div>
      {SECTIONS.map((s) => (
        <div key={s.id} className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
          <h2 className="font-display text-headline-sm text-ink flex items-center gap-1"><Icon name={s.icon} size={22} className="text-muted" />{t(`help.${s.id}.title`)}</h2>
          <dl className="flex flex-col gap-2">
            {s.items.map(([id, href]) => (
              <div key={id} className="p-2 rounded-lg bg-panel">
                <dt className="text-label-lg text-ink font-bold">{t(`help.${s.id}.${id}.q`)}</dt>
                <dd className="text-body-sm text-ink-soft mt-0.5">{t(`help.${s.id}.${id}.a`)} {href && <Link href={href} className="text-ink underline whitespace-nowrap">{t("help.goThere")}</Link>}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </section>
  );
}
