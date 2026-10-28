import { SettingsTabs } from "./tabs";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-space-lg">
      <div className="flex flex-col gap-space-xs">
        <span className="eyebrow">Bagerst i hæftet</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Alle indstillinger</h1>
        <p className="text-[15px] text-ink-soft max-w-[560px]">Alt, Dialogbot ved og gør – ét sted. Intet markeres som klar, før det virker.</p>
      </div>
      <SettingsTabs />
      {children}
    </div>
  );
}
