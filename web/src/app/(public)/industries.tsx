"use client";
import { useState } from "react";
import { Icon } from "@/components/ui";

const PANELS: { key: string; tab: string; icon: string; title: string; ask: string; reply: string; results: string[] }[] = [
  { key: "craft", tab: "Håndværk & Byg", icon: "construction", title: "Gulvfirma & byggehåndværk",
    ask: "“Kan I give et overslag på slibning af 65 m² stuegulv?”",
    reply: "“Ja, standardprisen for afslibning og 2x lak er 145 kr./m² ekskl. moms. Skal vi aftale en uforpligtende opmåling?”",
    results: ["Besigtigelse foreslået ud fra jeres bookingregler.", "Opgave med adresse og areal samlet til mester."] },
  { key: "salon", tab: "Salon & Behandling", icon: "content_cut", title: "Frisør & skønhedsklinik",
    ask: "“Har I en ledig tid til herreklip i morgen efter kl. 16?”",
    reply: "“Der er en ledig tid i morgen kl. 16.30. Skal jeg reservere den i dit navn?”",
    results: ["Aftalen foreslås inden for jeres åbningstider.", "Kunden får en bekræftelse, når I har godkendt flowet."] },
  { key: "service", tab: "Service & Rådgivning", icon: "support_agent", title: "Konsulent & IT-service",
    ask: "“Jeg søger rådgivning om overgang til nyt regnskabssystem.”",
    reply: "“Det hjælper vi gerne med. Hvor mange brugere er I, og hvornår passer det at tage en kort introduktion?”",
    results: ["Henvendelsen kvalificeres med de spørgsmål, I har godkendt.", "Næste skridt samles til den rette rådgiver."] },
];

/** Industry switcher (Stitch P01 §3). The examples are illustrations, not live bookings. */
export function IndustrySwitcher() {
  const [active, setActive] = useState(PANELS[0].key);
  const p = PANELS.find((x) => x.key === active)!;
  return (
    <div className="max-w-4xl mx-auto flex flex-col gap-space-md">
      <div className="flex items-center justify-center gap-space-xs p-1 bg-surface-container rounded-xl self-stretch sm:self-center" role="tablist" aria-label="Brancheeksempler">
        {PANELS.map((x) => (
          <button key={x.key} role="tab" id={`tab-${x.key}`} aria-selected={x.key === active} aria-controls={`panel-${x.key}`} type="button" onClick={() => setActive(x.key)}
            className={`flex-1 sm:flex-none px-space-sm sm:px-space-md py-space-xs rounded-lg font-label-md text-label-md sm:font-label-lg sm:text-label-lg font-semibold transition-all ${x.key === active ? "bg-primary text-on-primary shadow-sm" : "text-on-surface-variant hover:text-on-surface"}`}>
            <span className="sm:hidden">{x.tab.split(" ")[0]}</span><span className="hidden sm:inline">{x.tab}</span>
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${p.key}`} aria-labelledby={`tab-${p.key}`} className="bg-surface-container-lowest rounded-xl p-space-md sm:p-space-lg shadow-sm">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-space-md md:gap-gutter-lg items-center">
          <div className="md:col-span-7 flex flex-col gap-space-md">
            <div className="flex items-center gap-space-xs text-primary font-semibold"><Icon name={p.icon} size={20} /><span className="font-label-lg text-label-lg">{p.title}</span></div>
            <div className="flex flex-col gap-space-sm bg-surface-container-low p-space-md rounded-lg">
              <div className="flex flex-col gap-0.5"><span className="font-label-sm text-label-sm text-on-surface-variant font-semibold">Kunde henvender sig:</span><p className="font-body-md text-body-md text-on-surface italic">{p.ask}</p></div>
              <div className="flex flex-col gap-0.5 pt-space-xs"><span className="font-label-sm text-label-sm text-primary font-semibold">Dialogbot svarer:</span><p className="font-body-md text-body-md text-on-surface">{p.reply}</p></div>
            </div>
          </div>
          <div className="md:col-span-5 bg-surface-container rounded-lg p-space-md flex flex-col gap-space-sm">
            <span className="font-label-sm text-label-sm text-primary font-semibold uppercase tracking-wider">Resultat</span>
            {p.results.map((r) => <div key={r} className="flex items-start gap-space-xs"><Icon name="check_circle" size={20} filled className="text-secondary mt-0.5" /><span className="font-body-sm text-body-sm text-on-surface">{r}</span></div>)}
          </div>
        </div>
      </div>
      <p className="text-center font-body-sm text-body-sm text-on-surface-variant">Brancherne er eksempler — Dialogbot sættes op efter jeres egne ydelser og arbejdsgange.</p>
    </div>
  );
}
