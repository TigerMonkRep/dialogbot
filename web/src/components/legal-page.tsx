import Link from "@/i18n/link";
import { getT } from "@/i18n/server";
import { format, type Vars } from "@/i18n/translate";
import { CompareTable } from "./compare-table";
import { LogoMark } from "./ui";

/** Shared frame for the public legal and contact pages (privatliv, vilkår, kontakt). Server component. */
export const COMPANY = {
  name: "Dialogbot",
  cvr: "25632710",
  address: "Abildgade 18, 8200 Aarhus, Danmark",
  email: "info@dialogbot.dk",
};

/* ── Rich text from JSON (namespaces "articles" and "legal") ──────────────────────────────────────────────────────
 * A section body is an array of blocks:
 *   {"type":"p","text":"…"}                         plain paragraph
 *   {"type":"p","parts":["text ",{"b":"fed"}," …"]}  paragraph with inline parts
 *   {"type":"ul","items":["…", ["…",{"code":"##002#"}]]}  list; an item is a string or an array of parts
 *   {"type":"table","other":"…","rows":[[what, Dialogbot, other], …]}  → <CompareTable>
 * Inline parts: "string" | {"b"} bold | {"code"} phone code | {"link","text"} internal link (gets the language prefix)
 *   | {"href","text"} external link | {"email":true} COMPANY.email as mailto.
 * Strings may use {name} {cvr} {address} {email} (COMPANY) and any extra vars passed in. */
export type Part = string | { b: string } | { code: string } | { link: string; text: string } | { href: string; text: string } | { email: true };
export type Block =
  | { type: "p"; text?: string; parts?: Part[] }
  | { type: "ul"; items: (string | Part[])[] }
  | { type: "table"; other: string; rows: [string, string, string][] };
export type RichSection = { title: string; body: Block[] };

const COMPANY_VARS: Vars = { name: COMPANY.name, cvr: COMPANY.cvr, address: COMPANY.address, email: COMPANY.email };
const CODE = "rounded-md bg-panel-deep px-2 py-0.5 font-mono text-ink whitespace-nowrap";

function Inline({ parts, vars }: { parts: string | Part[]; vars: Vars }) {
  const list = typeof parts === "string" ? [parts] : parts;
  return <>{list.map((p, i) => {
    if (typeof p === "string") return <span key={i}>{format(p, vars)}</span>;
    if ("b" in p) return <strong key={i}>{format(p.b, vars)}</strong>;
    if ("code" in p) return <span key={i} className={CODE}>{p.code}</span>;
    if ("link" in p) return <Link key={i} href={p.link}>{format(p.text, vars)}</Link>;
    if ("href" in p) return <a key={i} href={p.href} rel="noreferrer">{format(p.text, vars)}</a>;
    return <a key={i} href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>;
  })}</>;
}

/** Renders JSON blocks with the current markup. `ulClassName` for containers that don't style lists themselves. */
export function Blocks({ blocks, vars, ulClassName }: { blocks: Block[]; vars?: Vars; ulClassName?: string }) {
  const v = { ...COMPANY_VARS, ...vars };
  return <>{blocks.map((b, i) => {
    if (b.type === "ul") return <ul key={i} className={ulClassName}>{b.items.map((it, j) => <li key={j}><Inline parts={it} vars={v} /></li>)}</ul>;
    if (b.type === "table") return <CompareTable key={i} other={b.other} rows={b.rows} />;
    return <p key={i}><Inline parts={b.parts ?? b.text ?? ""} vars={v} /></p>;
  })}</>;
}

export async function LegalPage({ label, title, intro, updated, sections }: {
  label: string; title: string; intro?: React.ReactNode; updated: string; sections: [string, React.ReactNode][];
}) {
  const t = await getT("legal");
  const notice = t("notice");
  return (
    <div className="min-h-dvh bg-panel text-ink">
      <header className="bg-paper border-b-2 border-ink">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 min-h-16 flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-2.5"><LogoMark size={32} /><span className="font-display font-extrabold text-[20px] tracking-[-0.3px] text-ink">Dialogbot</span></Link>
          <nav className="flex items-center gap-1" aria-label={t("shell.nav")}>
            <Link href="/vilkaar" className="inline-flex items-center min-h-[44px] px-3 rounded-xl text-[14px] font-semibold text-ink hover:bg-panel">{t("shell.terms")}</Link>
            <Link href="/privatliv" className="inline-flex items-center min-h-[44px] px-3 rounded-xl text-[14px] font-semibold text-ink hover:bg-panel">{t("shell.privacy")}</Link>
            <Link href="/kontakt" className="inline-flex items-center min-h-[44px] px-3 rounded-xl text-[14px] font-semibold text-ink hover:bg-panel">{t("shell.contact")}</Link>
          </nav>
        </div>
      </header>
      <main id="main" className="max-w-3xl mx-auto px-4 sm:px-6 py-8 md:py-10 flex flex-col gap-5">
        {notice && <p className="text-body-sm text-ink bg-highlight rounded-xl border-2 border-ink px-4 py-2.5">{notice}</p>}
        <div className="flex flex-col gap-2">
          <span className="eyebrow">{label}</span>
          <h1 className="font-display text-headline-lg-mobile md:text-[40px] md:leading-[1.05] md:tracking-[-1px] text-ink">{title}</h1>
          {intro && <p className="text-body-lg text-ink-soft max-w-[70ch]">{intro}</p>}
          <p className="text-body-sm text-muted">{updated}</p>
        </div>
        {sections.map(([h, body], i) => (
          <section key={h} className="bg-paper rounded-2xl border-2 border-ink p-5 sm:p-6 flex gap-4">
            <span className="hidden sm:inline-flex w-10 h-10 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-[20px] text-ink flex-shrink-0" aria-hidden>{i + 1}</span>
            <div className="min-w-0 flex-1">
              <h2 className="font-display text-headline-sm text-ink mb-2">{h}</h2>
              <div className="text-body-md text-ink-soft flex flex-col gap-2 [&_a]:underline [&_a]:text-accent">{body}</div>
            </div>
          </section>
        ))}
        <p className="text-body-sm text-muted">{COMPANY.name} · {t("shell.cvr")} {COMPANY.cvr} · {COMPANY.address} · <a className="underline text-accent" href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a></p>
      </main>
    </div>
  );
}
