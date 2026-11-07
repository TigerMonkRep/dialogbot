import Link from "@/i18n/link";
import { getT } from "@/i18n/server";

export type Audience = "erhverv" | "privat";

/** The small two-door pill that sits next to the logo on both sites: «Erhverv | Privat». Same shape as the path
 *  switch (rounded-full, 2 px ink), the active door filled with ink; each door carries its colour dot (Klods-blå
 *  square for Erhverv, Hjemme-orange dot for Privat). On the entry page neither door is current. Server component –
 *  texts from common.json ("audience.*"). */
export async function AudienceSwitch({ current, size = "md" }: { current?: Audience; size?: "sm" | "md" }) {
  const t = await getT("common");
  const h = size === "sm" ? "min-h-8 px-3 text-[12px]" : "min-h-9 px-3.5 text-[13px]";
  const seg = `inline-flex items-center gap-2 ${h} rounded-full font-semibold leading-none no-underline whitespace-nowrap`;
  const door = (key: Audience, href: string, label: string, title: string) => {
    const active = current === key;
    const dot = key === "erhverv"
      ? <span aria-hidden="true" className={`inline-block w-2.5 h-2.5 rounded-[2px] ${active ? "bg-white" : ""}`} style={active ? undefined : { background: "#2456F6" }} />
      : <span aria-hidden="true" className={`inline-block w-2.5 h-2.5 rounded-full ${active ? "bg-white" : ""}`} style={active ? undefined : { background: "#E0521A" }} />;
    return active
      ? <span aria-current="page" title={title} className={`${seg} bg-ink text-white`}>{dot}{label}</span>
      : <Link href={href} title={title} className={`${seg} text-ink hover:bg-panel`}>{dot}{label}</Link>;
  };
  return (
    <nav aria-label={t("audience.label")} className="inline-flex p-1 rounded-full border-2 border-ink bg-white shrink-0">
      {door("erhverv", "/erhverv", t("audience.businessShort"), t("audience.business"))}
      {door("privat", "/privat", t("audience.privateShort"), t("audience.private"))}
    </nav>
  );
}
