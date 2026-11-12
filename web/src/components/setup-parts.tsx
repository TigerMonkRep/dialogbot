/** "Du skal bruge": the box before every step. `title` is setup.need.title in the current language. */
export function Need({ items, title }: { items: [count: string, text: string, note?: string][]; title: string }) {
  return (
    <div className="rounded-2xl border-[1.5px] border-ink bg-paper px-4 py-3 flex flex-wrap items-center gap-x-5 gap-y-2">
      <span className="eyebrow">{title}</span>
      {items.map(([n, t, note]) => (
        <span key={t} className="text-[14px] text-ink"><b className="font-display">{n}</b> {t}{note && <span className="text-muted"> ({note})</span>}</span>
      ))}
    </div>
  );
}

/** The lettered sub-step card (A, B, C …) with the yellow tile. */
export function Part({ letter, title, hint, aside, children }: { letter: string; title: string; hint?: string; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-[20px] bg-paper border-2 border-ink p-5 md:p-6 flex flex-col gap-4">
      <header className="flex items-start gap-3">
        <span className="shrink-0 w-10 h-10 rounded-[10px] bg-highlight text-ink font-display font-extrabold text-[20px] inline-flex items-center justify-center" aria-hidden>{letter}</span>
        <div className="flex-1 min-w-0">
          <h2 className="font-display font-extrabold text-[20px] sm:text-[22px] leading-tight tracking-[-0.4px] text-ink">{title}</h2>
          {hint && <p className="text-[14px] text-muted mt-0.5">{hint}</p>}
        </div>
        {aside}
      </header>
      {children}
    </section>
  );
}

/** The head of a guide step: its number, «Trin 2 af 5 · …», the title, a line of intro and «Du skal bruge». */
export function StepHead({ n, eyebrow, title, intro, need, needTitle }: { n: number; eyebrow: string; title: string; intro?: string; need?: [string, string, string?][]; needTitle?: string }) {
  return (
    <div className="flex flex-col gap-3 mb-6">
      <div className="flex items-center gap-4">
        <span className="shrink-0 w-14 h-14 rounded-[14px] bg-highlight text-ink font-display font-extrabold text-[30px] inline-flex items-center justify-center" aria-hidden>{n}</span>
        <div className="min-w-0">
          <span className="eyebrow">{eyebrow}</span>
          <h1 className="font-display font-extrabold text-[27px] sm:text-[30px] md:text-[40px] leading-[1.05] tracking-[-0.8px] sm:tracking-[-1px] text-ink">{title}</h1>
        </div>
      </div>
      {intro && <p className="text-[16px] text-ink-soft max-w-[620px]">{intro}</p>}
      {need && needTitle && <Need items={need} title={needTitle} />}
    </div>
  );
}
