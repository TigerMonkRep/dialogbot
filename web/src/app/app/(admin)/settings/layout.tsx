import { Icon } from "@/components/ui";
import { SettingsTabs } from "./tabs";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-space-lg">
      <div className="flex flex-col gap-space-xs">
        <div className="hidden md:flex items-center gap-space-xs font-label-md text-label-md text-on-surface-variant"><span>Administration</span><Icon name="chevron_right" size={14} /><span className="text-primary font-semibold">Indstillinger</span></div>
        <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight">Indstillinger</h1>
      </div>
      <SettingsTabs />
      {children}
    </div>
  );
}
