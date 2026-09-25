import Link from "next/link";

/** P01 (minimal): entry points for reception and campaigns; preserves product intent into signup (A01). */
export default function Home() {
  return (
    <main className="mx-auto max-w-4xl px-4 py-16">
      <p className="text-sm font-semibold uppercase tracking-wide text-primary">Dialogbot</p>
      <h1 className="mt-2 text-4xl font-extrabold text-primary-dark">AI-reception, callback og kampagner for danske virksomheder</h1>
      <p className="mt-4 max-w-2xl text-muted">Vælg, hvad du vil starte med. Dit valg følger med gennem oprettelsen, og du kan ændre det senere i opsætningen.</p>
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {[["reception", "Reception", "Telefon, webchat og bestilt callback besvaret af en assistent, der kun bruger godkendt viden."],
          ["campaigns", "Kampagner", "Udgående opfølgning i forudbetalte kontaktpakker. Betaling starter aldrig opkald."],
          ["both", "Begge dele", "Reception og kampagner i samme arbejdsrum med én vidensbase."]].map(([intent, title, text]) => (
          <Link key={intent} href={`/signup?intent=${intent}`} className="rounded-2xl border border-line bg-white p-5 shadow-sm hover:border-primary">
            <h2 className="text-lg font-bold text-primary-dark">{title}</h2>
            <p className="mt-2 text-sm text-muted">{text}</p>
            <span className="mt-4 inline-block text-sm font-semibold text-primary">Kom i gang →</span>
          </Link>
        ))}
      </div>
      <p className="mt-10 text-sm text-muted">Har du allerede en konto? <Link className="font-semibold text-primary underline" href="/login">Log ind</Link></p>
      <p className="mt-2 text-xs text-muted">Priser, demo og hjælpecenter (P02–P09) tilføjes i de næste milepæle; ingen vilkår eller garantier vises, før de er godkendt.</p>
    </main>
  );
}
