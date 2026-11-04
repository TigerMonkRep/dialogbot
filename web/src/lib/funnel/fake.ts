"use client";
/** In-browser simulation of the funnel API (same interface as ./api.ts). Used with NEXT_PUBLIC_FUNNEL_FAKE=1 and when
 *  the real API is missing (404). Drafts live in sessionStorage; the build "progresses" with real time (one row per
 *  1.5 s), the SMS code is always 123456, the demo call "ends" ~6 s after the reveal page starts polling.
 *  Nothing here calls anyone or writes anything outside the browser. */
import { FAKE_SMS_CODE } from "@/lib/privat/fake";
import { localEstimate, type Answers, type BuildErhverv, type BuildPrivat, type Draft, type FunnelApi, type Industry, type Place } from "./api";

const KEY = "dialogbot-funnel-fake";
type Row = Draft & { created: number; built_at: number | null; gate: { name: string; email: string; phone: string } | null; verified_at: number | null; reveal_from: number | null };
type Store = Record<string, Row>;

const fail = (status: number, code: string, message: string): never => { throw { status, code, message }; };
const wait = (ms = 60) => new Promise<void>((r) => setTimeout(r, ms));
function load(): Store { try { return JSON.parse(sessionStorage.getItem(KEY) ?? "{}") as Store; } catch { return {}; } }
function save(s: Store) { try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ignore */ } }
function row(id: string): Row { const r = load()[id]; return r ?? fail(404, "not_found", "Udkastet findes ikke længere"); }
function put(r: Row) { const s = load(); s[r.id] = r; save(s); }

const PLACES: Place[] = [
  { place_id: "fake-fjordgulv", name: "Fjordgulv ApS", address: "Havnegade 12, 8000 Aarhus C", phone_display: "86 12 34 56", website: "https://fjordgulv.example", open_now: true },
  { place_id: "fake-klinik-holm", name: "Klinik Holm", address: "Søndergade 20, 8000 Aarhus C", phone_display: "86 11 22 33", website: "https://klinikholm.example", open_now: true },
  { place_id: "fake-salon", name: "Salon Klip & Krøl", address: "Mejlgade 21, 8000 Aarhus C", phone_display: "28 91 44 12", website: null, open_now: false },
  { place_id: "fake-vaerksted", name: "Nørre Auto", address: "Nørre Allé 5, 8000 Aarhus C", phone_display: "86 98 76 54", website: "https://norreauto.example", open_now: true },
];

export function PRIVAT_TASKS(answers: Answers): BuildPrivat {
  const postponed = answers.postponed ?? [];
  const calls = postponed.filter((p) => ["dentist", "bike", "car_inspection", "doctor", "hairdresser", "landlord"].includes(p));
  const household = answers.household;
  const lists = 1 + (household === "kids" ? 1 : 0) + (household === "parents" ? 1 : 0);
  const first = calls[0];
  const titles: Record<string, string> = {
    dentist: "Bestil tid hos tandlægen", bike: "Få cyklen til eftersyn", car_inspection: "Book bilsyn", doctor: "Bestil tid hos lægen",
    hairdresser: "Bestil tid hos frisøren", landlord: "Ring til udlejer om det, der venter",
  };
  return { tasks: postponed.length, lists, first_call: first ? { title: titles[first] ?? first } : null };
}

function buildOf(r: Row, now: number): Draft["build"] {
  if (r.kind === "privat") return r.step >= 4 ? PRIVAT_TASKS(r.answers) : null;
  if (r.step < 4 || r.built_at === null) return null;
  const n = Math.floor((now - r.built_at) / 1500);
  const b: BuildErhverv = {
    knowledge: n >= 3 ? (r.company?.website ? "done" : "skipped") : "pending",
    voice: n >= 1 ? "done" : "pending",
    hours: n >= 2 ? (r.company?.opening_hours_text ? "done" : "default") : "pending",
    number: n >= 4 ? "done" : "pending",
  };
  return b;
}

function view(r: Row): Draft {
  const { created, built_at, gate, verified_at, reveal_from, ...d } = r;
  void created; void built_at; void gate; void verified_at; void reveal_from;
  return { ...d, build: buildOf(r, Date.now()) };
}

export const fakeFunnel: FunnelApi = {
  async create(body) {
    await wait();
    const id = `fake-${Math.random().toString(36).slice(2, 10)}`;
    const r: Row = {
      id, kind: body.kind, hook: body.hook ?? null, step: 0, answers: body.industry ? { industry: body.industry as Industry } : {},
      company: null, estimate: null, build: null, gated: false, expires_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
      created: Date.now(), built_at: null, gate: null, verified_at: null, reveal_from: null,
    };
    put(r);
    return view(r);
  },
  async get(id) { await wait(); return view(row(id)); },
  async patch(id, step, answers) {
    await wait();
    const r = row(id);
    r.answers = { ...r.answers, ...answers };
    r.step = Math.max(r.step, step);
    if (r.kind === "erhverv") {
      if (step === 2 && answers.company_name) {
        const p = PLACES.find((x) => x.place_id === answers.place_id);
        r.company = p ? { name: p.name, address: p.address, phone_display: p.phone_display, website: p.website, opening_hours_text: p.open_now ? "Man–fre 08–16" : null, place_id: p.place_id }
          : { name: String(answers.company_name), address: null, phone_display: null, website: null, opening_hours_text: null, place_id: null };
      }
      if (step === 3) {
        const est = localEstimate(r.answers.industry, r.answers.missed ?? []);
        r.estimate = { missed_per_week: typeof answers.missed_per_week === "number" ? answers.missed_per_week : est.missed_per_week, source: est.source };
      }
      if (step === 4 && r.built_at === null) r.built_at = Date.now();
    }
    put(r);
    return view(r);
  },
  async places(q, industry) {
    await wait(120);
    const low = q.trim().toLowerCase();
    if (low.length < 2) return [];
    const hits = PLACES.filter((p) => p.name.toLowerCase().includes(low));
    if (hits.length) return hits;
    const name = q.trim().replace(/^\p{Ll}/u, (c) => c.toUpperCase());
    const suffix = industry === "klinik" ? "Klinik" : industry === "salon" ? "Salon" : industry === "restaurant" ? "Restaurant" : "ApS";
    return [{ place_id: `fake-${low.replace(/\W+/g, "-")}`, name: `${name} ${suffix}`, address: "Åboulevarden 1, 8000 Aarhus C", phone_display: "86 00 00 00", website: null, open_now: true }];
  },
  async gate(id, body) {
    await wait(200);
    const r = row(id);
    if (body.website) return { status: "code_sent", phone_display: body.phone };
    if (!body.consent) fail(422, "validation_failed", "Sæt kryds for at fortsætte");
    if (!/^\+?\d[\d ]{7,}$/.test(body.phone.trim())) throw { status: 422, code: "validation_failed", message: "Skriv et mobilnummer med 8 cifre", field_errors: [{ field: "phone", message: "Skriv et mobilnummer med 8 cifre" }] };
    r.gate = { name: body.name, email: body.email, phone: body.phone };
    put(r);
    const digits = body.phone.replace(/\D/g, "").slice(-8);
    return { status: "code_sent", phone_display: digits.replace(/(\d{2})(?=\d)/g, "$1 ") };
  },
  async verify(id, code) {
    await wait(300);
    const r = row(id);
    if (!r.gate) fail(409, "gate_missing", "Udfyld dine oplysninger først");
    if (code !== FAKE_SMS_CODE) throw { status: 422, code: "code_invalid", message: "Koden passer ikke. Prøv igen.", field_errors: [{ field: "code", message: "Koden passer ikke" }] };
    r.gated = true; r.verified_at = Date.now(); r.reveal_from = Date.now();
    put(r);
    if (r.kind === "privat") { try { sessionStorage.setItem("dialogbot-privat-fake-login", "1"); } catch { /* ignore */ } }
    return { status: "ok", next: r.kind === "privat" ? "/privat/dag?velkommen=1" : "/start/klar" };
  },
  async reveal(id) {
    await wait();
    const r = row(id);
    if (!r.gated) fail(401, "unauthorized", "Log ind først");
    const since = Date.now() - (r.reveal_from ?? Date.now());
    const name = r.company?.name ?? r.answers.company_name ?? "jer";
    const call = since < 3000 ? { status: "dialling", summary: null, duration_seconds: null }
      : since < 7000 ? { status: "in_progress", summary: null, duration_seconds: null }
      : { status: "answered", summary: `Kunden ringede til ${name} og spurgte om en tid i næste uge. Receptionisten tilbød torsdag kl. 10 og tog navn og nummer, så I kan ringe tilbage.`, duration_seconds: 74 };
    return { call, workspace_id: "fake-workspace" };
  },
};
