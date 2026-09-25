"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui";

const TABS: [string, string, string, string][] = [
  ["/onboarding/business", "Virksomhed (S01)", "Virksomhed", "domain"],
  ["/app/settings/team", "Team & roller (S02)", "Team", "group"],
  ["/app/settings/profile", "Min profil (S08)", "Profil", "person"],
  ["/app/settings/activity", "Aktivitetslog (S09)", "Log", "history"],
];

/** Settings tab bar in the same style as the K01 tab switcher. */
export function SettingsTabs() {
  const path = usePathname();
  return (
    <div className="overflow-x-auto no-scrollbar -mx-margin px-margin md:mx-0 md:px-0 pb-space-xs">
      <nav className="flex items-center gap-space-xs min-w-max md:p-1 md:bg-surface-container-low md:rounded-xl" aria-label="Indstillinger">
        {TABS.map(([href, label, short, icon]) => {
          const on = path === href;
          return (
            <Link key={href} href={href} aria-current={on ? "page" : undefined}
              className={`flex items-center gap-space-sm px-space-md py-space-sm rounded-full md:rounded-lg font-label-md text-label-md transition-all ${on ? "bg-primary-container text-on-primary shadow-sm" : "bg-surface-container md:bg-transparent text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high"}`}>
              <Icon name={icon} size={18} /><span className="hidden md:inline">{label}</span><span className="md:hidden">{short}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
