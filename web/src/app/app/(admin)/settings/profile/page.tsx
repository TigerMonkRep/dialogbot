import Link from "next/link";
import { backend } from "@/lib/api.server";
import { Icon } from "@/components/ui";
import { LogoutButton } from "./client";

type Me = { id: string; email: string; display_name: string; email_verified: boolean; interface_language: string; signup_intent: string | null; created_at: string };
type Session = { id: string; created_at: string; last_seen_at: string; expires_at: string; user_agent: string | null; current: boolean };
const LANG: Record<string, string> = { da: "Dansk", en: "Engelsk", de: "Tysk", sv: "Svensk", no: "Norsk" };
const dt = (s: string) => new Date(s).toLocaleString("da-DK", { dateStyle: "medium", timeStyle: "short" });

function device(ua: string | null) {
  if (!ua) return "Ukendt enhed";
  const os = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "";
  const br = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : /node|undici|python|curl/i.test(ua) ? "Server/værktøj" : "Browser";
  return [br, os].filter(Boolean).join(" på ");
}

/** S08: own profile, language and sessions. Editing name/interface language has no API yet – shown read-only. */
export default async function ProfilePage() {
  const [me, sessions] = await Promise.all([backend<Me>("/auth/me"), backend<Session[]>("/auth/sessions")]);
  const rows: [string, React.ReactNode][] = [
    ["Navn", me.display_name],
    ["E-mail", <span key="e" className="flex flex-wrap items-center gap-space-xs">{me.email}{me.email_verified ? <span className="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-bold flex items-center gap-1"><Icon name="verified" size={14} />Bekræftet</span> : <Link href="/verify-email" className="px-2 py-0.5 rounded-full bg-error-container text-on-error-container font-label-sm text-label-sm font-bold">Ikke bekræftet – bekræft nu</Link>}</span>],
    ["Brugerfladesprog", LANG[me.interface_language] ?? me.interface_language],
    ["Konto oprettet", dt(me.created_at)],
  ];
  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-space-lg items-start">
      <section className="xl:col-span-7 bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
        <div className="flex items-center gap-space-md">
          <div className="w-12 h-12 rounded-full bg-primary text-on-primary flex items-center justify-center font-headline-sm text-headline-sm font-bold">{me.display_name.split(/\s+/).map((s) => s[0]).join("").slice(0, 2).toUpperCase()}</div>
          <div><span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Indstillinger</span><h2 className="font-headline-sm text-headline-sm text-primary font-bold">Min profil</h2></div>
        </div>
        <dl className="rounded-xl bg-surface-container-low divide-y divide-surface-container">
          {rows.map(([k, v]) => <div key={k} className="grid grid-cols-1 sm:grid-cols-[180px,1fr] gap-1 p-space-md"><dt className="font-label-md text-label-md text-on-surface-variant">{k}</dt><dd className="font-body-md text-body-md text-on-surface">{v}</dd></div>)}
        </dl>
        <p className="font-body-sm text-body-sm text-on-surface-variant flex items-start gap-space-xs"><Icon name="info" size={18} className="flex-shrink-0" />Navn og brugerfladesprog kan endnu ikke ændres her – der findes ikke et API til det. Samtale- og rapportsprog for arbejdsrummet styres under Sprog i opsætningen.</p>
        <div className="flex flex-wrap gap-space-md">
          <Link href="/password/forgot" className="px-space-md py-2.5 rounded-lg bg-surface-container text-primary font-label-md text-label-md font-semibold hover:bg-surface-container-high flex items-center gap-1.5"><Icon name="key" size={18} />Skift adgangskode</Link>
          <LogoutButton />
        </div>
      </section>
      <section className="xl:col-span-5 bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
        <div><h2 className="font-headline-sm text-headline-sm text-primary font-bold">Aktive sessioner</h2><p className="font-body-sm text-body-sm text-on-surface-variant">Alle sessioner tilbagekaldes, når du nulstiller adgangskoden.</p></div>
        <ul className="flex flex-col gap-2">
          {sessions.map((s) => (
            <li key={s.id} className="p-3 rounded-xl bg-surface-container-low flex items-start gap-space-sm">
              <Icon name={/iPhone|Android/.test(s.user_agent ?? "") ? "smartphone" : "computer"} size={22} className="text-primary mt-0.5" />
              <div className="min-w-0 flex-1">
                <p className="font-label-lg text-label-lg text-primary flex flex-wrap items-center gap-space-xs">{device(s.user_agent)}{s.current && <span className="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-bold">Denne enhed</span>}</p>
                <p className="font-body-sm text-body-sm text-on-surface-variant">Sidst aktiv {dt(s.last_seen_at)} · udløber {dt(s.expires_at)}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
