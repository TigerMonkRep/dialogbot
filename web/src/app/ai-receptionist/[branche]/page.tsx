import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SeoPage } from "@/components/seo-page";
import { INDUSTRIES, industryBySlug } from "@/lib/industries";

export const dynamicParams = false;

export function generateStaticParams() {
  return INDUSTRIES.map((i) => ({ branche: i.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ branche: string }> }): Promise<Metadata> {
  const i = industryBySlug((await params).branche);
  if (!i) return {};
  const path = `/ai-receptionist/${i.slug}`;
  return { title: i.title, description: i.description, alternates: { canonical: path },
    openGraph: { url: path, title: `${i.title} | Dialogbot`, images: ["/opengraph-image.png"] } };
}

export default async function Page({ params }: { params: Promise<{ branche: string }> }) {
  const i = industryBySlug((await params).branche);
  if (!i) notFound();
  const others = INDUSTRIES.filter((x) => x.slug !== i.slug);
  return (
    <SeoPage path={`/ai-receptionist/${i.slug}`} kicker={`AI-receptionist til ${i.name}`} title={i.title.split(" – ")[0]}
      lead={i.description} points={[...i.benefits, "Vi guider jer gennem hele opsætningen"]}
      sections={[
        { title: `Problemet for ${i.name}`, body: <p>{i.pain} Dialogbot er en dansk AI-receptionist til {i.examples}, der tager telefonen og chatten, når I ikke selv kan.</p> },
        { title: "Sådan lyder det (eksempel)", body: <div className="flex flex-col gap-2.5 not-prose">
          {i.scenario.map(([who, line], n) => (
            <p key={n} className={`m-0 px-4 py-3 text-[15px] leading-normal max-w-[460px] border-2 border-ink ${who === "Dialogbot" ? "self-start rounded-[16px_16px_16px_4px] bg-white text-ink" : "self-end rounded-[16px_16px_4px_16px] bg-ink text-white"}`}>
              <span className="block text-xs font-semibold tracking-[1px] uppercase opacity-70 mb-0.5">{who}</span>{line}</p>
          ))}
          <p className="text-sm text-muted">Eksemplet er en illustration. Dialogbot svarer altid ud fra den viden, I selv har godkendt. <Link href="/proev">Hør den selv – bliv ringet op</Link>.</p>
        </div> },
        { title: `“${i.objection[0]}”`, body: <p>{i.objection[1]}</p> },
        { title: "Pris og opsætning", body: <p>Ét abonnement fra <strong>2.495 kr. om måneden</strong> – ekskl. moms og uden pris pr. henvendelse. En fra Dialogbot sætter det op sammen med jer på cirka en halv time. Se alle detaljer på <Link href="/priser">prissiden</Link>.</p> },
        { title: "Dialogbot til andre brancher", body: <ul>{others.map((o) => <li key={o.slug}><Link href={`/ai-receptionist/${o.slug}`}>AI-receptionist til {o.name}</Link></li>)}</ul> },
      ]}
      faq={[...i.faq, ["Hvad koster det?", "Ét abonnement fra 2.495 kr. om måneden, ekskl. moms. Der er ingen pris pr. henvendelse."], ["Kan vi beholde vores telefonnummer?", "Ja. I viderestiller jeres nummer til Dialogbot, når I er optaget eller har lukket."]]} />
  );
}
