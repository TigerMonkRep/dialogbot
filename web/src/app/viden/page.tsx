import type { Metadata } from "next";
import Link from "next/link";
import { SeoPage } from "@/components/seo-page";
import { ARTICLES } from "@/lib/site";
import { INDUSTRIES } from "@/lib/industries";

export const metadata: Metadata = {
  title: "Viden om AI-receptionist, AI-telefonsvarer og chatbot",
  description: "Guides til danske virksomheder om AI-receptionist, AI-telefonsvarer, telefonpasning, viderestilling og chatbot på hjemmesiden.",
  alternates: { canonical: "/viden" },
  openGraph: { url: "/viden", title: "Viden | Dialogbot", images: ["/opengraph-image.png"] },
};

export default function Page() {
  return (
    <SeoPage path="/viden" kicker="Viden"
      title="Guides om AI-receptionist og telefonpasning"
      lead="Korte, praktiske guides til danske virksomheder, der vil have styr på telefonen og henvendelserne – uden at ansætte en ekstra person."
      points={ARTICLES.map((a) => a.title)}
      sections={[
        { title: "Guides", body: <ul>{ARTICLES.map((a) => <li key={a.slug}><Link href={`/viden/${a.slug}`}><strong>{a.title}</strong></Link> – {a.teaser}</li>)}</ul> },
        { title: "AI-receptionist til din branche", body: <ul>{INDUSTRIES.map((i) => <li key={i.slug}><Link href={`/ai-receptionist/${i.slug}`}>AI-receptionist til {i.name}</Link> – {i.examples}</li>)}</ul> },
      ]}
      faq={[["Hvad er Dialogbot?", "En dansk AI-receptionist, der tager telefonen og chatten for din virksomhed, svarer ud fra jeres egen godkendte viden og booker tider."], ["Kan jeg høre den?", "Ja. Skriv dit nummer på forsiden, så ringer Dialogbot dig op og viser det."]]} />
  );
}
