/** Industry landing pages (/ai-receptionist/[branche]). Copy mirrors the sales playbooks in app/modules/sales/script.py;
 *  every claim is something Dialogbot does today. The slugs stay Danish in every language; the texts live in
 *  messages/<locale>/landing.json under landing.industries.<slug> (shape: IndustryCopy). */
export type IndustryCopy = {
  name: string; plural: string; examples: string; title: string; description: string;
  pain: string; scenario: [string, string][]; benefits: string[]; objection: [string, string]; faq: [string, string][];
};

/** `plural` is the Danish label, kept for callers not yet translated – use raw(`landing.industries.${slug}`).plural
 *  or t(`landing.industries.${slug}.plural`). */
export type Industry = { slug: string; plural: string };

export const INDUSTRIES: Industry[] = [
  { slug: "haandvaerkere", plural: "Håndværkere" },
  { slug: "klinikker", plural: "Klinikker" },
  { slug: "frisoerer", plural: "Frisører og saloner" },
  { slug: "autovaerksteder", plural: "Autoværksteder" },
  { slug: "raadgivere", plural: "Rådgivere og kontorer" },
  { slug: "restauranter", plural: "Restauranter, hoteller og caféer" },
];

export const industryBySlug = (slug: string) => INDUSTRIES.find((i) => i.slug === slug);

/** Message key of an industry's copy: raw<IndustryCopy>(industryKey(slug)). */
export const industryKey = (slug: string) => `landing.industries.${slug}`;
