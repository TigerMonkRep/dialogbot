"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type ApiError } from "@/lib/client";
import { EMAIL, HOURS, PHONE_DISPLAY, PHONE_TEL } from "@/lib/contact";
import { ArrowIcon, CloseIcon, PhoneIcon } from "@/components/site-icons";

/** The "Prøv den" conversation (Proev.dc.html): start → firma → branche (→ andet) → tlf → calling → done.
 *  The call is REAL: POST /demo-call (app/modules/sales) rings the number with our sales assistant. It needs the
 *  visitor's consent (markedsføringsloven § 10), only works inside the calling hours and only while demo calls are
 *  switched on, so the chat reads GET /demo-call first and says honestly when it cannot ring – it never pretends. */
type Info = {
  available: boolean; demo_number: string | null; open_now: boolean; hours: { from: string; to: string };
  consent_text: string; consent_version: string; industries: { key: string; label: string }[];
};
type Step = "start" | "firma" | "branche" | "andet" | "tlf" | "calling" | "done" | "unavailable";
type Msg = { from: "bot" | "user"; text: string };

/** Chip label → the backend's industry key (app/modules/sales/script.py). "Noget andet" asks for the visitor's own words. */
const BRANCHES: [string, string | null][] = [
  ["Håndværker", "haandvaerk"], ["Klinik", "klinik"], ["Frisør / salon", "skoenhed"], ["Restaurant", "restaurant"], ["Rådgiver", "raadgivning"], ["Noget andet", null],
];
const GREETING = "Hej! Jeg hedder Peter og er Dialogbots digitale receptionist. Vil du høre, hvordan jeg lyder, når jeg tager telefonen for din virksomhed?";
const STEP_LABEL: Record<Step, string> = {
  start: "Start", firma: "Trin 1 · hvem er I", branche: "Trin 1 · hvad laver I", andet: "Trin 1 · hvad laver I",
  tlf: "Trin 2 · dit nummer", calling: "Trin 2 · ringer", done: "Trin 3 · byg din egen", unavailable: "Ikke lige nu",
};
/** How long the phone card shows "ringer" before the chat moves on. We cannot see when the call ends. */
const CALL_WINDOW_MS = 45_000;

/** "+4570123456" → "70 12 34 56" */
function pretty(e164: string) {
  const d = e164.replace(/^\+45/, "");
  return d.length === 8 ? d.replace(/(\d{2})(?=\d)/g, "$1 ") : e164;
}

const chip = "min-h-11 px-4 rounded-full bg-white border-2 border-ink text-ink font-semibold text-[15px] cursor-pointer hover:bg-panel";
const avatar = "flex-none w-[30px] h-[30px] rounded-full bg-accent inline-flex items-center justify-center font-display font-extrabold text-[13px] text-white";

/** `embedded`: the chat stage alone, filling its container (the floating widget on every other page) – no side
 *  column, the log scrolls, and the header gets a close button. Default: the full /proev layout with the aside. */
export function ProevChat({ embedded = false, onClose }: { embedded?: boolean; onClose?: () => void } = {}) {
  const [info, setInfo] = useState<Info | null | "error">(null);
  const [step, setStep] = useState<Step>("start");
  const [history, setHistory] = useState<Msg[]>([{ from: "bot", text: GREETING }]);
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [firma, setFirma] = useState("");
  const [industry, setIndustry] = useState<{ key: string | null; other: string }>({ key: null, other: "" });
  const [tlf, setTlf] = useState("");
  const [consent, setConsent] = useState(false);
  const [consentError, setConsentError] = useState(false);
  const [pending, setPending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    api<Info>("/demo-call").then((i) => setInfo({ ...i, industries: i.industries ?? [] })).catch(() => setInfo("error"));
    const t = timers.current;
    return () => t.forEach(clearTimeout);
  }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [history, typing]);
  useEffect(() => { if (step === "firma" || step === "andet" || step === "tlf") inputRef.current?.focus(); }, [step]);

  const push = useCallback((m: Msg) => setHistory((h) => h.concat(m)), []);
  const later = useCallback((fn: () => void, ms: number) => { timers.current.push(window.setTimeout(fn, ms)); }, []);
  /** The bot "types" for 700 ms, then answers and moves to the next step. */
  const botSays = useCallback((text: string, next?: Step, ms = 700) => {
    setTyping(true);
    later(() => { setTyping(false); push({ from: "bot", text }); if (next) setStep(next); }, ms);
  }, [later, push]);

  /** Why we cannot ring right now – or null when we can. Honest copy; never claims a call was placed. */
  const blocker = (): string | null => {
    if (info === null) return null; // still loading: ask on, check again before dialling
    if (info === "error" || !info.available) {
      return `Prøveopkaldet aktiveres snart – indtil da ringer vi til dig manuelt inden for åbningstiden. Ring til os på ${PHONE_DISPLAY} (${HOURS.toLowerCase()}), eller skriv dit nummer til ${EMAIL}, så ringer vi til dig.`;
    }
    if (!info.open_now) {
      const own = info.demo_number ? ` Du kan også selv ringe til mit demonummer ${pretty(info.demo_number)}.` : "";
      return `Jeg ringer kun op mellem kl. ${info.hours.from} og ${info.hours.to} på hverdage. Kom tilbage der – eller skriv dit nummer til ${EMAIL}, så ringer vi til dig inden for åbningstiden.${own}`;
    }
    return null;
  };

  const startChips = [
    { label: "Ja, ring til mig", act: () => {
      push({ from: "user", text: "Ja, ring til mig" });
      const why = blocker();
      if (why) botSays(why, "unavailable"); else botSays("Super. Hvad hedder din virksomhed?", "firma");
    } },
    { label: "Hvad kan du?", act: () => { push({ from: "user", text: "Hvad kan du?" }); botSays("Jeg tager telefonen døgnet rundt, svarer på det, kunderne oftest spørger om, booker tider i din kalender og sender dig en besked, hvis der er noget, jeg ikke kan klare.\n\nVil du høre det selv?", "start"); } },
    { label: "Hvad koster det?", act: () => { push({ from: "user", text: "Hvad koster det?" }); botSays("Ét abonnement fra 2.495 kr. om måneden, ekskl. moms. Opsætningen kan I gøre selv – det er med. Vil I have vores specialister til at skræddersy den til jeres systemer, koster det 5.000 kr. én gang.\n\nSkal jeg ringe og vise dig, hvad du får?", "start"); } },
  ];
  const chooseBranch = (label: string, key: string | null) => () => {
    push({ from: "user", text: label });
    setIndustry({ key, other: "" });
    if (key === null) botSays("Skriv kort, hvad I laver – så ved jeg, hvordan jeg skal tage imod kunderne.", "andet");
    else botSays(`Så er jeg receptionist for ${firma} fra nu af. Hvilket nummer skal jeg ringe til?`, "tlf");
  };

  const reset = () => {
    timers.current.forEach(clearTimeout); timers.current = [];
    setStep("start"); setHistory([{ from: "bot", text: GREETING }]); setTyping(false); setDraft(""); setFirma("");
    setIndustry({ key: null, other: "" }); setTlf(""); setConsent(false); setConsentError(false); setPending(false);
  };

  /** Anything that is not one of the scripted steps goes to Peter himself: POST /demo-call/chat answers from the
   *  sales workspace's approved knowledge. The step does not change, so the chips stay where they were. */
  const ask = async (v: string) => {
    push({ from: "user", text: v }); setDraft(""); setPending(true); setTyping(true);
    const messages = history.concat({ from: "user", text: v }).slice(-16)
      .map((m) => ({ role: m.from === "bot" ? "assistant" : "user", content: m.text.slice(0, 600) }));
    try {
      const r = await api<{ reply: string }>("/demo-call/chat", { method: "POST", body: JSON.stringify({ messages, website: "" }) });
      setTyping(false); push({ from: "bot", text: r.reply });
    } catch (err) {
      setTyping(false);
      const a = err as ApiError;
      push({ from: "bot", text: a?.code === "demo_unavailable"
        ? `Chatten er ikke helt klar endnu. Ring til os på ${PHONE_DISPLAY} (${HOURS.toLowerCase()}) eller skriv til ${EMAIL} – så svarer vi.`
        : `Det kunne jeg ikke svare på lige nu. Prøv igen om lidt, eller ring til os på ${PHONE_DISPLAY}.` });
    } finally { setPending(false); }
  };

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const v = draft.trim();
    if (!v || pending) return;
    if (step === "start" || step === "unavailable" || step === "calling" || step === "done") { await ask(v); return; }
    if (step === "branche") {
      push({ from: "user", text: v }); setDraft(""); setIndustry({ key: null, other: v });
      botSays(`Så er jeg receptionist for ${firma} fra nu af. Hvilket nummer skal jeg ringe til?`, "tlf");
      return;
    }
    if (step === "tlf" && !/\d{8}/.test(v.replace(/[\s+\-()]/g, ""))) { await ask(v); return; }
    if (step === "firma") {
      push({ from: "user", text: v }); setFirma(v); setDraft("");
      botSays(`Hej ${v}. Hvad laver I?`, "branche");
      return;
    }
    if (step === "andet") {
      push({ from: "user", text: v }); setIndustry((i) => ({ ...i, other: v })); setDraft("");
      botSays(`Så er jeg receptionist for ${firma} fra nu af. Hvilket nummer skal jeg ringe til?`, "tlf");
      return;
    }
    if (step !== "tlf") return;
    if (!consent) { setConsentError(true); return; }
    const why = blocker();
    push({ from: "user", text: v }); setTlf(v); setDraft("");
    if (why || info === null || info === "error") { botSays(why ?? "Jeg kunne ikke få fat i opkaldstjenesten. Prøv igen om lidt.", "unavailable"); return; }
    setPending(true); setTyping(true);
    try {
      await api("/demo-call", { method: "POST", body: JSON.stringify({
        phone: v, company: firma, consent: true, consent_version: info.consent_version, website: "",
        industry: industry.key ?? "andet", industry_other: industry.key ? null : industry.other || null }) });
      setTyping(false);
      push({ from: "bot", text: `Jeg ringer til ${v} nu – du får et opkald fra Peter fra Dialogbot inden for et minut. Tag den, og spørg mig om alt det, en kunde ville spørge ${firma} om.` });
      setStep("calling");
      later(() => botSays(`Opkaldet er sendt til din telefon. Ringede den ikke? Så ring til os på ${PHONE_DISPLAY}, så viser vi det live.\n\nVil du bygge din egen? Det tager 3 trin og ca. 30 minutter, og jeg guider dig hele vejen.`, "done"), CALL_WINDOW_MS);
    } catch (err) {
      setTyping(false);
      const a = err as ApiError;
      const msg = a?.message || "Vi kunne ikke ringe op lige nu. Prøv igen om lidt.";
      if (a?.code === "demo_unavailable") botSays(msg, "unavailable");
      else botSays(`${msg} Skriv nummeret igen, eller ring selv til os på ${PHONE_DISPLAY}.`, "tlf");
    } finally { setPending(false); }
  };

  const hasInput = true; // the chips are shortcuts; the visitor can always write to Peter instead
  const placeholder = step === "firma" ? "Fx Nørgaard Tømrer" : step === "andet" ? "Fx tømrer, tandlæge, bogholder …"
    : step === "tlf" ? "Fx 93 70 34 33 – eller stil et spørgsmål" : step === "branche" ? "Vælg ovenfor – eller skriv, hvad I laver"
    : "Skriv dit spørgsmål til Peter …";
  const done = step === "done";
  const calling = step === "calling";
  const pastOne = step === "tlf" || calling || done;
  const consentText = info && info !== "error" ? info.consent_text
    : "Ja tak, Peter fra Dialogbot, en digital assistent, må ringe mig op på dette nummer nu og vise, hvordan Dialogbot tager telefonen. Opkaldet bliver skrevet ned, og en medarbejder fra Dialogbot må kontakte mig bagefter om det, vi talte om.";

  const phone = calling ? null
    : done ? ["Opkaldet er sat i gang", "Var det noget? Så er din egen receptionist tre trin væk."]
    : step === "unavailable" ? ["Prøveopkaldet aktiveres snart", `Indtil da ringer vi til dig manuelt inden for åbningstiden (${HOURS.toLowerCase()}). Ring til ${PHONE_DISPLAY} eller skriv til ${EMAIL}.`]
    : ["Din telefon ringer snart", "Når du har skrevet dit nummer i chatten, ringer Peter fra Dialogbot inden for et minut."];

  const stage = (
      <section aria-label="Chat med Dialogbot"
        className={`min-w-0 bg-white flex flex-col overflow-hidden ${embedded
 ?"h-full w-full"
 :"flex-[1_1_460px] max-w-[640px] border-2 border-ink rounded-[22px] shadow-block"}`}>
        <div className="flex items-center gap-3 px-4 py-3 sm:px-5 sm:py-4 border-b-2 border-ink">
          <span className="inline-flex w-10 h-10 rounded-xl bg-accent items-center justify-center font-display font-extrabold text-white text-lg">D</span>
          <div className="flex flex-col min-w-0">
            <span className="font-display font-bold text-[17px]">Dialogbot</span>
            <span className="text-[13px] text-muted flex items-center gap-1.5"><span aria-hidden className="w-2 h-2 rounded-full bg-[#1B9E5A]" />Svarer med det samme</span>
          </div>
          <span className={`ml-auto text-xs font-semibold tracking-[1.5px] uppercase px-2.5 py-1.5 rounded-full bg-highlight ${embedded ? "hidden sm:inline" : ""}`} aria-live="polite">{STEP_LABEL[step]}</span>
          {onClose && (
            <button type="button" onClick={onClose} aria-label="Luk chatten" className={`w-11 h-11 rounded-[10px] bg-white inline-flex items-center justify-center text-ink hover:bg-panel cursor-pointer ${embedded ? "ml-auto sm:ml-0" : "ml-2"}`}>
              <CloseIcon size={18} />
            </button>
          )}
        </div>

        <div className={`flex flex-col gap-3 p-4 sm:p-5 bg-white ${embedded ? "flex-1 min-h-0 overflow-y-auto" : "min-h-[360px]"}`} role="log" aria-live="polite">
          {history.map((m, i) => {
            const bot = m.from === "bot";
            return (
              <div key={i} className={`flex gap-2.5 items-end ${bot ? "" : "justify-end"}`}>
                {bot && <span className={avatar}>D</span>}
                <p className={`m-0 px-4 py-3 text-[15px] leading-normal max-w-[420px] whitespace-pre-line border-2 border-ink ${bot ? "rounded-[16px_16px_16px_4px] bg-white text-ink" : "rounded-[16px_16px_4px_16px] bg-ink text-white"}`}>{m.text}</p>
              </div>
            );
          })}
          {typing && (
            <div className="flex gap-2.5 items-end" aria-label="Dialogbot skriver">
              <span className={avatar}>D</span>
              <span className="inline-flex gap-[5px] px-4 py-3.5 rounded-[16px_16px_16px_4px] bg-white border-2 border-ink">
                <span className="dot1 w-[7px] h-[7px] rounded-full bg-ink" /><span className="dot2 w-[7px] h-[7px] rounded-full bg-ink" /><span className="dot3 w-[7px] h-[7px] rounded-full bg-ink" />
              </span>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="flex flex-col gap-3 px-4 pt-4 pb-5 sm:px-5 border-t-2 border-ink bg-panel">
          {step === "start" && !typing && (
            <div className="flex flex-wrap gap-2">{startChips.map((q) => <button key={q.label} type="button" onClick={q.act} className={chip}>{q.label}</button>)}</div>
          )}
          {(step === "done" || step === "unavailable" || step === "calling") && !typing && null}
          {step === "branche" && !typing && (
            <div className="flex flex-wrap gap-2">{BRANCHES.map(([l, k]) => <button key={l} type="button" onClick={chooseBranch(l, k)} className={chip}>{l}</button>)}</div>
          )}
          {step === "unavailable" && !typing && (
            <div className="flex flex-wrap gap-2">
              <a href={PHONE_TEL} className={`${chip} inline-flex items-center gap-2 no-underline`}><PhoneIcon size={16} />Ring til os</a>
              <a href={`mailto:${EMAIL}?subject=${encodeURIComponent("Ring mig op – prøveopkald")}`} className={`${chip} inline-flex items-center no-underline`}>Skriv dit nummer til os</a>
              <Link href="/byggevejledning" className={`${chip} inline-flex items-center no-underline`}>Se byggevejledningen</Link>
              <button type="button" onClick={reset} className={chip}>Prøv igen</button>
            </div>
          )}
          {hasInput && (
            <form onSubmit={send} className="flex flex-col gap-3">
              <div className="flex gap-2.5">
                <label htmlFor="chat-input" className="sr-only">{placeholder}</label>
                <input ref={inputRef} id="chat-input" type="text" inputMode={step === "tlf" ? "tel" : "text"} value={draft}
                  onChange={(e) => setDraft(e.target.value)} placeholder={placeholder} autoComplete={step === "tlf" ? "tel" : "organization"} disabled={pending}
                  className="flex-1 min-w-0 min-h-12 px-4 rounded-xl border-2 border-ink text-base text-ink bg-white placeholder:text-muted/70" />
                <button type="submit" disabled={pending} className="inline-flex items-center gap-2 min-h-12 px-[18px] rounded-xl bg-accent hover:bg-accent-deep text-white font-semibold text-[15px] cursor-pointer disabled:opacity-60">
                  {step === "tlf" && /\d{8}/.test(draft.replace(/[\s+\-()]/g, "")) ? "Ring mig op" : "Send"}<ArrowIcon size={16} />
                </button>
              </div>
              {step === "tlf" && (
                <>
                  {/* Honeypot: hidden from people, filled by bots; the backend then stores nothing and calls nobody. */}
                  <input type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden className="hidden" defaultValue="" />
                  <label className={`flex items-start gap-3 text-[13px] leading-normal cursor-pointer ${consentError ? "text-danger" : "text-ink-soft"}`}>
                    <input type="checkbox" checked={consent} onChange={(e) => { setConsent(e.target.checked); if (e.target.checked) setConsentError(false); }}
                      className="mt-0.5 w-5 h-5 shrink-0 accent-accent" aria-invalid={consentError} />
                    <span>{consentText}{consentError && <b className="block mt-1">Sæt kryds, hvis jeg må ringe dig op.</b>}</span>
                  </label>
                </>
              )}
            </form>
          )}
          {done && (
            <div className="flex flex-wrap gap-2.5">
              <Link href="/signup" className="inline-flex items-center gap-2.5 min-h-12 px-5 rounded-xl bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[15px]">Ja – byg min nu (trin 1 af 3)</Link>
              <button type="button" onClick={reset} className="min-h-12 px-[18px] rounded-xl bg-white border-2 border-ink text-ink font-semibold text-[15px] cursor-pointer hover:bg-panel">Prøv igen</button>
            </div>
          )}
          {calling && <p className="m-0 text-sm font-semibold">Tag telefonen, når den ringer. Du kan lægge på når som helst.</p>}
          <span className="text-xs text-muted">Vi ringer kun til det nummer, du selv skriver, og bruger det ikke til andet end dette opkald og en opfølgning, hvis du har sagt ja til det.</span>
        </div>
      </section>
  );

  if (embedded) return stage;

  return (
    <div className="flex flex-wrap gap-8 items-start">
      {stage}

      {/* SIDE: what happens */}
      <aside className="flex-[1_1_320px] min-w-0 flex flex-col gap-5">
        <div className="bg-white border-2 border-ink rounded-[20px] p-6 flex flex-col gap-4 items-center text-center min-h-[250px] justify-center" aria-live="polite">
          {calling ? (
            <>
              <div className="relative w-24 h-24 flex items-center justify-center">
                <span aria-hidden className="ringwave absolute inset-0 rounded-full border-[3px] border-accent" />
                <span aria-hidden className="ringwave2 absolute inset-0 rounded-full border-[3px] border-accent" />
                <span className="w-[72px] h-[72px] rounded-full bg-accent inline-flex items-center justify-center"><PhoneIcon size={32} stroke="#FFFFFF" /></span>
              </div>
              <span className="font-display font-bold text-xl">Ringer til {tlf} …</span>
              <span className="text-sm text-ink-soft">Jeg præsenterer mig som receptionist for <b>{firma}</b>. Spørg mig om priser, tider eller en aftale.</span>
            </>
          ) : (
            <>
              <span className="inline-flex w-[72px] h-[72px] rounded-full bg-panel border-2 border-ink items-center justify-center"><PhoneIcon size={32} /></span>
              <span className="font-display font-bold text-xl">{phone![0]}</span>
              <span className="text-sm text-ink-soft">{phone![1]}</span>
            </>
          )}
        </div>

        <ol className="m-0 p-0 list-none flex flex-col gap-2.5">
          {([["1", "Fortæl chatten, hvem I er", true], ["2", "Tag telefonen – spørg som en kunde", pastOne], ["3", "Kan du lide det? Så bygger vi den rigtige", done]] as [string, string, boolean][]).map(([n, t, on]) => (
            <li key={n} className="flex gap-3 items-center px-3.5 py-3 rounded-[14px] bg-white border-2 border-ink">
              <span className={`flex-none inline-flex w-9 h-9 rounded-[10px] items-center justify-center font-display font-extrabold text-lg ${on ? "bg-highlight" : "bg-panel"}`}>{n}</span>
              <span className="text-[15px] font-semibold">{t}</span>
            </li>
          ))}
        </ol>

        <p className="m-0 text-[13px] leading-normal text-muted">Den samme chat følger dig videre: Når du siger ja, guider den dig gennem opsætningen, kobler din kalender på og tester det hele sammen med dig.</p>
      </aside>
    </div>
  );
}
