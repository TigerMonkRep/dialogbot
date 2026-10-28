import Link from "next/link";
import { Icon } from "@/components/ui";

const GROUPS: { icon: string; title: string; text: string; items: [href: string, label: string][] }[] = [
  { icon: "call", title: "Telefon", text: "Nummer, viderestilling, hilsen og stemme.", items: [["/app/indstillinger/telefoni", "Nummer og viderestilling"], ["/app/indstillinger/hilsen", "Hilsen og manuskript"], ["/app/indstillinger/stemmer", "Stemme"]] },
  { icon: "menu_book", title: "Viden", text: "Hvad den ved, og hvad den ikke må.", items: [["/app/viden", "Det ved den"], ["/app/indstillinger/virksomhed", "Om virksomheden"]] },
  { icon: "chat", title: "Kanaler", text: "Chat på hjemmesiden.", items: [["/app/indstillinger/webchat", "Webchat og domæner"]] },
  { icon: "calendar_month", title: "Booking", text: "Kalender og regler for aftaler.", items: [["/app/aftaler", "Aftaler og bookingregler"], ["/app/indstillinger/integrationer", "Kalender og systemer"]] },
  { icon: "campaign", title: "Kampagner", text: "Ring kunder op.", items: [["/app/kampagner", "Kampagner"]] },
  { icon: "group", title: "Team og konto", text: "Hvem må hvad, abonnement og fakturaer.", items: [["/app/konto", "Hvem må se og ændre"], ["/app/konto/abonnement", "Abonnement"], ["/app/konto/fakturering", "Fakturaer"], ["/app/konto/profil", "Min profil"]] },
  { icon: "history", title: "Historik", text: "Hvad der er ændret, og af hvem.", items: [["/app/indstillinger/log", "Aktivitetslog"]] },
];

export default function SettingsOverview() {
  return (
    <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {GROUPS.map((g) => (
        <li key={g.title} className="rounded-2xl bg-paper border-2 border-ink p-5 flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <span className="inline-flex w-10 h-10 rounded-[10px] bg-accent text-white items-center justify-center"><Icon name={g.icon} size={22} /></span>
            <div>
              <h2 className="font-display font-extrabold text-[20px] leading-tight text-ink">{g.title}</h2>
              <p className="text-[13px] text-muted">{g.text}</p>
            </div>
          </div>
          <ul className="flex flex-col">
            {g.items.map(([href, label]) => (
              <li key={href}><Link href={href} className="flex items-center justify-between min-h-[44px] border-t-[1.5px] border-line text-[15px] font-semibold text-ink hover:text-accent">{label}<Icon name="arrow_forward" size={18} /></Link></li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}
