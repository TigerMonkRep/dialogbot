import Link from "next/link";
import { AdminFrame, NotOperator, load } from "../shared";

const TOOLS: [string, string, string][] = [
  ["/app/operator/salg", "Dialogbots salg", "Find virksomheder, undersøg dem, byg manuskripter til Peter og simulér samtaler."],
  ["/app/operator/social", "Sociale medier", "Godkend og planlæg opslag på Facebook, Instagram og TikTok."],
  ["/app/operator/ambassadors", "Ambassadører og affiliates", "Godkend, se saldi og kør udbetalinger. Se en ambassadørs egen side via Brugere → Se som."],
  ["/app/operator/sales", "Salg", "Prøveopkald og leads fra hjemmesiden."],
  ["/app/operator/telephony", "Telefoni", "Numre, dokumenter og opsætningsjob."],
  ["/app/operator/voices", "Stemmer", "Gennemgå rettigheder og udgiv stemmer."],
];

export default async function Tools() {
  if (!(await load("/operator/admin/overview"))) return <NotOperator />;
  return (
    <AdminFrame active="/app/operator/admin/vaerktoejer" title="Værktøjer" intro="De eksisterende operatørsider samlet ét sted.">
      <ul className="grid md:grid-cols-2 gap-space-md">
        {TOOLS.map(([href, t, d]) => <li key={href}><Link href={href} className="block rounded-2xl bg-paper border-2 border-ink p-space-md hover:bg-panel h-full"><span className="font-display font-bold text-[18px]">{t}</span><span className="block text-[14px] text-muted mt-1">{d}</span></Link></li>)}
      </ul>
    </AdminFrame>
  );
}
