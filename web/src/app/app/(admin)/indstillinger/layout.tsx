/** Alle indstillinger: the overview of tiles; the forms open as sheets (?ark=…). */
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return <section className="flex flex-col gap-6">{children}</section>;
}
