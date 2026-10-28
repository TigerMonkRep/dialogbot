"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui";

const TABS: [string, string, string, string][] = [
  ["/onboarding/business", "Virksomhed", "Virksomhed", "domain"],
  ["/app/settings/team", "Team & roller", "Team", "group"],
  ["/app/settings/webchat", "Webchat", "Webchat", "chat"],
  ["/app/settings/telephony", "Telefoni", "Telefoni", "call"],
  ["/app/settings/integrationer", "Integrationer", "Systemer", "extension"],
  ["/app/settings/agreement", "Abonnement", "Aftale", "handshake"],
  ["/app/settings/profile", "Min profil", "Profil", "person"],
  ["/app/settings/activity", "Aktivitetslog", "Log", "history"],
];

/** Settings tab bar in the same style as the K01 tab switcher. */
export function SettingsTabs() {
  const path = usePathname();
  return (
    <div className="overflow-x-auto no-scrollbar -mx-margin px-margin md:mx-0 md:px-0 pb-space-xs">
      <nav className="inline-flex p-1 rounded-full border-2 border-ink bg-paper min-w-max" aria-label="Indstillinger">
        {TABS.map(([href, label, short, icon]) => {
          const on = path === href;
          return (
            <Link key={href} href={href} aria-current={on ? "page" : undefined}
              className={`inline-flex items-center gap-1.5 min-h-[40px] px-3.5 rounded-full text-[14px] font-semibold whitespace-nowrap ${on ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>
              <Icon name={icon} size={18} /><span className="hidden md:inline">{label}</span><span className="md:hidden">{short}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
