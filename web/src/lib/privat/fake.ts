"use client";
/** In-browser simulation of the Privat API (same interface as ./api.ts) with the prototype's example data and rules
 *  (design-reference/privat/Main.dc.html):
 *  - 10 free everyday tasks a month (starts at 8/10), 3 welcome credits;
 *  - edits, ticking off, questions and "what is waiting" are free; task #11 becomes a draft that waits for
 *    credit / purchase / sponsor clip / later;
 *  - approving a call reserves 3 credits; simulated outcome answered (3 credits charged) or no answer (released);
 *  - purchases are simulated, and repeating the last payment signal adds nothing.
 *  Used when NEXT_PUBLIC_PRIVAT_FAKE=1, when the real API is missing (404/feature disabled), and – read-only, as
 *  example data – for visitors who are not logged in. Content text is Danish, like the backend's. State lives in
 *  sessionStorage so it survives navigation and reloads in the tab. */
import { bareLink, prettyPhone } from "./sms";
import { PLANS, TRIAL_DAYS, apiPlans } from "./plans";
import { creditPackPrice, currencyFor, currencyOr, formatPrice, type Currency } from "@/lib/markets";
import { ADDON, type Addon, type ApproveBody, type Balance, type BillingInterval, type ChatMessage, type ChatOption, type Day, type InvitePreview, type LedgerEntry, type ListType,
  type Member, type Plan, type PlanKey, type PrivatApi, type Referrals, type Group, type GroupMember, type InviteStatus, type ShareGroupResult, type Subscription, type SubscriptionPlan, type SubscriptionStatus,
  type SuggestedPerson, type SendResult, type Task, type TaskItem, type TaskStatus, type GiverGroupGift, type OwnerGroupGift, type WishBody, type WishDesign } from "./api";
import WISH_THEMES from "./wish-themes.json";

export const FAKE_SMS_CODE = "123456";
const FREE_LIMIT = 0; // no free tasks any more: without a plan the account only reads lists shared with it
const CALL_CREDITS = 3;
const SPONSOR_PER_DAY = 2;

type Shop = { name: string; address: string; phone: string | null; price: string; open: boolean; next?: string; rating: number; count: number; km: number };
/** Fictional demo businesses (like the backend's DemoPlaces without a Google key) – never callable. */
const SHOPS: Record<string, Shop> = {
  cykelmageren: { name: "Cykelmageren", address: "Nørregade 12, 8000 Aarhus C", phone: "86 12 34 56", price: "450 kr. for et almindeligt eftersyn", open: true, rating: 4.7, count: 213, km: 0.6 },
  oestbyen: { name: "Østbyens Cykler", address: "Østergade 3, 8000 Aarhus C", phone: "86 98 76 54", price: "395 kr. for et almindeligt eftersyn", open: false, next: "tors. kl. 8.00", rating: 4.5, count: 88, km: 1.2 },
  hjoernet: { name: "Cykelhjørnet", address: "Jægergårdsgade 40, 8000 Aarhus C", phone: null, price: "Ikke oplyst", open: true, rating: 4.2, count: 41, km: 1.9 },
  fona: { name: "Fona Bruuns Galleri", address: "M.P. Bruuns Gade 25, 8000 Aarhus C", phone: "86 13 00 00", price: "Ikke oplyst", open: true, rating: 4.1, count: 156, km: 0.4 },
  fonaS: { name: "Fona Strøget", address: "Søndergade 42, 8000 Aarhus C", phone: "86 12 00 00", price: "Ikke oplyst", open: false, next: "i morgen kl. 10.00", rating: 4.0, count: 97, km: 0.9 },
  frisoer: { name: "Salon Klip & Krøl", address: "Mejlgade 21, 8000 Aarhus C", phone: "28 91 44 12", price: "Ikke oplyst", open: true, rating: 4.8, count: 64, km: 0.8 },
};
const MOBILE = /^\+45(2\d|30|31|40|41|42|50|51|52|53|60|61|71|81|91|92|93)/;
export const isDanishMobile = (e164: string | null | undefined) => !!e164 && MOBILE.test(e164);
const e164 = (display: string | null) => (display ? `+45${display.replace(/\D/g, "").slice(-8)}` : null);
function findShops(text: string): string[] {
  const low = text.toLowerCase();
  if (/cykel/.test(low)) return ["cykelmageren", "oestbyen", "hjoernet"];
  if (/fona/.test(low)) return ["fona", "fonaS"];
  if (/fris(ø|o)r/.test(low)) return ["frisoer", "hjoernet"];
  return ["cykelmageren", "frisoer"];
}
type Meta = { kind: "shops" | "prefill" | "decide" | "mkgroup" | "where"; query?: string; groupName?: string; win?: string; taskId?: string; answered?: boolean };
type Pending = { status: TaskStatus; next: string; intro: string };
/** Simulated subscription: a 14-day trial with Plus rights from the first use; checkout activates the chosen plan
 *  after a fake redirect (the session id carries plan and interval). Calls count per calendar month. */
type Sub = { plan: SubscriptionPlan; status: SubscriptionStatus; interval: BillingInterval | null; trialStart: string | null; periodEnd: string | null; cancelAtPeriodEnd: boolean;
  callsMonth: string; callsUsed: number; checkouts: Record<string, { plan: PlanKey; interval: BillingInterval; currency?: Currency }>; currency?: Currency };
type State = {
  v: 8; sub: Sub; packCurrency?: Currency; quotaCalls: Record<string, true>; location: string | null; push: string[]; joinLinks: Record<string, string>; groups: Group[]; status: Record<string, (InviteStatus & { key: string })[]>; ref: { invited: number; joined: number; activated: number; credits_earned: number; viaInvite: string | null; selfRewarded: boolean; annaJoined: boolean; annaRewarded: boolean };
  addons: Record<string, boolean>; invites: Record<string, string>; reservations: Record<string, "me" | "other">;
  /** Simulated group gifts on wishes others shared with me: the others' pledges are one simulated sum. */
  gifts?: Record<string, FakeGift>;
  invitable: Record<string, Task>; n: number; freeUsed: number; credits: number; reserved: number; sponsorDay: string; sponsorUsed: number;
  phone: string | null; phoneVerified: boolean; phonePending: string | null;
  tasks: Task[]; msgs: ChatMessage[]; ledger: LedgerEntry[]; paySeq: number; lastPay: string | null;
  meta: Record<string, Meta>; pending: Record<string, Pending>; prices: Record<string, string>;
};

type FakeGift = { target: number; currency: string; others: number; othersCount: number; mine: number | null; status: "open" | "bought" | "cancelled"; coordinator: "me" | "other" | null; pendingMe: boolean };

type FakeError = { status: number; code: string; message: string };
const fail = (status: number, code: string, message: string): never => { throw { status, code, message } as FakeError; };
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
const wait = () => new Promise<void>((r) => setTimeout(r, 40));

// ---------- dates (Danish wording, like the backend's texts) ----------
function atDay(offset: number, h: number, m = 0): string {
  const d = new Date(); d.setDate(d.getDate() + offset); d.setHours(h, m, 0, 0); return d.toISOString();
}
/** Days until the next given weekday (0 = Sunday … 6 = Saturday), 1–7. */
function daysTo(weekday: number): number { const diff = (weekday - new Date().getDay() + 7) % 7; return diff === 0 ? 7 : diff; }
const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
function dayOffset(iso: string): number {
  const a = new Date(); a.setHours(0, 0, 0, 0); const b = new Date(iso); b.setHours(0, 0, 0, 0);
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}
const hhmm = (iso: string) => { const d = new Date(iso); return `${d.getHours()}.${String(d.getMinutes()).padStart(2, "0")}`; };
const WEEKDAY = ["Søndag", "Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag"];
function daWhen(iso: string): string {
  const off = dayOffset(iso);
  const day = off === 0 ? "I dag" : off === 1 ? "I morgen" : off === -1 ? "I går" : off > 1 && off < 7 ? WEEKDAY[new Date(iso).getDay()] : new Date(iso).toLocaleDateString("da-DK", { day: "numeric", month: "long" });
  return `${day} kl. ${hhmm(iso)}`;
}
const lower1 = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
const cap = (s: string) => { s = (s || "").trim(); return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; };
const monthDa = () => new Date().toLocaleDateString("da-DK", { month: "long" });
const isToday = (iso: string | null) => !!iso && dayOffset(iso) === 0;

function splitItems(str: string): string[] {
  return (str || "").replace(/[.!]+$/, "").split(/,|\sog\s/i).map((x) => cap(x.trim())).filter(Boolean);
}

function examples(): Task[] {
  const now = new Date().toISOString();
  const base = { is_example: true, created_at: now, items: [], remind_at: null, call: null };
  const callBase = { max_credits: CALL_CREDITS, share_phone: true, confirmed_text: null, business_price_text: null };
  return [
    { ...base, id: "e1", kind: "call", title: "Vælg tid hos Tandlæge Holm", status: "awaiting_user", next_step: "Vælg tirsdag kl. 9.00 eller onsdag kl. 14.30",
      due_at: atDay(0, 18), who: "Dig", usage_text: "1 gratis opgave (oktober)",
      call: { ...callBase, business_name: "Tandlæge Holm", address: "Søndergade 20, 8000 Aarhus C", phone_display: "86 11 22 33", may_ask: "En ny tid til tandeftersyn",
        may_agree: "Ingenting, før du har valgt", may_not: "Sige ja til behandlinger", window: "tirsdag eller onsdag", result: "answered",
        business_reply: "Vi kan tilbyde tirsdag kl. 9.00 eller onsdag kl. 14.30.", duration_seconds: 95 },
      events: [{ at: atDay(-1, 14, 12), text: "Klinikken foreslog to tider" }] },
    { ...base, id: "e2", kind: "call", title: "Spørg boligforeningen, om de har modtaget min klage over den utætte radiator i badeværelset på 2. sal",
      status: "awaiting_business", next_step: "Boligforeningen ringer tilbage", due_at: atDay(daysTo(5), 16), who: "Boligforeningen",
      usage_text: "3 credits · besvaret opkald, 2 min. 40 sek.",
      call: { ...callBase, business_name: "Boligforeningen Østparken", address: "Østparken 1, 8000 Aarhus C", phone_display: "86 22 33 44",
        may_ask: "Om klagen over radiatoren er modtaget", may_agree: "At de ringer tilbage", may_not: "Aftale håndværkerbesøg", window: "i dag",
        result: "answered", business_reply: "Vi har modtaget klagen. Vi undersøger sagen og ringer tilbage inden fredag.", duration_seconds: 160 },
      events: [{ at: atDay(-2, 10, 3), text: "Opkald besvaret. De undersøger sagen og ringer tilbage." }] },
    { ...base, id: "e3", kind: "reminder", title: "Hent Ida i børnehaven", status: "planned", next_step: "Påmindelse i dag kl. 15.45",
      due_at: atDay(0, 15, 45), remind_at: atDay(0, 15, 45), who: "Assistenten minder dig", usage_text: "1 gratis opgave",
      events: [{ at: atDay(-2, 9), text: "Oprettet" }] },
    { ...base, id: "e4", kind: "reminder", title: "Køb gave til Idas fødselsdag", status: "planned", next_step: "Påmindelse fredag kl. 10.00",
      due_at: atDay(daysTo(5), 10), remind_at: atDay(daysTo(5), 10), who: "Assistenten minder dig", usage_text: "1 gratis opgave",
      events: [{ at: atDay(-1, 12), text: "Oprettet" }] },
    { ...base, id: "e5", kind: "reminder", title: "Aflever pant i Netto", status: "done", next_step: "Klaret",
      due_at: atDay(-1, 17), remind_at: atDay(-1, 17), who: "Dig", usage_text: "1 gratis opgave",
      events: [{ at: atDay(-1, 17), text: "Påmindelse sendt" }, { at: atDay(-1, 18, 20), text: "Markeret som klaret" }] },
  ];
}

export const FAKE_ME = "Mette";
export const FAKE_OTHER = "Anna";
const ME: Member = { id: "me", name: FAKE_ME, role: "owner", is_me: true };
const item = (id: string, text: string, extra: Partial<TaskItem> = {}): TaskItem => ({ id, text, done: false, added_by_name: null, done_by_name: null, note: null, link: null, ...extra });

/** Lists other people shared with the user: one wishlist already joined, one waiting behind an invite link. */
function sharedExamples(): { joined: Task[]; invitable: Record<string, Task> } {
  const base = { is_example: true, created_at: atDay(-3, 12), remind_at: null, call: null, due_at: null, shared: true, updated_at: atDay(-1, 20) };
  const anna: Member = { id: "anna", name: FAKE_OTHER, role: "owner", is_me: false };
  const meEditor: Member = { ...ME, role: "editor" };
  const wish: Task = { ...base, id: "s1", kind: "list", list_type: "wishlist", share_mode: "wishlist", my_role: "editor", title: "Annas ønskeliste",
    status: "in_progress", next_step: "Vælg en gave", who: FAKE_OTHER, usage_text: "Gratis – delt med dig",
    items: [item("s1a", "Bluetooth-højttaler", { note: "Gerne en lille en til badeværelset", added_by_name: FAKE_OTHER, price_minor: 129900, currency: "DKK", price_source: "user", color: "Sort", quantity: 1 }),
      item("s1b", "Strikkebog", { link: "https://example.com/strikkebog", added_by_name: FAKE_OTHER, price_minor: 24995, currency: "DKK", price_source: "user", shop: "example.com", quantity: 1 }),
      item("s1c", "Brætspillet Azul", { added_by_name: FAKE_OTHER, quantity: 1 }),
      item("s1d", "Weekend i sommerhus", { note: "En oplevelse sammen – vi går gerne sammen om den", added_by_name: FAKE_OTHER, quantity: 1, price_minor: 300000, currency: "DKK", price_source: "user" })],
    members: [anna, meEditor, { id: "jonas", name: "Jonas", role: "editor", is_me: false }],
    events: [{ at: atDay(-3, 12), text: "Anna delte sin ønskeliste med dig" }] };
  const party: Task = { ...base, is_example: false, id: "s2", kind: "list", list_type: "shopping", share_mode: "group", my_role: "editor",
    title: "Sommerfest – fælles indkøb", status: "in_progress", next_step: "Tilføj det, du tager med", who: "Alle", usage_text: "Gratis – delt med dig",
    items: [item("s2a", "Grillkul", { added_by_name: FAKE_OTHER }), item("s2b", "Pølser", { added_by_name: FAKE_OTHER })],
    members: [anna, meEditor], events: [{ at: atDay(-1, 19), text: "Anna oprettede listen" }] };
  return { joined: [wish], invitable: { sommerfest: party } };
}

/** People who accepted the user's invitations before (they have Dialogbot). */
const SUGGESTED: SuggestedPerson[] = [
  { name: "Anna", has_dialogbot: true, user_id: "u-anna", phone_e164: null },
  { name: "Jonas", has_dialogbot: true, user_id: "u-jonas", phone_e164: null },
  { name: "Peter", has_dialogbot: true, user_id: "u-peter", phone_e164: null },
];

/** The shop catalogue (Butikken). `requires_plan` apps need trial/Plus/Familie; `included` is computed per user. */
type CatalogEntry = Omit<Addon, "enabled" | "enabled_at" | "included"> & { requires_plan: boolean; what: string; example: string; steps: string[] };
const PLAN_APP = "Med i Plus og Familie";
const CATALOG: CatalogEntry[] = [
  { key: ADDON.call, name: "Ring for mig", tagline: "Peter ringer til virksomheder for dig", icon: "phone", category: "Hverdag",
    description: "Når du beder om det, foreslår Peter et opkald – hvem, hvad han må aftale, og hvad det højst koster. Der ringes først, når du har godkendt.",
    what: "Peter ringer til værkstedet, lægen eller frisøren og aftaler en tid – inden for det, du har sagt ja til. Du godkender altid først.",
    example: "Ring til cykelværkstedet og aftal aflevering torsdag efter kl. 15.",
    steps: ["Bekræft dit mobilnummer", "Vælg om Peter må give dit nummer videre", "Færdig – Peter spørger, før han ringer"],
    price_text: "Med i alle planer · ellers 3 credits pr. opkald", pricing: "credits", monthly_price_minor: null, status: "available", requires_plan: false,
    permissions: ["Ringer kun til virksomheder, du godkender", "Må give dit nummer videre, hvis du siger ja", "Gemmer et referat af opkaldet"], requires: [] },
  { key: ADDON.sharedLists, name: "Delte lister", tagline: "Fælles lister – alle kan tilføje og krydse af", icon: "users", category: "Lister",
    description: "Del en liste via et link. Dem, du inviterer, kan tilføje og krydse af, og du kan se, hvem der gjorde hvad.",
    what: "Indkøb, pakkeliste eller gøremål, som flere kan se og strege ud. Peter holder listen opdateret, uanset hvem der siger noget.",
    example: "Del indkøbslisten med Mette.",
    steps: ["Vælg hvem du vil dele med", "Peter laver en SMS-invitation, du sender fra dit nummer", "Listen er fælles – færdig"],
    price_text: "Gratis", pricing: "free", monthly_price_minor: null, status: "available", requires_plan: false,
    permissions: ["Deler en liste via link", "Viser medlemmernes fornavne på listen"], requires: [] },
  { key: ADDON.wishlists, name: "Ønskeseddel", tagline: "Del ønsker – de andre reserverer i hemmelighed", icon: "gift", category: "Lister",
    description: "Lav en ønskeseddel og del den. De andre kan skrive «Jeg køber den», så to ikke køber det samme – du ser aldrig, hvad der er reserveret.",
    what: "Lav en ønskeseddel og del den. Familien kan reservere en gave, uden at du kan se hvad – så overraskelsen holder.",
    example: "Lav en ønskeseddel til min fødselsdag.",
    steps: ["Opret din første ønskeseddel", "Vælg hvem der må se den", "Peter laver invitationer, du sender fra dit nummer", "Reservationer er skjult for dig – færdig"],
    price_text: PLAN_APP, pricing: "monthly", monthly_price_minor: null, status: "available", requires_plan: true,
    permissions: ["Deler en liste via link", "Holder reservationer skjult for dig"], requires: [] },
  { key: "foedselsdage", name: "Fødselsdage", tagline: "Peter husker mærkedage og siger til i god tid", icon: "cake", category: "Hverdag",
    description: "Peter husker fødselsdage og mærkedage og siger til i god tid – med forslag til gave fra personens ønskeseddel.",
    what: "Peter husker fødselsdage og mærkedage og siger til i god tid – med forslag til gave fra personens ønskeseddel.",
    example: "Mormor fylder 80 den 3. marts.",
    steps: ["Hent fødselsdage fra dine kontakter (valgfrit)", "Vælg hvor mange dage før du vil have besked", "Færdig"],
    price_text: PLAN_APP, pricing: "monthly", monthly_price_minor: null, status: "available", requires_plan: true,
    permissions: ["Gemmer de datoer, du giver den", "Læser kun kontakter, du selv vælger"], requires: [] },
  { key: "kalender", name: "Kalender", tagline: "Læg aftaler i din Google-, Outlook- eller iPhone-kalender", icon: "calendar", category: "Hverdag",
    description: "Aftaler, du har godkendt, kommer automatisk i din egen kalender.",
    what: "De tider, Peter aftaler for dig, og dem du selv fortæller ham, lander i din egen kalender – med adresse og det, I aftalte.",
    example: "Læg tiden hos frisøren i min kalender",
    steps: ["Forbind Google eller Outlook – eller abonnér på dit private kalenderlink", "Peter lægger aftaler ind, når de er bekræftet", "Flyttes eller fjernes en aftale, opdateres din kalender også"],
    price_text: PLAN_APP, pricing: "monthly", monthly_price_minor: null, status: "available", requires_plan: true,
    permissions: ["Skriver aftaler, du har godkendt, i din kalender", "Læser ikke dine andre aftaler"], requires: [] },
  { key: "madplan", name: "Madplan", tagline: "Ugens aftensmad på én side", icon: "utensils", category: "Hverdag",
    description: "Peter foreslår retter, og indkøbslisten laver sig selv ud fra planen.",
    what: "Ugens aftensmad på én side. Peter foreslår retter, og indkøbslisten laver sig selv ud fra planen.",
    example: "Lav en madplan til næste uge – ikke fisk om fredagen.",
    steps: ["Fortæl Peter hvor mange I er, og hvad I ikke spiser", "Vælg hvilken dag ugen starter", "Færdig"],
    price_text: PLAN_APP, pricing: "monthly", monthly_price_minor: null, status: "available", requires_plan: true,
    permissions: ["Gemmer jeres madpræferencer"], requires: [] },
  { key: "bil", name: "Bil & syn", tagline: "Syn, service og dæk – Peter holder styr på det", icon: "car", category: "Hverdag",
    description: "Peter holder styr på syn, service og dæk – og ringer til værkstedet og booker tiden, når du siger ja.",
    what: "Peter holder styr på syn, service og dæk – og ringer til værkstedet og booker tiden, når du siger ja.",
    example: "Min bil skal til syn i november.",
    steps: ["Indtast nummerplade", "Peter finder synsfristen", "Vælg dit faste værksted (valgfrit) – færdig"],
    price_text: PLAN_APP, pricing: "monthly", monthly_price_minor: null, status: "available", requires_plan: true,
    permissions: ["Slår nummerpladen op i Motorregistret"], requires: [ADDON.call] },
  { key: "regninger", name: "Regninger", tagline: "Faste regninger og opsigelsesfrister", icon: "receipt", category: "Hverdag",
    description: "Peter minder dig om faste regninger og opsigelsesfrister, så du ikke betaler for noget, du ikke bruger.",
    what: "Peter minder dig om faste regninger og opsigelsesfrister, så du ikke betaler for noget, du ikke bruger.",
    example: "Husk mig på at opsige fitness inden den 20.",
    steps: ["Sig hvilke regninger Peter skal huske", "Vælg hvor mange dage før du vil mindes", "Færdig"],
    price_text: PLAN_APP, pricing: "monthly", monthly_price_minor: null, status: "available", requires_plan: true,
    permissions: ["Gemmer kun de regninger, du nævner – ingen bankadgang"], requires: [] },
  { key: "laege", name: "Læge & tandlæge", tagline: "Peter bestiller og flytter tider for dig", icon: "stethoscope", category: "Hverdag",
    description: "Peter ringer og bestiller eller flytter tider hos lægen, tandlægen eller fysioterapeuten – inden for de tider, du har givet ham.",
    what: "Peter ringer og bestiller eller flytter tider hos lægen, tandlægen eller fysioterapeuten – inden for de tider, du har givet ham.",
    example: "Flyt min tandlægetid til næste uge, eftermiddag.",
    steps: ["Indtast dine faste behandlere", "Vælg hvornår Peter må booke", "Færdig"],
    price_text: PLAN_APP, pricing: "monthly", monthly_price_minor: null, status: "available", requires_plan: true,
    permissions: ["Ringer kun til behandlere, du har indtastet", "Deler aldrig helbredsoplysninger"], requires: [ADDON.call] },
  { key: "pakkeliste", name: "Pakkeliste", tagline: "Peter pakker listen – og husker det, I glemte sidst", icon: "suitcase", category: "Lister",
    description: "Sig hvor I skal hen og hvor længe – Peter laver pakkelisten og husker det, I glemte sidst.",
    what: "Sig hvor I skal hen og hvor længe – Peter laver pakkelisten og husker det, I glemte sidst.",
    example: "Vi skal en uge i sommerhus med to børn.",
    steps: ["Fortæl Peter om turen", "Ret listen til – Peter husker rettelserne", "Færdig"],
    price_text: PLAN_APP, pricing: "monthly", monthly_price_minor: null, status: "available", requires_plan: true,
    permissions: ["Gemmer dine pakkelister"], requires: [] },
  { key: "pakker", name: "Pakker", tagline: "Følg dine forsendelser ét sted", icon: "package", category: "Hverdag",
    description: "Send et sporingsnummer, så holder Peter øje og siger til, når pakken er klar.",
    what: "Send et sporingsnummer, så holder Peter øje og siger til, når pakken er klar til afhentning.",
    example: "Hold øje med pakken med nummer 00340434…",
    steps: ["Send Peter et sporingsnummer", "Færdig"],
    price_text: "Gratis", pricing: "free", monthly_price_minor: null, status: "coming_soon", requires_plan: false,
    permissions: ["Slår dine sporingsnumre op hos fragtfirmaet"], requires: [] },
];
const monthKey = (d = new Date()) => `${d.getFullYear()}-${d.getMonth()}`;
const addDays = (iso: string, n: number) => { const d = new Date(iso); d.setDate(d.getDate() + n); return d.toISOString(); };

function fresh(): State {
  const sh = sharedExamples();
  return {
    v: 8, sub: { plan: "none", status: "trial", interval: null, trialStart: new Date().toISOString(), periodEnd: null, cancelAtPeriodEnd: false, callsMonth: monthKey(), callsUsed: 0, checkouts: {} },
    quotaCalls: {}, location: null, push: [], joinLinks: {}, groups: [], status: {}, ref: { invited: 0, joined: 0, activated: 0, credits_earned: 0, viaInvite: null, selfRewarded: false, annaJoined: false, annaRewarded: false },
    addons: { [ADDON.call]: true, [ADDON.sharedLists]: true, [ADDON.wishlists]: true }, invites: {}, reservations: { s1c: "other" },
    gifts: { s1d: { target: 300000, currency: "DKK", others: 125000, othersCount: 2, mine: null, status: "open", coordinator: "other", pendingMe: false } },
    invitable: sh.invitable, n: 1000, freeUsed: 0, credits: 3, reserved: 0, sponsorDay: dayKey(new Date()), sponsorUsed: 0,
    phone: null, phoneVerified: false, phonePending: null,
    tasks: [...examples(), ...sh.joined], msgs: [],
    ledger: [{ id: "l1", kind: "welcome", amount: 3, text: "Velkomstcredits (én gang)", created_at: atDay(-3, 9) }],
    paySeq: 1040, lastPay: null, meta: {}, pending: {}, prices: {},
  };
}

export type FakeTools = {
  /** Prototype only: pick the outcome of a call that is in progress. */
  simulateOutcome(taskId: string, outcome: "answered" | "no_answer"): Promise<Task>;
  /** Simulated Stripe Checkout: +10 credits (a draft waiting for payment is activated with 1 of them). */
  completePurchase(draftTaskId: string | null): Promise<{ ref: string; activated: boolean }>;
  /** Replays the last payment webhook: already registered, nothing is added. */
  repeatPayment(): Promise<{ ref: string | null }>;
  /** A second member (Anna) acts on a shared list: joins, adds an item (group) or reserves a wish (wishlist). */
  simulateMember(taskId: string): Promise<Task>;
  /** The invited friend (Anna, a new user) creates her first own task: both get +3 credits (once per person). */
  simulateInviteeActivated(): Promise<{ rewarded: boolean }>;
  /** Moves the next invited person along: «Ikke åbnet endnu» → «Har åbnet» → «Med». */
  simulateInviteProgress(taskId: string): Promise<void>;
  /** Back to a fresh account without a trial (status «none»): only lists shared with it, drafts for the rest. */
  startFree(): Promise<void>;
  /** Ends the trial now (no plan): the free quota and credits apply again. */
  endTrial(): Promise<void>;
  emptyDay(): Promise<void>;
  reset(): Promise<void>;
};
export type FakePrivat = PrivatApi & FakeTools;

export function createFakePrivat(storageKey = "dialogbot-privat-fake"): FakePrivat {
  let s: State = load();

  function load(): State {
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (raw) { const v = JSON.parse(raw) as State; if (v.v === 8) return v; }
    } catch { /* private window, blocked storage: start fresh */ }
    return fresh();
  }
  function save() { try { sessionStorage.setItem(storageKey, JSON.stringify(s)); } catch { /* ignore */ } }
  const nid = (p: string) => { s.n += 1; return `${p}${s.n}`; };
  const find = (id: string) => s.tasks.find((t) => t.id === id) ?? fail(404, "not_found", "Opgaven findes ikke");
  const event = (t: Task, text: string) => { t.events.push({ at: new Date().toISOString(), text }); };
  const ledger = (kind: string, amount: number, text: string) => { s.ledger.push({ id: nid("l"), kind, amount, text, created_at: new Date().toISOString() }); };
  const msg = (o: Partial<ChatMessage> & Pick<ChatMessage, "kind">): ChatMessage => ({
    id: nid("m"), role: "assistant", text: "", task_id: null, about_task_id: null, before: null, after: null, options: null, links: null,
    created_at: new Date().toISOString(), ...o,
  });
  function rollSponsorDay() { const k = dayKey(new Date()); if (s.sponsorDay !== k) { s.sponsorDay = k; s.sponsorUsed = 0; } }
  // ---------- subscription ----------
  /** The plans' currency: the subscription's own once chosen (the market it was bought in), else the asked one. */
  function subscription(asked?: string): Subscription {
    const sb = s.sub;
    const currency: Currency = sb.plan !== "none" && sb.currency ? sb.currency : currencyOr(asked);
    if (sb.callsMonth !== monthKey()) { sb.callsMonth = monthKey(); sb.callsUsed = 0; }
    // No trial started yet (a fresh account, or one that only reads shared lists): status «none» – the trial starts
    // with the card at the checkout, as on the real site.
    const trialEnd = sb.trialStart ? addDays(sb.trialStart, TRIAL_DAYS) : null;
    const trialLeft = trialEnd ? Math.max(0, Math.ceil((new Date(trialEnd).getTime() - Date.now()) / 86_400_000)) : 0;
    const trialActive = trialLeft > 0;
    let status: SubscriptionStatus = sb.status;
    if (!sb.trialStart) status = "none";
    else if (sb.plan === "none") status = trialActive ? "trial" : "expired";
    else if (status === "trial" && !trialActive) status = "active";
    const entitled = status === "trial" || status === "active" || status === "past_due";
    // Rights: the chosen plan, or Plus during the trial.
    const spec = PLANS.find((p) => p.key === (sb.plan === "none" ? "plus" : sb.plan))!;
    const quota = entitled ? spec.calls : 0;
    return { plan: sb.plan, status, interval: sb.interval, trial_ends_at: status === "trial" ? trialEnd : null, trial_days_left: status === "trial" ? trialLeft : 0,
      current_period_end: sb.periodEnd, cancel_at_period_end: sb.cancelAtPeriodEnd, entitled,
      calls_quota: quota, calls_used: sb.callsUsed, calls_left: Math.max(0, quota - sb.callsUsed),
      people_limit: entitled ? spec.people : 1, apps_included: entitled && spec.appsIncluded, currency, plans: apiPlans(currency) as Plan[] };
  }
  const isEntitled = () => subscription().entitled;
  /** Usage line on a call proposal: the plan quota while it lasts, otherwise credits. */
  const proposalUsage = () => { const sb = subscription(); return sb.entitled && sb.calls_left > 0 ? `${sb.calls_used + 1} af ${sb.calls_quota} opkald i ${planName()} · maks. 4 min.` : `Højst ${CALL_CREDITS} credits, når du godkender`; };
  /** «Plus» (chosen plan, or the trial's Plus rights). */
  const planName = () => { const sb = subscription(); return PLANS.find((p) => p.key === (sb.plan === "none" ? "plus" : sb.plan))!.name; };
  function balance(): Balance {
    rollSponsorDay();
    const sb = subscription();
    return { free_used: s.freeUsed, free_limit: FREE_LIMIT, credits: s.credits, reserved: s.reserved, sponsor_left_today: SPONSOR_PER_DAY - s.sponsorUsed,
      phone_display: s.phone, phone_verified: s.phoneVerified, push_enabled: s.push.length > 0, location_city: s.location,
      plan: sb.plan, plan_status: sb.status, trial_days_left: sb.trial_days_left, calls_quota: sb.calls_quota, calls_used: sb.calls_used, calls_left: sb.calls_left, entitled: sb.entitled };
  }
  /** What the current user may see: the owner of a wishlist never sees reservations; others see "Reserveret". */
  function project(t: Task): Task {
    const ownerOfWish = t.share_mode === "wishlist" ? t.my_role === "owner" : t.list_type === "wishlist";
    t.items = t.items.map((it) => {
      const r = s.reservations[it.id];
      const base: TaskItem = { quantity: 1, ...it };
      if (ownerOfWish) return { ...base, reserved: null, reserved_by_me: false, group_gift: base.group_gift ?? { enabled: false, target_minor: null, currency: null } };
      if (t.list_type === "wishlist" || t.share_mode === "wishlist") return { ...base, reserved: !!r, reserved_by_me: r === "me", group_gift: giverGift(it) };
      return base;
    }).filter((it) => !it.archived || (it.group_gift && "status" in it.group_gift));
    if (t.list_type === "wishlist") t.design = resolveDesign((t as Task & { designRaw?: Record<string, unknown> | null }).designRaw ?? null, t.design?.cover ?? null);
    return t;
  }
  /** A wish shared with me: the simulated agreement (others = one sum), never shown to the owner. */
  function giverGift(it: TaskItem): GiverGroupGift | null {
    const own = it.group_gift as OwnerGroupGift | undefined;
    const g = (s.gifts ??= {})[it.id];
    if (!g && !(own?.enabled && own.target_minor)) return null;
    const x: FakeGift = g ?? { target: own!.target_minor!, currency: own!.currency ?? "DKK", others: 0, othersCount: 0, mine: null, status: "open", coordinator: null, pendingMe: false };
    const pledged = x.others + (x.mine ?? 0);
    const status = x.status === "open" && pledged >= x.target ? "full" : x.status;
    return { enabled: true, status, target_minor: x.target, currency: x.currency, pledged_minor: pledged, remaining_minor: Math.max(0, x.target - pledged),
      participants: x.othersCount + (x.mine ? 1 : 0), my_pledge_minor: x.mine, coordinator: x.coordinator ? { name: x.coordinator === "me" ? FAKE_ME : FAKE_OTHER, is_me: x.coordinator === "me" } : null,
      pending_coordinator_is_me: x.pendingMe, is_coordinator: x.coordinator === "me", cancel_reason: x.status === "cancelled" ? "wish_removed" : null,
      can_join: x.status === "open" && (x.mine != null || pledged < x.target) && !s.reservations[it.id], reserved_by_me: s.reservations[it.id] === "me",
      participant_names: x.coordinator === "me" && x.othersCount ? [{ user_ref: "anna", name: FAKE_OTHER }] : null };
  }
  function resolveDesign(raw: Record<string, unknown> | null, cover: WishDesign["cover"]): WishDesign {
    const themes = WISH_THEMES.themes as Record<string, { accent: string; background: string; text: string; font: string }>;
    const theme = typeof raw?.theme === "string" && themes[raw.theme] ? raw.theme : "neutral";
    const b = themes[theme];
    const pick = (k: "accent" | "background" | "text" | "font") => (typeof raw?.[k] === "string" && raw[k] ? raw[k] as string : b[k]);
    return { theme, accent: pick("accent"), background: pick("background"), text: pick("text"), font: pick("font"),
      decorations: typeof raw?.decorations === "boolean" ? raw.decorations : true, subtitle: (raw?.subtitle as string) || null, date: (raw?.date as string) || null,
      cover: raw?.cover ? cover : null, customized: !!raw };
  }
  function giftOf(taskId: string, itemId: string): { t: Task; g: FakeGift } {
    const t = find(taskId);
    if (mine(t)) fail(403, "owner_cannot_give", "Fællesgaven tilhører gavegiverne");
    const it = t.items.find((x) => x.id === itemId) ?? fail(404, "not_found", "Ønsket findes ikke");
    const own = it.group_gift as OwnerGroupGift | undefined;
    s.gifts ??= {};
    if (!s.gifts[itemId]) {
      if (!own?.enabled || !own.target_minor) fail(409, "group_gift_off", "Dette ønske er ikke en fællesgave");
      s.gifts[itemId] = { target: own!.target_minor!, currency: own!.currency ?? "DKK", others: 0, othersCount: 0, mine: null, status: "open", coordinator: null, pendingMe: false };
    }
    return { t, g: s.gifts[itemId] };
  }
  function wishItem(body: Partial<WishBody>, base: TaskItem): TaskItem {
    const x: TaskItem = { ...base };
    if (body.text !== undefined) x.text = cap(body.text);
    for (const k of ["note", "link", "shop", "size", "color", "variant", "currency", "price_fetched_at"] as const) if (k in body) (x as Record<string, unknown>)[k] = body[k] || null;
    if ("quantity" in body) x.quantity = body.quantity ?? 1;
    if ("price_minor" in body) { x.price_minor = body.price_minor ?? null; x.price_source = body.price_minor == null ? null : body.price_source === "shop" ? "shop" : "user"; }
    if (x.price_minor != null && !x.currency) x.currency = "DKK";
    if ("details" in body) x.details = body.details ?? null;
    if ("image_key" in body) { x.image = body.image_key ? images[body.image_key] ?? x.image ?? null : null; x.image_origin = body.image_key ? body.image_origin ?? "upload" : null; }
    if ("group_gift_enabled" in body || "group_gift_target_minor" in body) {
      const prev = (x.group_gift as OwnerGroupGift | null) ?? { enabled: false, target_minor: null, currency: null };
      const enabled = body.group_gift_enabled ?? prev.enabled;
      const target = body.group_gift_target_minor !== undefined ? body.group_gift_target_minor : prev.target_minor;
      if (enabled && (!target || target <= 0)) fail(422, "validation_failed", "Skriv et målbeløb over 0");
      x.group_gift = { enabled, target_minor: target ?? null, currency: x.currency || "DKK" };
    }
    return x;
  }
  /** Simulated uploads: kept as small data URLs in the tab (the real API stores them in the private bucket). */
  const images: Record<string, { url: string; url_sm: string }> = {};
  async function asDataUrl(file: Blob): Promise<string> {
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) fail(422, "validation_failed", "Brug et billede i JPEG, PNG eller WebP");
    if (file.size > 1_500_000) fail(422, "validation_failed", "I simuleringen kan billeder højst være 1,5 MB");
    return await new Promise<string>((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result)); r.onerror = () => rej(r.error); r.readAsDataURL(file); });
  }
  function walk(v: unknown): unknown {
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === "object") {
      const o = v as Record<string, unknown>;
      if ("items" in o && "kind" in o && "status" in o) return project(o as unknown as Task);
      if ("awaiting" in o && "today" in o) { for (const k of ["awaiting", "today", "soon"]) o[k] = walk(o[k]); }
    }
    return v;
  }
  function done<T>(v: T): T { save(); return walk(clone(v)) as T; }
  const on = (key: string) => !!s.addons[key];
  const addonName = (key: string) => CATALOG.find((a) => a.key === key)?.name ?? key;
  const addonIncluded = (a: CatalogEntry) => !a.requires_plan || isEntitled();
  const projectAddon = (a: CatalogEntry): Addon => ({ ...a, included: addonIncluded(a), enabled: on(a.key), enabled_at: on(a.key) ? atDay(-3, 9) : null });
  const addonMsg = (key: string) => msg({ kind: "addon", addon_key: key, text: `${addonName(key)} er ikke slået til.` });
  const gate = (key: string) => { if (!on(key)) fail(403, "addon_disabled", `${addonName(key)} er ikke slået til`); };
  const mine = (t: Task) => !t.my_role || t.my_role === "owner";
  function share(t: Task, mode: "group" | "wishlist"): string {
    const ABC = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let token = "";
    do { token = Array.from({ length: 8 }, () => ABC[Math.floor(Math.random() * ABC.length)]).join(""); } while (s.invites[token]);
    s.invites[token] = t.id; s.ref.invited += 1;
    t.shared = true; t.share_mode = mode; t.my_role = "owner";
    t.members = t.members?.length ? t.members : [ME];
    t.updated_at = new Date().toISOString();
    return token;
  }
  const result = (messages: ChatMessage[]): SendResult => { s.msgs.push(...messages); return done({ messages, balance: balance() }); };

  /** A new list or reminder: free while the month has free tasks left, otherwise a draft that waits for a choice. */
  const REFERRAL = 3;
  function newDigital(t: Task, intro: string): ChatMessage[] {
    s.tasks.push(t);
    if (s.ref.viaInvite && !s.ref.selfRewarded) {
      s.ref.selfRewarded = true; s.credits += REFERRAL;
      ledger("referral", REFERRAL, `Invitationsbonus: din første egen opgave (${FAKE_OTHER} får også ${REFERRAL})`);
    }
    if (isEntitled()) {
      // Lists and reminders are unlimited with the trial and every plan.
      t.usage_text = `Med i ${planName()} · ubegrænset`;
      return [msg({ kind: "text", text: intro }), msg({ kind: "task", task_id: t.id })];
    }
    s.pending[t.id] = { status: t.status, next: t.next_step, intro };
    t.status = "draft"; t.next_step = "Venter på din plan"; t.usage_text = "Ikke betalt endnu";
    const st = subscription().status;
    return [msg({ kind: "draft", task_id: t.id, text: st === "none"
      ? "Det kræver en plan. Prøv Dialogbot Privat gratis i 14 dage – kortet trækkes først, når prøveperioden er slut. Opgaven er gemt som udkast, til du har valgt."
      : "Din prøveperiode er slut. Vælg en plan, eller brug 1 credit – udkastet venter, mens du vælger." })];
  }

  function activate(t: Task, usage: string): ChatMessage[] {
    const p = s.pending[t.id];
    t.status = p.status; t.next_step = p.next; t.usage_text = usage;
    event(t, `Fortsat: ${usage}`);
    delete s.pending[t.id];
    return [msg({ kind: "text", text: `${p.intro} Opgaven er aktiv nu.` }), msg({ kind: "task", task_id: t.id })];
  }

  function reply(text: string, focus: Task | null): ChatMessage[] {
    const low = text.toLowerCase();
    const open = (k: Task["kind"]) => [...s.tasks].reverse().find((t) => t.kind === k && t.status !== "done" && t.status !== "declined" && !t.is_example);

    if (focus && focus.is_example && focus.id === "e1" && focus.status === "awaiting_user") {
      const m = msg({ kind: "clarify", text: "Hvilken tid vil du have hos Tandlæge Holm?", about_task_id: focus.id, options: [
        { id: "tue", label: "Tirsdag kl. 9.00", sub: "Jeg giver klinikken besked" }, { id: "wed", label: "Onsdag kl. 14.30", sub: "Jeg giver klinikken besked" }] });
      s.meta[m.id] = { kind: "decide", taskId: focus.id };
      return [m];
    }
    if (/^del\b/.test(low) || /\bdel (listen|indkøbslisten|ønskelisten|den)\b/.test(low)) {
      const target = (focus && focus.kind === "list" && mine(focus) ? focus : null) ?? open("list");
      const wishT = target?.list_type === "wishlist";
      const key = wishT ? ADDON.wishlists : ADDON.sharedLists;
      if (!on(key)) return [addonMsg(key)];
      if (!target) return [msg({ kind: "text", text: "Du har ingen liste at dele endnu. Lav en først – fx «Lav en indkøbsliste med mælk og rugbrød»." })];
      const who = text.match(/\bmed\s+([\wæøåÆØÅ-]+)/)?.[1] ?? null;
      const group = who ? s.groups.find((g) => g.name.toLowerCase() === who.toLowerCase()) : undefined;
      if (group) {
        return [msg({ kind: "share_proposal", task_id: target.id, about_task_id: target.id, options: [{ id: group.id, label: group.name, sub: `${group.members.length} personer` }],
          text: `Skal jeg dele «${target.title}» med ${group.name}? Dem, der har Dialogbot, kommer med med det samme – resten får en SMS fra dig. Der sendes intet, før du siger ja.` })];
      }
      if (who && who === who.toLowerCase()) {
        const name = cap(who);
        const names = SUGGESTED.map((p) => p.name);
        const m = msg({ kind: "clarify", about_task_id: target.id, text: `Du har ingen gruppe, der hedder ${name}. Skal jeg lave gruppen ${name} med ${names.slice(0, -1).join(", ")} og ${names[names.length - 1]}?`,
          options: [{ id: "yes", label: "Ja, lav gruppen", sub: "Du kan rette den bagefter under Mine folk" }, { id: "edit", label: "Ret", sub: "Vælg selv, hvem der skal med" }] });
        s.meta[m.id] = { kind: "mkgroup", groupName: name, taskId: target.id };
        return [m];
      }
      return [msg({ kind: "share_proposal", task_id: target.id, about_task_id: target.id,
        text: `Skal jeg lave et invitationslink til «${target.title}»${who ? `, som du kan sende til ${who}` : ""}? Der sendes intet, før du selv deler linket.` })];
    }
    if (focus && focus.kind === "call" && focus.call && !focus.call.phone_e164 && /\d{2}\s?\d{2}\s?\d{2}\s?\d{2}/.test(text)) {
      const n = text.match(/(\+45\s?)?(\d{2}\s?\d{2}\s?\d{2}\s?\d{2})/)![2].replace(/\s/g, "");
      focus.call.phone_e164 = `+45${n}`; focus.call.phone_display = n.replace(/(\d{2})(?=\d)/g, "$1 "); focus.call.source = "user";
      focus.call.is_mobile = isDanishMobile(focus.call.phone_e164);
      event(focus, `Nummer tilføjet: ${focus.call.phone_display}`);
      return [msg({ kind: "text", about_task_id: focus.id, text: `Tak. Jeg bruger ${focus.call.phone_display}.` }), msg({ kind: "call_proposal", task_id: focus.id, text: "" })];
    }
    if (/hvad venter/.test(low)) {
      const w = s.tasks.filter((t) => t.status === "awaiting_user" || t.status === "draft");
      return [msg({ kind: "waiting", links: w.map((t) => t.id),
        text: w.length ? (w.length === 1 ? "Én ting venter på dit svar:" : `${w.length} ting venter på dit svar:`) : "Intet venter på dit svar lige nu." })];
    }
    const listT = focus && focus.kind === "list" ? focus : open("list");
    if (listT && /(tilføj|tilfoej|husk også|sæt .+ på)/.test(low) && !/liste med/.test(low)) {
      const raw = text.replace(/^.*?(tilføj|tilfoej|husk også|sæt)\s*/i, "").replace(/\s*(på listen|til listen|på)\s*[.!]?$/i, "");
      const its = splitItems(raw);
      listT.items.push(...its.map((x) => item(nid("i"), x)));
      event(listT, `Tilføjet: ${its.join(", ").toLowerCase()} (gratis rettelse)`);
      return [msg({ kind: "text", text: `Tilføjet ${its.join(" og ").toLowerCase()}. Det er stadig den samme liste, og en rettelse koster ingen opgave.`, about_task_id: listT.id }),
        msg({ kind: "task", task_id: listT.id })];
    }
    const remT = focus && focus.kind === "reminder" ? focus : open("reminder");
    const hm = low.match(/kl\.?\s*(\d{1,2})(?:[.:](\d{2}))?/);
    if (remT && remT.remind_at && /(flyt|ændr|skub|ret den)/.test(low) && hm) {
      const before = daWhen(remT.remind_at);
      const d = new Date(remT.remind_at); d.setHours(+hm[1], +(hm[2] ?? 0), 0, 0);
      remT.remind_at = d.toISOString(); remT.due_at = remT.remind_at;
      const after = daWhen(remT.remind_at);
      remT.next_step = `Påmindelse ${lower1(after)}`;
      event(remT, `Flyttet fra ${lower1(before)} til ${lower1(after)}`);
      return [msg({ kind: "move", task_id: remT.id, before, after, about_task_id: remT.id })];
    }
    if (/liste/.test(low)) {
      const wish = /ønske/.test(low);
      if (wish && !on(ADDON.wishlists)) return [addonMsg(ADDON.wishlists)];
      const m = text.match(/\smed\s(.+)$/i);
      const its = m ? splitItems(m[1]) : [];
      const list_type: ListType = wish ? "wishlist" : /indkøb/.test(low) ? "shopping" : "todo";
      const title = wish ? "Ønskeliste" : /indkøb/.test(low) ? "Indkøbsliste" : "Liste";
      const t: Task = { id: nid("t"), kind: "list", title, list_type, shared: false, share_mode: null, my_role: "owner", members: [], status: "in_progress", next_step: "Køb ind", due_at: null, who: "Dig", usage_text: "",
        is_example: false, created_at: new Date().toISOString(), items: its.map((x) => item(nid("i"), x)), remind_at: null, call: null,
        events: [{ at: new Date().toISOString(), text: "Oprettet i samtalen" }] };
      if (wish) t.next_step = "Del listen, når du er klar";
      return newDigital(t, its.length ? `Her er din ${title.toLowerCase()} med ${its.join(" og ").toLowerCase()}.` : "Her er din liste.");
    }
    if (/mind mig om/.test(low)) {
      let what = text.replace(/^.*?mind mig om\s*(at\s+)?/i, "");
      let off = 0;
      if (/i morgen/i.test(what)) off = 1; else if (/torsdag/i.test(what)) off = daysTo(4); else if (/fredag/i.test(what)) off = daysTo(5);
      what = what.replace(/\s*(i morgen|i dag|på torsdag|torsdag|på fredag|fredag)\b.*$/i, "").replace(/\s*kl\.?.*$/i, "");
      const at = atDay(off, hm ? +hm[1] : 9, hm ? +(hm[2] ?? 0) : 0);
      const when = daWhen(at);
      const t: Task = { id: nid("t"), kind: "reminder", title: cap(what) || "Påmindelse", status: "planned", next_step: `Påmindelse ${lower1(when)}`, due_at: at,
        who: "Assistenten minder dig", usage_text: "", is_example: false, created_at: new Date().toISOString(), items: [], remind_at: at, call: null,
        events: [{ at: new Date().toISOString(), text: "Oprettet i samtalen" }] };
      return newDigital(t, `Jeg minder dig om det ${lower1(when)}.`);
    }
    if (/ring til|ring for mig|ring op/.test(low)) {
      if (!on(ADDON.call)) return [addonMsg(ADDON.call)];
      if (!s.location) {
        const m = msg({ kind: "clarify", text: "Hvor skal jeg lede? Jeg bruger kun din position til denne søgning.", options: [
          { id: "location:geo", label: "Brug min position", sub: "Kun når du trykker" }, { id: "location:city", label: "Skriv by eller postnummer", sub: "Fx 8000 eller Aarhus C" }] });
        s.meta[m.id] = { kind: "where", query: text };
        return [m];
      }
      let win = "torsdag efter kl. 15";
      const k = low.match(/(?:kl\.?|klokken)\s*(\d{1,2}|tre|fire|fem)/);
      const words: Record<string, number> = { tre: 15, fire: 16, fem: 17 };
      if (k) { let h = words[k[1]] ?? +k[1]; if (h < 12) h += 12; win = `torsdag efter kl. ${h}`; }
      const ids = findShops(text);
      const km = (n: number) => n < 1 ? `${Math.round(n * 1000)} m` : `${n.toLocaleString("da-DK")} km`;
      const options: ChatOption[] = [
        ...ids.map((k) => { const x = SHOPS[k]; return { id: `place:demo-${k}`, label: x.name,
          sub: [`${x.address} · ${km(x.km)}`, x.open ? "Åben nu" : `Lukket – åbner ${x.next}`, `★ ${x.rating.toLocaleString("da-DK")} (${x.count})`, x.phone ?? "Intet nummer"].join(" · ") }; }),
        { id: "other", label: "En anden", sub: "Skriv navnet eller nummeret" }];
      const m = msg({ kind: "clarify", text: `Jeg fandt ${ids.length} tæt på ${s.location}. Hvem mener du?`, options });
      s.meta[m.id] = { kind: "shops", win };
      return [m];
    }
    const m = msg({ kind: "clarify", text: "Skal jeg lave en påmindelse, en liste eller ringe for dig?", options: [
      { id: "reminder", label: "Mind mig om …", sub: "En besked på et bestemt tidspunkt" },
      { id: "list", label: "Lav en liste", sub: "Med punkter, du kan krydse af" },
      { id: "call", label: "Ring for mig", sub: "Du godkender, før jeg ringer" }] });
    s.meta[m.id] = { kind: "prefill" };
    return [m];
  }

  function day(): Day {
    const awaiting = s.tasks.filter((t) => t.status === "awaiting_user" || t.status === "draft");
    const active = (t: Task) => t.status === "planned" || t.status === "in_progress" || t.status === "awaiting_business";
    const todayList = (t: Task) => t.kind === "list" && t.status === "in_progress" && isToday(t.created_at);
    const today = s.tasks.filter((t) => active(t) && (isToday(t.due_at) || todayList(t)));
    const soon = s.tasks.filter((t) => !today.includes(t) && !awaiting.includes(t) && t.due_at && dayOffset(t.due_at) >= 0
      && (active(t) || (t.status === "done" && t.call?.result === "answered"))).slice(0, 4);
    return { awaiting, today, soon };
  }

  const confirmedFor = (win: string) => /fredag/.test(win) ? { text: "Fredag kl. 10.00", off: daysTo(5), h: 10, m: 0 }
    : /kl\. 16/.test(win) ? { text: "Torsdag kl. 16.30", off: daysTo(4), h: 16, m: 30 } : /kl\. 17/.test(win) ? { text: "Torsdag kl. 17.15", off: daysTo(4), h: 17, m: 15 }
    : { text: "Torsdag kl. 15.30", off: daysTo(4), h: 15, m: 30 };

  function makeGroup(name: string, members: { name: string; phone: string | null; user_id?: string | null }[]): Group {
    const g: Group = { id: nid("g"), name: cap(name), members: [], created_at: new Date().toISOString() };
    s.groups.push(g); addMembers(g, members);
    return g;
  }
  function addMembers(g: Group, members: { name: string; phone: string | null; user_id?: string | null }[]) {
    for (const m of members) {
      if (m.phone && g.members.some((x) => x.phone_e164 === m.phone)) continue;
      if (m.user_id && g.members.some((x) => x.user_id === m.user_id)) continue;
      const known = SUGGESTED.find((p) => p.user_id && p.user_id === m.user_id);
      const gm: GroupMember = { id: nid("gm"), name: m.name.trim() || (m.phone ? prettyPhone(m.phone) : "?"), phone_e164: m.phone, user_id: m.user_id ?? null, has_dialogbot: !!known };
      g.members.push(gm);
    }
  }
  const findGroup = (id: string) => s.groups.find((g) => g.id === id) ?? fail(404, "not_found", "Gruppen findes ikke");

  const fake: FakePrivat = {
    async account() { await wait(); return { workspace_id: "fake-personal", created: false }; },
    async me() { await wait(); return done(balance()); },
    async bootstrap() {
      const [me, d, own, shared, messages, ledger, addons, referrals, groups, subscription] = await Promise.all([
        fake.me(), fake.day(), fake.tasks(), fake.sharedTasks(), fake.messages(), fake.ledger(), fake.addons(), fake.referrals(), fake.groups(), fake.subscription()]);
      const tasks = [...own];
      for (const t of shared) if (!tasks.some((x) => x.id === t.id)) tasks.push(t);
      return { me, day: d, tasks, messages, ledger, addons, referrals, groups, subscription };
    },
    async day() { await wait(); return done(day()); },
    async tasks(status) { await wait(); return done(status ? s.tasks.filter((t) => t.status === status) : s.tasks); },
    async task(id) { await wait(); return done(find(id)); },
    async toggleItem(taskId, itemId) {
      await wait();
      const t = find(taskId); const it = t.items.find((x) => x.id === itemId) ?? fail(404, "not_found", "Punktet findes ikke");
      it.done = !it.done; it.done_by_name = null;
      t.updated_at = new Date().toISOString();
      return done(t);
    },
    async activate(taskId, method) {
      await wait();
      const t = find(taskId);
      if (t.status !== "draft") return done(t);
      if (method === "sponsor") return fake.sponsorClaim(taskId);
      if (s.credits < 1) fail(409, "insufficient_credits", "Du har ingen credits");
      s.credits -= 1; ledger("task_credit", -1, "Ny opgave efter månedsgrænsen");
      s.msgs.push(...activate(t, "1 credit"));
      return done(t);
    },
    async messages(taskId) { await wait(); return done(taskId ? s.msgs.filter((m) => m.task_id === taskId || m.about_task_id === taskId) : s.msgs); },
    async send(text, aboutTaskId) {
      await wait();
      const t = text.trim();
      if (!t) fail(422, "validation_error", "Skriv en besked");
      const focus = aboutTaskId ? s.tasks.find((x) => x.id === aboutTaskId) ?? null : null;
      const me = msg({ role: "user", kind: "text", text: t, about_task_id: focus?.id ?? null });
      return result([me, ...reply(t, focus)]);
    },
    async pickOption(messageId, optionId) {
      await wait();
      const m = s.msgs.find((x) => x.id === messageId) ?? fail(404, "not_found", "Beskeden findes ikke");
      const meta = s.meta[messageId];
      const o = m.options?.find((x) => x.id === optionId) ?? fail(404, "not_found", "Valget findes ikke");
      if (!meta || meta.answered) fail(409, "already_answered", "Du har allerede svaret");
      meta.answered = true;
      const me = msg({ role: "user", kind: "text", text: o.label, about_task_id: m.about_task_id });
      if (meta.kind === "prefill") {
        const hint = { reminder: "Skriv, hvad og hvornår – fx «Mind mig om at hente pakken i morgen kl. 16».",
          list: "Skriv punkterne – fx «Lav en indkøbsliste med mælk og rugbrød».", call: "Skriv, hvem jeg skal ringe til, og hvad det gælder – fx «Ring til cykelværkstedet og aftal aflevering torsdag efter kl. 15»." }[optionId] ?? "";
        return result([me, msg({ kind: "text", text: hint })]);
      }
      if (meta.kind === "where") return result([me, msg({ kind: "text", text: "Skriv byen eller postnummeret, så leder jeg der." })]);
      if (meta.kind === "mkgroup" && meta.taskId) {
        if (optionId !== "yes") return result([me, msg({ kind: "text", text: "Lav eller ret gruppen under Mine folk – så deler jeg bagefter." })]);
        const g = makeGroup(meta.groupName ?? "Gruppe", SUGGESTED.map((p) => ({ name: p.name, phone: null, user_id: p.user_id ?? null })));
        const t = find(meta.taskId);
        return result([me, msg({ kind: "share_proposal", task_id: t.id, about_task_id: t.id, options: [{ id: g.id, label: g.name, sub: `${g.members.length} personer` }],
          text: `Gruppen ${g.name} er lavet. Skal jeg dele «${t.title}» med den? Der sendes intet, før du siger ja.` })]);
      }
      if (meta.kind === "decide" && meta.taskId) {
        const t = find(meta.taskId);
        t.status = "awaiting_business"; t.next_step = `Klinikken bekræfter ${lower1(o.label)}`; t.who = "Tandlæge Holm";
        t.due_at = atDay(daysTo(/tirsdag/i.test(o.label) ? 2 : 3), /tirsdag/i.test(o.label) ? 9 : 14, /tirsdag/i.test(o.label) ? 0 : 30);
        event(t, `Du valgte ${lower1(o.label)}. Afventer klinikkens bekræftelse.`);
        return result([me, msg({ kind: "text", text: `Godt. Jeg giver Tandlæge Holm besked om ${lower1(o.label)} og siger til, når de har bekræftet.`, about_task_id: t.id })]);
      }
      const key = optionId.replace(/^place:demo-/, "");
      if (optionId === "other" || !SHOPS[key]) return result([me, msg({ kind: "text", text: "Skriv navnet eller nummeret på virksomheden, så finder jeg den." })]);
      const shop = SHOPS[key]; const win = meta.win ?? "torsdag efter kl. 15";
      const t: Task = { id: nid("t"), kind: "call", title: `Aflever cyklen hos ${shop.name} ${win}`, status: "awaiting_user", next_step: "Godkend opkaldet",
        due_at: null, who: "Dig", usage_text: proposalUsage(), is_example: false, created_at: new Date().toISOString(),
        items: [], remind_at: null,
        call: { business_name: shop.name, address: shop.address, phone_display: shop.phone ?? "", phone_e164: e164(shop.phone), is_mobile: isDanishMobile(e164(shop.phone)),
          open_now: shop.open, next_open_text: shop.open ? null : shop.next ?? null, source: "demo", status: "proposed", may_ask: `En tid til at aflevere cyklen ${win}`,
          may_agree: `Aflevering ${win}`, may_not: "Sige ja til reparationer eller priser", window: win, max_credits: CALL_CREDITS, share_phone: true,
          result: null, confirmed_text: null, business_reply: null, business_price_text: null, duration_seconds: null },
        events: [{ at: new Date().toISOString(), text: "Forslag til opkald oprettet" }] };
      s.tasks.push(t); s.prices[t.id] = shop.price;
      return result([me, msg({ kind: "call_proposal", task_id: t.id, text: `Skal jeg ringe til ${shop.name}?` })]);
    },
    async approveCall(taskId, body: ApproveBody) {
      await wait();
      const t = find(taskId);
      gate(ADDON.call);
      if (!t.call || t.status !== "awaiting_user" || t.call.result) fail(409, "conflict", "Opkaldet kan ikke godkendes nu");
      if (!s.phoneVerified) fail(409, "needs_phone", "Bekræft dit telefonnummer først");
      // Plan quota first (counted when the call is answered); otherwise credits («ekstra opkald»).
      const sb = subscription();
      const viaPlan = sb.entitled && sb.calls_left > 0;
      if (!viaPlan && s.credits < t.call!.max_credits) fail(409, "insufficient_credits", `Opkaldet kræver ${t.call!.max_credits} credits`);
      const c = t.call!;
      if (!c.phone_e164) fail(409, "no_number", "Skriv virksomhedens nummer først");
      if ((c.is_mobile ?? isDanishMobile(c.phone_e164)) && !body.confirm_business) fail(409, "confirm_business", "Bekræft, at det er en virksomhed");
      if (c.open_now === false && !body.at_next_open) fail(409, "business_closed", `Virksomheden har lukket. Jeg kan ringe ${c.next_open_text}, når de åbner.`);
      if (body.window && body.window !== c.window) {
        const swap = (x: string) => x.split(c.window).join(body.window);
        t.title = swap(t.title); c.may_ask = swap(c.may_ask); c.may_agree = swap(c.may_agree); c.window = body.window;
      }
      c.share_phone = body.share_phone;
      let usage: string;
      if (viaPlan) {
        s.quotaCalls[t.id] = true;
        usage = `${sb.calls_used + 1} af ${sb.calls_quota} opkald i ${planName()} · maks. 4 min.`;
      } else {
        s.credits -= c.max_credits; s.reserved += c.max_credits;
        ledger("reserve", -c.max_credits, "Reserveret til opkald");
        usage = `${c.max_credits} credits reserveret`;
      }
      t.usage_text = usage;
      if (c.open_now === false) {
        t.status = "planned"; c.status = "approved"; t.next_step = `Ringer ${c.next_open_text}, når de åbner`; t.who = "Assistenten";
        event(t, `Du godkendte opkaldet. Jeg ringer ${c.next_open_text}, når de åbner. ${usage}.`);
        return done(t);
      }
      t.status = "in_progress"; c.status = "in_progress"; t.next_step = "Assistenten ringer op"; t.who = "Assistenten";
      event(t, `Du godkendte opkaldet. ${usage}.`);
      return done(t);
    },
    async declineCall(taskId) {
      await wait();
      const t = find(taskId);
      if (t.status === "in_progress") fail(409, "conflict", "Opkaldet er i gang");
      t.status = "declined"; if (t.call) t.call.result = "declined";
      t.next_step = "Afvist – der er ikke ringet"; t.usage_text = "Intet forbrug";
      event(t, "Du afviste opkaldet");
      return done(t);
    },
    async retryCall(taskId) {
      await wait();
      const t = find(taskId);
      if (!t.call) fail(409, "conflict", "Ikke et opkald");
      t.status = "awaiting_user"; t.call!.result = null; t.next_step = "Godkend opkaldet"; t.who = "Dig";
      t.usage_text = proposalUsage();
      event(t, "Nyt forslag til opkald");
      s.msgs.push(msg({ kind: "call_proposal", task_id: t.id, text: `Skal jeg ringe til ${t.call!.business_name} igen?` }));
      return done(t);
    },
    async phoneStart(phone) {
      await wait();
      const digits = phone.replace(/[^\d+]/g, "");
      if (digits.replace(/^\+45/, "").length !== 8) fail(422, "invalid_phone", "Skriv et dansk mobilnummer med 8 cifre");
      s.phonePending = digits.replace(/^\+45/, "").replace(/(\d{2})(?=\d)/g, "$1 ").trim();
      return done({ sent: true as const });
    },
    async phoneVerify(code) {
      await wait();
      if (!s.phonePending) fail(409, "no_code", "Bed om en kode først");
      if (code.trim() !== FAKE_SMS_CODE) fail(422, "invalid_code", "Koden passer ikke");
      s.phone = s.phonePending; s.phonePending = null; s.phoneVerified = true;
      return done(balance());
    },
    async checkout(body) { await wait(); s.packCurrency = currencyFor(body?.locale); save(); return { url: "#simuleret-betaling" }; },
    async subscription(sessionId, currency) {
      await wait();
      if (sessionId) {
        // Return from the (simulated) Stripe Checkout: the session id says which plan was chosen.
        const co = s.sub.checkouts[sessionId];
        if (co) {
          const sb = s.sub; const before = subscription();
          if (!sb.trialStart) sb.trialStart = new Date().toISOString();  // the card is in: the 14 days start now
          const cur = before.status === "none" ? { ...before, status: "trial" as const, trial_days_left: TRIAL_DAYS, trial_ends_at: addDays(sb.trialStart, TRIAL_DAYS) } : before;
          sb.plan = co.plan; sb.interval = co.interval; sb.cancelAtPeriodEnd = false; sb.currency = co.currency ?? "DKK";
          delete sb.checkouts[sessionId];
          // Every draft that waited for the plan comes alive, paid by it.
          for (const t of s.tasks) if (t.status === "draft" && s.pending[t.id]) s.msgs.push(...activate(t, "Med i prøveperioden"));
          const start = cur.status === "trial" && cur.trial_days_left > 2 ? cur.trial_ends_at! : new Date().toISOString();
          const d = new Date(start); if (co.interval === "year") d.setFullYear(d.getFullYear() + 1); else d.setMonth(d.getMonth() + 1);
          sb.periodEnd = d.toISOString();
          sb.status = cur.status === "trial" && cur.trial_days_left > 2 ? "trial" : "active";
          const spec = apiPlans(sb.currency).find((p) => p.key === co.plan)!;
          const fmt = (m: number) => formatPrice(m, sb.currency ?? "DKK", "da");
          ledger("subscription", 0, `${spec.name} valgt · ${co.interval === "year" ? `${fmt(spec.yearly_total_minor)}/år` : `${fmt(spec.monthly_minor)}/md.`} inkl. moms · ${sessionId}`);
        }
      }
      return done(subscription(currency));
    },
    async subscriptionCheckout(body) {
      await wait();
      if (!PLANS.some((p) => p.key === body.plan)) fail(422, "validation_error", "Ukendt plan");
      const id = `cs_fake_${++s.paySeq}`;
      s.sub.checkouts[id] = { plan: body.plan, interval: body.interval, currency: currencyFor(body.locale) };
      save();
      return { url: `/privat/konto?abonnement=ok&session_id=${id}` };
    },
    async subscriptionPortal() { await wait(); return { url: "/privat/konto?portal=simuleret" }; },
    async ledger() { await wait(); return done(s.ledger); },
    async sponsorClaim(taskId) {
      await wait();
      rollSponsorDay();
      const t = find(taskId);
      if (s.sponsorUsed >= SPONSOR_PER_DAY) fail(409, "sponsor_limit", "Du har set 2 sponsorindslag i dag");
      if (t.status !== "draft") return done(t);
      s.sponsorUsed += 1; ledger("sponsor", 0, "Sponsorindslag set – 1 ekstra opgave");
      s.msgs.push(...activate(t, "Sponsorindslag (+1 opgave)"));
      return done(t);
    },

    // ---------- shared lists ----------
    async sharedTasks() { await wait(); return done(s.tasks.filter((t) => t.shared)); },
    async addItem(taskId, body) {
      await wait();
      const t = find(taskId);
      if (t.kind !== "list" || t.my_role === "viewer") fail(403, "forbidden", "Du kan ikke tilføje til listen");
      if (!body.text.trim()) fail(422, "validation_error", "Skriv noget");
      t.items.push(item(nid("i"), cap(body.text.trim()), { note: body.note?.trim() || null, link: body.link?.trim() || null }));
      t.updated_at = new Date().toISOString();
      event(t, `Tilføjet: ${body.text.trim().toLowerCase()}`);
      return done(t);
    },
    async deleteItem(taskId, itemId) {
      await wait();
      const t = find(taskId);
      if (t.my_role === "viewer") fail(403, "forbidden", "Du kan ikke ændre listen");
      t.items = t.items.filter((x) => x.id !== itemId);
      return done(t);
    },
    async reserve(taskId, itemId) {
      await wait();
      const t = find(taskId);
      if (mine(t) || t.share_mode !== "wishlist") fail(403, "forbidden", "Kun de inviterede kan reservere");
      if (s.reservations[itemId] === "other") fail(409, "already_reserved", "Den er allerede reserveret");
      s.reservations[itemId] = "me";
      return done(t);
    },
    async unreserve(taskId, itemId) {
      await wait();
      const t = find(taskId);
      if (s.reservations[itemId] === "me") delete s.reservations[itemId];
      return done(t);
    },
    async share(taskId, body) {
      await wait();
      const t = find(taskId);
      if (!mine(t)) fail(403, "forbidden", "Kun ejeren kan dele listen");
      gate(body.mode === "wishlist" ? ADDON.wishlists : ADDON.sharedLists);
      const token = share(t, body.mode);
      event(t, body.mode === "wishlist" ? "Delt som ønskeliste" : "Delt som fælles liste");
      save();
      const short = `${location.origin}/i/${token}`;
      const text = body.mode === "wishlist" ? `Hej! Jeg har lavet en ønskeliste – se den og reservér her: ${bareLink(short)} – ${FAKE_ME}`
        : `Hej! Jeg har lavet en fælles liste – se den og tilføj her: ${bareLink(short)} – ${FAKE_ME}`;
      return { invite_url: `${location.origin}/privat/invitation/${token}`, token, expires_at: atDay(30, 23, 59),
        short_code: token, short_url: short, suggested_text: text, share_text: text };
    },
    async revokeShare(taskId) {
      await wait();
      const t = find(taskId);
      for (const [k, v] of Object.entries(s.invites)) if (v === taskId) delete s.invites[k];
      t.shared = false; t.share_mode = null; t.members = t.members?.filter((m) => m.is_me) ?? [];
      event(t, "Deling stoppet – invitationslinks virker ikke længere");
      return done(t);
    },
    async invite(token) {
      await wait();
      const t = s.invitable[token] ?? (s.invites[token] ? s.tasks.find((x) => x.id === s.invites[token]) : undefined);
      if (!t) fail(404, "invite_not_found", "Invitationen findes ikke eller er stoppet");
      const owner = t!.members?.find((m) => m.role === "owner");
      const first = owner?.is_me ? FAKE_ME : owner?.name ?? FAKE_OTHER;
      const preview: InvitePreview = { title: t!.title, owner_first_name: first, inviter_first_name: first,
        list_type: t!.list_type ?? null, item_count: t!.items.length, share_mode: t!.share_mode ?? "group",
        resource_type: "list", addon_key: t!.share_mode === "wishlist" ? ADDON.wishlists : ADDON.sharedLists, cta_text: null };
      return preview;
    },
    async acceptInvite(token) {
      await wait();
      const t = s.invitable[token];
      if (!t) {
        const own = s.invites[token] ? find(s.invites[token]) : fail(404, "invite_not_found", "Invitationen findes ikke eller er stoppet");
        return done(own);
      }
      delete s.invitable[token];
      if (!s.ref.viaInvite) s.ref.viaInvite = token;
      t.events.push({ at: new Date().toISOString(), text: "Du blev medlem via et link" });
      s.tasks.push(t);
      return done(t);
    },
    async members(taskId) { await wait(); return done(find(taskId).members ?? []); },
    async removeMember(taskId, memberId) {
      await wait();
      const t = find(taskId);
      if (memberId === "me" && !mine(t)) { s.tasks = s.tasks.filter((x) => x.id !== taskId); save(); return clone({ ...t, members: [] }); }
      if (!mine(t)) fail(403, "forbidden", "Kun ejeren kan fjerne medlemmer");
      t.members = (t.members ?? []).filter((m) => m.id !== memberId);
      return done(t);
    },

    async referrals() {
      await wait();
      const r: Referrals = { invited: s.ref.invited, joined: s.ref.joined, activated: s.ref.activated, credits_earned: s.ref.credits_earned,
        monthly_left: Math.max(0, 10 - s.ref.activated) };
      return r;
    },

    // ---------- groups ----------
    async groups() { await wait(); return done(s.groups); },
    async createGroup(body) {
      await wait();
      if (!body.name.trim()) fail(422, "validation_error", "Giv gruppen et navn");
      return done(makeGroup(body.name, body.members ?? []));
    },
    async updateGroup(id, body) { await wait(); const g = findGroup(id); g.name = body.name.trim() || g.name; return done(g); },
    async deleteGroup(id) { await wait(); s.groups = s.groups.filter((g) => g.id !== id); save(); },
    async addGroupMembers(id, members) { await wait(); const g = findGroup(id); addMembers(g, members); return done(g); },
    async removeGroupMember(id, memberId) { await wait(); const g = findGroup(id); g.members = g.members.filter((m) => m.id !== memberId); return done(g); },
    async suggestedPeople() { await wait(); return clone(SUGGESTED); },
    async shareGroup(taskId, body) {
      await wait();
      const t = find(taskId); const g = findGroup(body.group_id);
      if (!mine(t)) fail(403, "forbidden", "Kun ejeren kan dele listen");
      gate(body.mode === "wishlist" ? ADDON.wishlists : ADDON.sharedLists);
      const token = share(t, body.mode);
      const link = bareLink(`${location.origin}/i/${token}`);
      const what = body.mode === "wishlist" ? "en ønskeliste – se den og reservér her" : `listen «${t.title}» – se den og tilføj her`;
      const st = (s.status[t.id] = s.status[t.id] ?? []);
      const res: ShareGroupResult = { added_in_app: [], sms_group: null, sms_queue: null };
      const smsPeople: GroupMember[] = [];
      for (const m of g.members) {
        if (m.has_dialogbot) {
          if (!t.members!.some((x) => x.name === m.name)) t.members!.push({ id: m.user_id ?? m.id, name: m.name, role: body.role, is_me: false });
          res.added_in_app.push({ name: m.name });
          if (!st.some((x) => x.key === m.id)) st.push({ key: m.id, name: m.name, status: "member" });
        } else if (m.phone_e164) {
          smsPeople.push(m);
          if (!st.some((x) => x.key === m.id)) st.push({ key: m.id, name: m.name, status: "invited" });
        }
      }
      if (smsPeople.length) {
        if (body.style === "group_sms") {
          res.sms_group = { recipients: smsPeople.map((m) => m.phone_e164!), body: `Hej! Jeg har lavet ${what}: ${link} – ${FAKE_ME}`, short_url: link };
        } else {
          res.sms_queue = smsPeople.map((m) => {
            const personal = Array.from({ length: 8 }, () => "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"[Math.floor(Math.random() * 32)]).join("");
            s.invites[personal] = t.id;
            const pl = bareLink(`${location.origin}/i/${personal}`);
            const hi = /^\+?\d/.test(m.name) ? "Hej!" : `Hej ${m.name.split(" ")[0]}!`;
            return { member_id: m.id, name: m.name, phone_e164: m.phone_e164!, body: `${hi} Jeg har lavet ${what}: ${pl} – ${FAKE_ME}`, short_url: pl };
          });
        }
      }
      event(t, `Delt med gruppen ${g.name}`);
      save();
      return clone(res);
    },
    async groupJoinLink(groupId) {
      await wait();
      const g = findGroup(groupId);
      let code = Object.entries(s.joinLinks).find(([, v]) => v === g.id)?.[0];
      if (!code) { const ABC = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; do { code = Array.from({ length: 8 }, () => ABC[Math.floor(Math.random() * 32)]).join(""); } while (s.joinLinks[code]); s.joinLinks[code] = g.id; }
      save();
      const url = `${location.origin}/g/${code}`;
      return { short_url: url, short_code: code, expires_at: atDay(30, 23, 59),
        suggested_text: `Tryk her for at komme med i ${g.name} på Dialogbot, så kan vi dele lister: ${bareLink(url)} – ${FAKE_ME}` };
    },
    async revokeGroupJoinLink(groupId) { await wait(); for (const [k, v] of Object.entries(s.joinLinks)) if (v === groupId) delete s.joinLinks[k]; save(); },
    async groupInvite(code) {
      await wait();
      const g = s.groups.find((x) => x.id === s.joinLinks[code.toUpperCase()]) ?? fail(404, "invite_not_found", "Linket findes ikke eller er stoppet");
      return { group_name: g.name, owner_first_name: FAKE_ME, member_count: g.members.length };
    },
    async searchBusinesses(q) {
      await wait();
      return findShops(q.q).map((k) => { const x = SHOPS[k]; const ph = e164(x.phone);
        return { place_id: `demo-${k}`, name: x.name, address: x.address, phone_display: x.phone ?? "", phone_e164: ph, rating: x.rating, rating_count: x.count,
          open_now: x.open, next_open_text: x.open ? null : x.next ?? null, distance_km: x.km, maps_url: "https://maps.google.com/", source: "demo" as const }; });
    },
    async setLocale() { await wait(); return {}; },
    async setLocation(body) {
      await wait();
      s.location = body.city?.trim() || (body.postcode ? `${body.postcode.trim()}${body.postcode.trim() === "8000" ? " Aarhus C" : ""}` : body.lat != null ? "din position" : null);
      return done(balance());
    },
    async setAssistantName(name, pronoun) { await wait(); return done({ ...balance(), assistant_name: name.trim() || "Peter", assistant_pronoun: pronoun ?? (name.trim() ? "den" : "han") }); },
    async pushPublicKey() { await wait(); return { public_key: "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U" }; },
    async pushSubscribe(body) { await wait(); if (!s.push.includes(body.endpoint)) s.push.push(body.endpoint); save(); return { id: `push-${s.push.length}` }; },
    async pushUnsubscribe(endpoint) { await wait(); s.push = s.push.filter((x) => x !== endpoint); save(); },
    async pushTest() { await wait(); return { sent: s.push.length }; },
    async inviteByCode(code) { return fake.invite(code); },
    async acceptInviteByCode(code) { return fake.acceptInvite(code); },
    async addonInvite(key, body) {
      if (!body.resource_id) fail(422, "validation_error", "resource_id mangler");
      return fake.share(body.resource_id!, { mode: body.mode ?? (key === ADDON.wishlists ? "wishlist" : "group"), role: body.role ?? "editor" });
    },
    async referralLink() {
      await wait();
      const url = `${location.origin}/privat?ref=METTE7Q2`;
      const text = `Hej! Jeg bruger Dialogbot til lister og påmindelser – prøv den gratis her: ${bareLink(url)} – ${FAKE_ME}`;
      return { invite_url: url, token: "METTE7Q2", short_code: "METTE7Q2", short_url: url, expires_at: atDay(365, 0), suggested_text: text, share_text: text };
    },
    async joinGroup(code, body) {
      await wait();
      const g = s.groups.find((x) => x.id === s.joinLinks[code.toUpperCase()]) ?? fail(404, "invite_not_found", "Linket findes ikke eller er stoppet");
      if (!body.name.trim()) fail(422, "validation_error", "Skriv dit navn");
      const phone = body.phone ? body.phone.replace(/[^\d+]/g, "") : "";
      addMembers(g, [{ name: body.name.trim(), phone: phone ? (phone.startsWith("+") ? phone : `+45${phone.slice(-8)}`) : null }]);
      save();
      return { joined: true, already: false, code_sent: false };
    },
    async inviteStatus(taskId) { await wait(); return clone((s.status[taskId] ?? []).map(({ name, status }) => ({ name, status }))); },

    // ---------- add-ons ----------
    async addons() { await wait(); return clone(CATALOG.map(projectAddon)); },
    async enableAddon(key) {
      await wait();
      const a = CATALOG.find((x) => x.key === key) ?? fail(404, "not_found", "Tilføjelsen findes ikke");
      if (a.status === "coming_soon") fail(409, "coming_soon", "Tilføjelsen kommer snart");
      if (!addonIncluded(a)) fail(409, "needs_plan", `${a.name} er med i Plus og Familie`);
      s.addons[key] = true; save();
      return { ...projectAddon(a), enabled: true, enabled_at: new Date().toISOString() };
    },
    async disableAddon(key) {
      await wait();
      const a = CATALOG.find((x) => x.key === key) ?? fail(404, "not_found", "Tilføjelsen findes ikke");
      s.addons[key] = false; save();
      return { ...projectAddon(a), enabled: false, enabled_at: null };
    },

    // ---------- Kalender (the demo never connects anything real) ----------
    async calendar() {
      await wait();
      const off = { available: false, connected: false, status: "not_connected", account_label: "", error: null };
      return { enabled: !!s.addons.kalender, feed: { active: false, created_at: null }, providers: { google: off, microsoft: off }, appointments: [] };
    },
    async newCalendarFeed() { await wait(); return fail(409, "demo", "Kalenderlinket virker kun med en rigtig konto"); },
    async dropCalendarFeed() { await wait(); },
    async connectCalendar() { await wait(); return fail(409, "demo", "Kalenderen kan kun forbindes med en rigtig konto"); },
    async disconnectCalendar() { await wait(); },
    async removeAppointment() { await wait(); return fail(404, "not_found", "Aftalen findes ikke"); },
    // ---------- Fødselsdage (the demo saves nothing) ----------
    async birthdays() { await wait(); return { items: [] }; },
    async addBirthday() { await wait(); return fail(409, "demo", "Fødselsdage gemmes kun med en rigtig konto"); },
    async updateBirthday() { await wait(); return fail(404, "not_found", "Fødselsdagen findes ikke"); },
    async removeBirthday() { await wait(); },
    // ---------- Regninger (the demo saves nothing) ----------
    async bills() { await wait(); return { items: [], month: { month: "", total_minor: 0, total_text: "0 kr.", without_amount: 0, items: [] } }; },
    async addBill() { await wait(); return fail(409, "demo", "Regninger gemmes kun med en rigtig konto"); },
    async updateBill() { await wait(); return fail(404, "not_found", "Regningen findes ikke"); },
    async removeBill() { await wait(); },
    // ---------- Madplan, Læge & tandlæge, Bil & syn, Pakker (the demo saves nothing) ----------
    async foodPreferences() { await wait(); return { people: null, avoid: "", likes: "" }; },
    async saveFoodPreferences() { await wait(); return fail(409, "demo", "Gemmes kun med en rigtig konto"); },
    async healthContacts() { await wait(); return { items: [] }; },
    async removeHealthContact() { await wait(); },
    async car() { await wait(); return { plate: null, inspection_due: null, service_due: null, tire_reminders: false, summary: "", workshop: null }; },
    async saveCar() { await wait(); return fail(409, "demo", "Gemmes kun med en rigtig konto"); },
    async parcels() { await wait(); return { items: [] }; },
    async addParcel() { await wait(); return fail(409, "demo", "Pakker følges kun med en rigtig konto"); },
    async removeParcel() { await wait(); },
    async refreshParcel() { await wait(); return fail(404, "not_found", "Pakken findes ikke"); },
    async searchTrips() { await wait(); return fail(409, "demo", "Rejser søges kun med en rigtig konto"); },
    async latestTrips() { await wait(); return { search: null }; },
    async appOverview() { await wait(); return { summary: "", items: [], partner: null }; },
    async removeAppItem() { await wait(); },
    async uploadAppPhoto() { await wait(); return fail(409, "demo", "Billeder gemmes kun med en rigtig konto"); },

    // ---------- wishes, group gifts and design (simulated) ----------
    async searchWishes() { await wait(); return fail(503, "search_unavailable", "Produktsøgning findes ikke i simuleringen. Indsæt et link, eller opret ønsket selv."); },
    async importWish(link) {
      await wait();
      const l = /^https?:\/\//i.test(link.trim()) ? link.trim() : `https://${link.trim()}`;
      let host = ""; try { host = new URL(l).hostname.replace(/^www\./, ""); } catch { fail(422, "validation_failed", "Linket ser ikke ud som en webadresse"); }
      // The simulation cannot read web pages: the honest answer is «could not be read», with the link kept.
      return { link: l, readable: false, reason: "unreachable", fetched_at: new Date().toISOString(), shop: host };
    },
    async uploadWishImage(file) {
      await wait();
      const url = await asDataUrl(file);
      const key = nid("img");
      images[key] = { url, url_sm: url };
      return { image_key: key, image: images[key] };
    },
    async addWish(taskId, body) {
      await wait();
      const t = find(taskId);
      if (!mine(t) && t.share_mode === "wishlist") fail(403, "owner_only", "Kun ejeren tilføjer ønsker");
      if (!body.text?.trim()) fail(422, "validation_failed", "Giv ønsket en titel");
      t.items.push(wishItem(body, item(nid("i"), "", { quantity: 1 })));
      t.updated_at = new Date().toISOString();
      event(t, `Tilføjet: ${body.text.trim().toLowerCase()}`);
      return done(t);
    },
    async editWish(taskId, itemId, body) {
      await wait();
      const t = find(taskId);
      if (!mine(t)) fail(403, "owner_only", "Kun ejeren retter ønsker");
      t.items = t.items.map((x) => x.id === itemId ? wishItem(body, x) : x);
      return done(t);
    },
    async pledge(taskId, itemId, amount) {
      await wait();
      const { t, g } = giftOf(taskId, itemId);
      if (g.status === "bought") fail(409, "gift_bought", "Gaven er markeret som købt");
      if (g.status === "cancelled") fail(409, "group_gift_off", "Fællesgaven er annulleret");
      if (s.reservations[itemId]) fail(409, "already_reserved", "Ønsket er reserveret");
      if (!Number.isInteger(amount) || amount <= 0) fail(422, "validation_failed", "Skriv et beløb over 0");
      const remaining = g.target - g.others;
      if (amount > remaining) throw { status: 409, code: remaining <= 0 ? "gift_full" : "pledge_exceeds_remaining", message: "Beløbet er højere end det, der mangler", remaining_minor: Math.max(0, remaining), currency: g.currency };
      g.mine = amount;
      return done(t);
    },
    async withdrawPledge(taskId, itemId) {
      await wait();
      const { t, g } = giftOf(taskId, itemId);
      if (g.status === "bought") fail(409, "gift_bought", "Gaven er markeret som købt");
      g.mine = null; if (g.coordinator === "me") g.coordinator = null; g.pendingMe = false;
      return done(t);
    },
    async giftCoordinator(taskId, itemId, action) {
      await wait();
      const { t, g } = giftOf(taskId, itemId);
      if (!g.mine) fail(403, "not_a_participant", "Kun deltagere i fællesgaven kan det");
      if (action === "take") { if (g.coordinator === "other") fail(409, "has_coordinator", "Der er allerede en koordinator"); g.coordinator = "me"; }
      else if (action === "transfer") { if (g.coordinator !== "me") fail(403, "not_coordinator", "Kun koordinatoren kan overdrage rollen"); g.coordinator = "other"; }
      else if (action === "accept") { if (!g.pendingMe) fail(409, "no_handover", "Der er ingen overdragelse til dig"); g.coordinator = "me"; g.pendingMe = false; }
      else if (action === "decline") g.pendingMe = false;
      else if (action === "release" && g.coordinator === "me") g.coordinator = null;
      return done(t);
    },
    async giftBought(taskId, itemId, bought) {
      await wait();
      const { t, g } = giftOf(taskId, itemId);
      if (g.coordinator !== "me") fail(403, "not_coordinator", "Kun gavens koordinator kan markere den som købt");
      g.status = bought ? "bought" : "open";
      return done(t);
    },
    async saveDesign(taskId, body) {
      await wait();
      const t = find(taskId) as Task & { designRaw?: Record<string, unknown> | null };
      if (!mine(t)) fail(403, "read_only", "Kun ejeren kan ændre designet");
      if (body.title !== undefined) { if (!body.title.trim()) fail(422, "validation_failed", "Ønskesedlen skal have en titel"); t.title = body.title.trim(); }
      t.designRaw = body.design ? { ...body.design } : null;
      const c = body.design?.cover;
      const keep = c && t.design?.cover && t.design.cover.key === c.key ? t.design.cover : null;
      t.design = { ...(t.design ?? resolveDesign(null, null)), cover: c && images[c.key] ? { ...images[c.key], key: c.key, zoom: c.zoom, x: c.x, y: c.y } : keep ? { ...keep, zoom: c!.zoom, x: c!.x, y: c!.y } : null };
      return done(t);
    },
    async uploadCover(_taskId, file) {
      await wait();
      const url = await asDataUrl(file);
      const key = nid("cover");
      images[key] = { url, url_sm: url };
      return { key, image: images[key], width: 0, height: 0 };
    },

    // ---------- simulation-only tools ----------
    async simulateMember(taskId) {
      await wait();
      const t = find(taskId);
      if (!t.shared) fail(409, "conflict", "Listen er ikke delt");
      if (!t.members?.some((m) => m.id === "anna")) {
        t.members = [...(t.members ?? []), { id: "anna", name: FAKE_OTHER, role: "editor", is_me: false }]; event(t, `${FAKE_OTHER} blev medlem`);
        if (!s.ref.annaJoined) { s.ref.annaJoined = true; s.ref.joined += 1; }
      }
      if (t.share_mode === "wishlist") {
        const free = t.items.find((x) => !s.reservations[x.id]);
        if (free) s.reservations[free.id] = "other";
      } else {
        const name = ["Kaffe", "Bananer", "Ost"].find((x) => !t.items.some((i) => i.text === x)) ?? "Kiks";
        t.items.push(item(nid("i"), name, { added_by_name: FAKE_OTHER }));
        event(t, `${FAKE_OTHER} tilføjede ${name.toLowerCase()}`);
      }
      t.updated_at = new Date().toISOString();
      return done(t);
    },
    async simulateOutcome(taskId, outcome) {
      await wait();
      const t = find(taskId); const c = t.call;
      if (!c || (t.status !== "in_progress" && !(t.status === "planned" && c.status === "approved"))) fail(409, "conflict", "Opkaldet er ikke i gang");
      const viaPlan = !!s.quotaCalls[t.id];
      if (!viaPlan) s.reserved -= c!.max_credits;
      if (outcome === "answered") {
        const conf = confirmedFor(c!.window);
        const price = s.prices[t.id] ?? "Ikke oplyst";
        c!.result = "answered"; c!.confirmed_text = conf.text; c!.duration_seconds = 130; c!.business_price_text = price;
        c!.business_reply = `Vi kan godt tage cyklen ${lower1(conf.text)}. Et almindeligt eftersyn koster ${price.replace(/ for .*/, "")} hos os – vi ringer, hvis der skal mere til.`;
        t.status = "done"; t.title = `Aflever cyklen hos ${c!.business_name}`; t.next_step = `${conf.text} – aflever cyklen`;
        t.due_at = atDay(conf.off, conf.h, conf.m); t.who = `${c!.business_name} har bekræftet`;
        event(t, `Opkaldet blev besvaret. ${c!.business_name} bekræftede ${lower1(conf.text)}.`);
        if (viaPlan) {
          // An answered call counts against the month's plan quota; nobody answering costs nothing.
          const sb = subscription(); s.sub.callsUsed += 1; delete s.quotaCalls[t.id];
          t.usage_text = `${sb.calls_used + 1} af ${sb.calls_quota} opkald i ${planName()} · 2 min. 10 sek.`;
          ledger("plan_call", 0, `Opkald til ${c!.business_name} · ${sb.calls_used + 1} af ${sb.calls_quota} i ${planName()}`);
          event(t, `Opkald ${sb.calls_used + 1} af ${sb.calls_quota} i ${planName()}`);
        } else {
          ledger("call_charge", -c!.max_credits, `Opkald til ${c!.business_name} · besvaret, 2 min. 10 sek.`);
          t.usage_text = `${c!.max_credits} credits · besvaret opkald, 2 min. 10 sek.`;
          event(t, `${c!.max_credits} credits trukket`);
        }
        s.msgs.push(msg({ kind: "text", about_task_id: t.id, text: `Opkaldet er slut. ${c!.business_name} har bekræftet ${lower1(conf.text)}. Jeg minder dig om det en time før.` }));
      } else {
        c!.result = "no_answer";
        t.status = "awaiting_user"; t.next_step = "Prøv igen eller annullér"; t.who = "Dig"; t.usage_text = "Intet forbrug – ingen svarede";
        if (viaPlan) {
          delete s.quotaCalls[t.id];
          event(t, "Ingen tog telefonen. Opkaldet tæller ikke.");
          s.msgs.push(msg({ kind: "text", about_task_id: t.id, text: `Ingen tog telefonen hos ${c!.business_name}. Opkaldet tæller ikke på din plan.` }));
        } else {
          s.credits += c!.max_credits;
          ledger("release", c!.max_credits, "Ingen svar – reservation frigivet");
          event(t, `Ingen tog telefonen. ${c!.max_credits} credits frigivet.`);
          s.msgs.push(msg({ kind: "text", about_task_id: t.id, text: `Ingen tog telefonen hos ${c!.business_name}. Du har fået dine ${c!.max_credits} credits igen.` }));
        }
      }
      return done(t);
    },
    async completePurchase(draftTaskId) {
      await wait();
      s.paySeq += 1; const ref = `PAY-${s.paySeq}`; s.lastPay = ref;
      s.credits += 10; const packCur = s.packCurrency ?? "DKK";
      ledger("purchase", 10, `Købt 10 credits · ${formatPrice(creditPackPrice(packCur), packCur, "da")} inkl. moms · ${ref}`);
      const t = draftTaskId ? s.tasks.find((x) => x.id === draftTaskId) : undefined;
      let activated = false;
      if (t && t.status === "draft") {
        s.credits -= 1; ledger("task_credit", -1, "Ny opgave efter månedsgrænsen");
        s.msgs.push(...activate(t, "1 credit")); activated = true;
      }
      save();
      return { ref, activated };
    },
    async repeatPayment() { await wait(); return { ref: s.lastPay }; },
    async simulateInviteeActivated() {
      await wait();
      if (!s.ref.annaJoined || s.ref.annaRewarded) return { rewarded: false };
      s.ref.annaRewarded = true; s.ref.activated += 1; s.ref.credits_earned += REFERRAL; s.credits += REFERRAL;
      ledger("referral", REFERRAL, `Invitationsbonus: ${FAKE_OTHER} lavede sin første opgave`);
      save();
      return { rewarded: true };
    },
    async simulateInviteProgress(taskId) {
      await wait();
      const st = s.status[taskId] ?? [];
      const t = find(taskId);
      const opened = st.find((x) => x.status === "opened");
      const invited = st.find((x) => x.status === "invited");
      if (opened) {
        opened.status = "member";
        if (!t.members!.some((m) => m.name === opened.name)) t.members!.push({ id: opened.key, name: opened.name, role: "editor", is_me: false });
        event(t, `${opened.name} kom med`);
      } else if (invited) invited.status = "opened";
      t.updated_at = new Date().toISOString();
      save();
    },
    async startFree() { await wait(); s.sub = { ...s.sub, plan: "none", status: "none", interval: null, trialStart: null, periodEnd: null, cancelAtPeriodEnd: false }; s.credits = 0; save(); },
    async endTrial() { await wait(); s.sub.trialStart = addDays(new Date().toISOString(), -(TRIAL_DAYS + 1)); if (s.sub.plan === "none") s.sub.status = "expired"; save(); },
    async emptyDay() { await wait(); s.tasks = s.tasks.filter((t) => !t.is_example); save(); },
    async reset() { await wait(); s = fresh(); save(); },
  };
  return fake;
}
