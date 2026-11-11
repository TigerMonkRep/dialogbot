"use client";
/** Dialogbot Privat – typed client for /api/v1/privat (reached through the BFF proxy /api/backend/privat/…).
 *  Types and endpoints follow the shared API contract (privat-api-contract.md) one to one. The same interface is
 *  implemented in-browser by ./fake.ts, so the UI works before the backend is merged. */
import { api, type ApiError } from "@/lib/client";

export type TaskKind = "list" | "reminder" | "call";
export type TaskStatus = "awaiting_user" | "draft" | "planned" | "in_progress" | "awaiting_business" | "done" | "declined";
export type CallResult = "answered" | "no_answer" | "failed" | "declined";

export type TaskItem = {
  id: string; text: string; done: boolean;
  /** Shared lists: who added / ticked it off (null when it was me or the list is not shared). */
  added_by_name?: string | null; done_by_name?: string | null;
  /** Wishlists: null for the owner (never sees reservations); others see whether someone reserved it. */
  reserved?: boolean | null; reserved_by_me?: boolean;
  note?: string | null; link?: string | null;
  // ---- Wishes (docs/privat-api.md «Ønsker, fællesgaver og design»). Optional so older backends still type-check.
  quantity?: number; price_minor?: number | null; currency?: string | null;
  /** "shop": read from the shop's page at price_fetched_at (never updated live); "user": typed by the owner. */
  price_source?: "shop" | "user" | null; price_fetched_at?: string | null;
  shop?: string | null; size?: string | null; color?: string | null; variant?: string | null;
  /** Our stored copy (signed, short-lived links): url = large, url_sm = card size. */
  image?: { url: string; url_sm: string } | null; image_origin?: "shop" | "upload" | null;
  details?: WishDetails | null;
  /** Owner: their setting only. Givers: the agreement (never shown to the owner). null = no group gift. */
  group_gift?: OwnerGroupGift | GiverGroupGift | null;
  /** Removed by the owner while you had a pledge on it (givers only). */
  archived?: boolean;
};
export type WishOptions = { sizes: string[]; colors: string[]; variants: { name?: string; size?: string; color?: string; sku?: string; price_minor?: number; currency?: string; availability?: string; url?: string }[] };
export type WishDetails = { brand?: string; sku?: string; description?: string; availability?: string; source_url?: string; options?: WishOptions };
export type OwnerGroupGift = { enabled: boolean; target_minor: number | null; currency: string | null };
export type GiftStatus = "open" | "full" | "bought" | "cancelled";
export type GiverGroupGift = {
  enabled: true; status: GiftStatus; target_minor: number; currency: string; pledged_minor: number; remaining_minor: number;
  participants: number; my_pledge_minor: number | null; coordinator: { name: string | null; is_me: boolean } | null;
  pending_coordinator_is_me: boolean; pending_coordinator_name?: string | null; is_coordinator: boolean;
  cancel_reason: "wish_removed" | "disabled" | null; can_join: boolean; reserved_by_me: boolean;
  /** Only for the coordinator (to hand the role over): the other participants' first names, never amounts. */
  participant_names: { user_ref: string; name: string }[] | null;
};
export const isGiverGift = (g: TaskItem["group_gift"]): g is GiverGroupGift => !!g && "status" in g;
/** The wish form's body – one model for search, link and «Opret selv». */
export type WishBody = {
  text: string; note?: string | null; link?: string | null; quantity?: number; price_minor?: number | null; currency?: string | null;
  price_source?: "shop" | "user" | null; price_fetched_at?: string | null; shop?: string | null; size?: string | null; color?: string | null;
  variant?: string | null; image_key?: string | null; image_origin?: "shop" | "upload" | null; details?: WishDetails | null;
  group_gift_enabled?: boolean; group_gift_target_minor?: number | null;
};
/** POST /privat/wishes/import: what the shop's page declares. readable=false keeps the link for a manual wish. */
export type WishImport = {
  link: string; readable: boolean; reason: "blocked" | "unreachable" | "not_a_page" | "no_product_data" | null; fetched_at: string;
  title?: string | null; price_minor?: number | null; currency?: string | null; shop?: string | null; size?: string | null;
  color?: string | null; variant?: string | null; details?: WishDetails | null; options?: WishOptions | null;
  image_key?: string | null; image?: { url: string; url_sm: string } | null;
};
export type WishSearchResult = { link: string; title: string; image_url: string | null; price_minor: number | null; currency: string | null; shop: string | null; availability: string | null; options: WishOptions | null };
export type WishDesign = {
  theme: string; accent: string; background: string; text: string; font: string; decorations: boolean;
  subtitle: string | null; date: string | null;
  /** key: the stored cover (already part of its signed link), sent back on «Gem design» to keep it. */
  cover: { key?: string; url: string; url_sm: string; zoom: number; x: number; y: number } | null;
  overrides?: string[]; customized?: boolean;
};
export type WishDesignBody = {
  theme: string; accent?: string | null; background?: string | null; text?: string | null; font?: string | null; decorations?: boolean;
  subtitle?: string | null; date?: string | null; cover?: { key: string; zoom: number; x: number; y: number } | null;
};
export type ListType = "shopping" | "wishlist" | "todo";
export type ShareMode = "group" | "wishlist";
export type MemberRole = "owner" | "editor" | "viewer";
export type Member = { id: string; name: string; role: MemberRole; is_me: boolean };
export type TaskEvent = { at: string; text: string };
export type TaskCall = {
  business_name: string; address: string; phone_display: string;
  may_ask: string; may_agree: string; may_not: string; window: string;
  /** plan = one of the month's plan calls; balance = an extra call paid from the Opkaldssaldo; null = not approved. */
  paid_via?: "plan" | "balance" | null;
  share_phone: boolean; result: CallResult | null;
  confirmed_text: string | null; business_reply: string | null; business_price_text: string | null; duration_seconds: number | null;
  /** Backend detail (docs/privat-api.md): proposed|approved|dialling|in_progress|unknown|answered|no_answer|failed|declined. */
  status?: CallStatus;
  // «Tilføjelse 6» (optional until the backend sends them): opening hours and the number's kind.
  open_now?: boolean | null; next_open_text?: string | null; phone_e164?: string | null; is_mobile?: boolean; source?: "google" | "demo" | "user";
};
export type CallStatus = "proposed" | "approved" | "dialling" | "in_progress" | "unknown" | "answered" | "no_answer" | "failed" | "declined";
export type Task = {
  id: string; kind: TaskKind; title: string; status: TaskStatus;
  next_step: string; due_at: string | null; who: string; usage_text: string; is_example: boolean; created_at: string;
  items: TaskItem[];
  remind_at: string | null;
  call: TaskCall | null;
  /** History, newest last. */
  events: TaskEvent[];
  // Shared lists (contract: «Tilføjelse: delte lister»). Optional so a backend without them still type-checks.
  /** A shopping list's grocery partner (always an advertisement), or null. */
  partner?: AppPartner | null;
  list_type?: ListType | null; shared?: boolean; share_mode?: ShareMode | null; my_role?: MemberRole;
  members?: Member[]; updated_at?: string;
  /** Wishlists: the list's look («Design ønskeseddel»), the same for the owner and everyone it is shared with. */
  design?: WishDesign | null;
  /** Kalender app: the agreed time saved from this task (call or booking), when there is one. */
  appointment?: { id: string; when_text: string; ics_path: string } | null;
};
export type Balance = {
  free_used: number; free_limit: number; sponsor_left_today: number;
  /** The Opkaldssaldo (øre, incl. VAT, in `currency`): what is on it, what open reservations hold, and the prices. */
  balance_minor: number; held_minor: number; currency: string;
  extra_call?: { answered: number; voicemail: number; no_answer: number; minute: number; max: number };
  topups_minor?: number[]; extra_task_minor?: number;
  phone_display: string | null; phone_verified: boolean;
  /** «Tilføjelse 6» */
  push_enabled?: boolean; location_city?: string | null;
  /** What the assistant is called (default «Peter»). */
  assistant_name?: string;
  /** How the texts refer to it: han | hun | den. */
  assistant_pronoun?: "han" | "hun" | "den";
  // Subscription summary (privat-abonnement-brief): the same numbers as GET /privat/subscription, so the header and
  // the paywall need only /me. Optional until the backend sends them.
  plan?: SubscriptionPlan; plan_status?: SubscriptionStatus; trial_days_left?: number;
  calls_quota?: number; calls_used?: number; calls_left?: number; entitled?: boolean;
};
// ---------- subscription (privat-abonnement-brief) ----------
export type PlanKey = "basis" | "plus" | "familie";
export type SubscriptionPlan = "none" | PlanKey;
/** trial = the local 14-day trial (Plus rights, no card); entitled = trial or active/past_due. */
export type SubscriptionStatus = "trial" | "active" | "past_due" | "canceled" | "expired" | "none";
export type BillingInterval = "month" | "year";
/** The plan catalogue comes from the API (prices in øre), so the web hard-codes none of it. */
export type Plan = {
  key: PlanKey; name: string; monthly_minor: number; yearly_monthly_minor: number; yearly_total_minor: number;
  calls: number; people: number; apps_included: boolean; recommended: boolean; features: string[];
};
export type Subscription = {
  plan: SubscriptionPlan; status: SubscriptionStatus; interval: BillingInterval | null;
  trial_ends_at: string | null; trial_days_left: number;
  current_period_end: string | null; cancel_at_period_end: boolean;
  entitled: boolean;
  /** This calendar month (Europe/Copenhagen). */
  calls_quota: number; calls_used: number; calls_left: number;
  people_limit: number; apps_included: boolean;
  /** The currency of `plans` (and of the customer's subscription once paying): DKK, SEK, NOK or EUR. Older backends
   *  leave it out – then the plans are in DKK. */
  currency?: string;
  plans: Plan[];
};
/** Business lookup (Google Places; DemoPlaces without a key – never callable). Show «Data fra Google» with results. */
export type Business = {
  place_id: string; name: string; address: string; phone_display: string; phone_e164: string | null;
  rating: number | null; rating_count: number | null; open_now: boolean | null; next_open_text: string | null;
  distance_km: number | null; maps_url: string; source: "google" | "demo";
};
export type LocationBody = { city?: string; postcode?: string; lat?: number; lng?: number };
export type PushSubscriptionBody = { endpoint: string; keys: { p256dh: string; auth: string } };
export type ChatOption = { id: string; label: string; sub: string };
/** "share_proposal": «Del indkøbslisten med Anna» → a card that makes an invite link on request (nothing is sent). */
export type Bootstrap = { me: Balance; day: Day; tasks: Task[]; messages: ChatMessage[]; ledger: LedgerEntry[]; addons: Addon[] | null; referrals: Referrals | null; groups: Group[]; subscription: Subscription | null };

export type ChatMessageKind = "text" | "task" | "move" | "clarify" | "call_proposal" | "draft" | "waiting" | "addon" | "share_proposal" | "booking_proposal";
export type ChatMessage = {
  id: string; role: "user" | "assistant"; kind: ChatMessageKind;
  text: string; task_id: string | null; about_task_id: string | null; before: string | null; after: string | null;
  options: ChatOption[] | null; links: string[] | null; created_at: string;
  /** kind "share_proposal" with a group: options[0] = {id: group_id, label: group name}. */
  /** kind "addon": the add-on that has to be switched on first. */
  addon_key?: string | null;
  /** clarify: the option the user chose (then the options are closed). */
  answered_option_id?: string | null;
};
export type Day = { awaiting: Task[]; today: Task[]; soon: Task[] };
/** One movement on the Opkaldssaldo: `amount_minor` in øre (minor units of `currency`), incl. VAT. */
export type LedgerEntry = { id: string; kind: string; amount_minor: number; currency: string; text: string; created_at: string };
export type SendResult = { messages: ChatMessage[]; balance: Balance };
/** confirm_business: the user ticked «Det er en virksomhed» for a mobile-looking number.
 *  at_next_open: the business is closed now – call at its next opening time (without it the API answers 409 business_closed). */
export type ApproveBody = { window: string; share_phone: boolean; confirm_business?: boolean; at_next_open?: boolean };
/** short_code/short_url: 8 chars (A–Z, 2–9 without look-alikes) for the SMS text, served by /i/[code] → /privat/invitation/[code].
 *  Optional until the backend has them; GET /privat/invites/{token} must accept the short code as the token. */
export type ShareResult = { invite_url: string; token: string; expires_at: string; short_code?: string; short_url?: string;
  /** Danish, GSM-7, ≤ 160 chars (share_text = suggested_text). */
  suggested_text?: string; share_text?: string };
/** Public invite preview. Never items or reservations (privacy) – only what makes the value clear. */
export type InvitePreview = {
  title: string; owner_first_name: string; list_type: ListType | null; item_count: number; share_mode: ShareMode;
  // «Tilføjelse 3»: one generic invite mechanism for every shareable add-on.
  inviter_first_name?: string; resource_type?: string; addon_key?: string | null; cta_text?: string | null;
  /** Wishlists: how many wishes allow a group gift, and the list's look (never the cover photo). */
  group_gift_count?: number;
  design?: Pick<WishDesign, "theme" | "accent" | "background" | "text" | "font" | "decorations"> | null;
};
// «Tilføjelse 4: Grupper» – Mine folk. Only the owner sees a group; numbers are used only when the user shares from
// their own phone and to recognise people already on Dialogbot.
export type GroupMember = { id: string; name: string; phone_e164: string | null; phone_display?: string | null; user_id: string | null; has_dialogbot?: boolean };
/** Group join without login: the first call sends an SMS code ({joined:false, code_sent:true}); call again with the code. */
export type GroupJoinResult = { joined: boolean; already?: boolean; code_sent?: boolean };
export type Group = { id: string; name: string; members: GroupMember[]; created_at: string };
export type SuggestedPerson = { name: string; has_dialogbot: boolean; user_id?: string | null; phone_e164?: string | null };
export type SmsQueueItem = { member_id: string; name: string; phone_e164: string; body: string; short_url: string };
export type ShareGroupResult = {
  added_in_app: { name: string }[];
  sms_group: { recipients: string[]; body: string; short_url: string } | null;
  sms_queue: SmsQueueItem[] | null;
};
// «Tilføjelse 5»: a group join link people use to add themselves (works on iPhone, where Safari cannot read contacts).
export type GroupJoinLink = { short_url: string; short_code: string; suggested_text: string; expires_at: string };
export type GroupInvitePreview = { group_name: string; owner_first_name: string; member_count: number };
export type InviteStatus = { name: string; status: "member" | "opened" | "invited" };
export type Referrals = { invited: number; joined: number; activated: number; earned_minor: number; currency?: string; reward_minor?: number; monthly_left: number };
export type GrowthRow = { invites_created: number; opened: number; accepted: number; new_users_from_invites: number; activated: number; k_factor: number };
export type Growth = GrowthRow & { by_addon: Record<string, Partial<GrowthRow>> };
export type AddonStatus = "available" | "beta" | "coming_soon";
/** Add-on shop (contract: «Tilføjelse 2»). The catalog comes from the API; the web hard-codes none of it. */
export type Addon = {
  key: string; name: string; tagline: string; description: string; icon: string; category: string; price_text: string;
  pricing: "free" | "balance" | "monthly"; monthly_price_minor: number | null; status: AddonStatus;
  permissions: string[]; requires: string[]; enabled: boolean; enabled_at: string | null;
  // Butikken (privat-abonnement-brief). Optional until the backend sends them.
  /** What it does, 1–2 sentences («Hvad den gør»). */
  what?: string;
  /** What you say to Peter («Sådan siger du det til Peter»). */
  example?: string;
  /** Setup steps shown before «Start opsætningen». */
  steps?: string[];
  /** Can be switched on with the user's current rights (trial/plan or free). */
  included?: boolean;
  /** Needs trial/Plus/Familie – POST /enable answers 409 needs_plan otherwise. */
  requires_plan?: boolean;
  /** Plans whose rights include it (empty = free for everyone). */
  included_in?: string[];
  // «Mine apps» (docs/privat-api.md «Apps: Mine apps og Butikken»). Optional so older backends still type-check.
  /** «Du skal bruge»: what to have at hand. */
  needs?: string[];
  /** What the app holds for the user right now («Syn om 34 dage · 8. dec.»), only while it is on. */
  summary_line?: string | null;
  /** Setup progress: done of total steps. */
  setup?: { done: number; total: number };
  /** Switched off earlier – its data is kept. Null while on, or never used. */
  disabled_at?: string | null;
  notify_requested?: boolean;
  /** Its saved things can be deleted from the app (others live in lists and tasks). */
  data_deletable?: boolean;
};
/** Add-on keys the UI reacts to (shortcuts, share button). Unknown keys still show in the shop. */
export const ADDON = { call: "ring-for-mig", sharedLists: "delte-lister", wishlists: "oenskelister" } as const;

/** Everything the UI needs from the backend. `realPrivat` calls the API, `createFakePrivat()` simulates it. */
export interface PrivatApi {
  account(): Promise<{ workspace_id: string; created: boolean }>;
  me(): Promise<Balance>;
  day(): Promise<Day>;
  tasks(status?: TaskStatus): Promise<Task[]>;
  task(id: string): Promise<Task>;
  toggleItem(taskId: string, itemId: string): Promise<Task>;
  activate(taskId: string, method: "balance" | "sponsor"): Promise<Task>;
  messages(taskId?: string): Promise<ChatMessage[]>;
  send(text: string, aboutTaskId?: string | null): Promise<SendResult>;
  pickOption(messageId: string, optionId: string): Promise<SendResult>;
  approveCall(taskId: string, body: ApproveBody): Promise<Task>;
  declineCall(taskId: string): Promise<Task>;
  retryCall(taskId: string): Promise<Task>;
  /** DELETE: one finished call with its summary and the chat lines about it (409 call_running while it runs). */
  deleteCall(taskId: string): Promise<void>;
  /** DELETE: one chat line. */
  deleteMessage(messageId: string): Promise<void>;
  phoneStart(phone: string): Promise<{ sent: true }>;
  phoneVerify(code: string): Promise<Balance>;
  /** Fill up the Opkaldssaldo at Stripe Checkout: `amount_minor` one of `topups_minor` (50/100/200 kr.); `locale` picks
   *  the market for a customer without a currency yet (da → DKK, sv → SEK, no → NOK, others → EUR). */
  checkout(body?: { amount_minor?: number; locale?: string }): Promise<{ url: string }>;
  ledger(): Promise<LedgerEntry[]>;
  // Subscription (privat-abonnement-brief). sessionId = Stripe Checkout session on return (synchronises first).
  /** `currency` = the market of the page's language: the plans come back in it (a paying customer keeps their own). */
  subscription(sessionId?: string, currency?: string): Promise<Subscription>;
  /** `app`: the app that needed the plan – switched on by the backend once the plan is there. */
  subscriptionCheckout(body: { plan: PlanKey; interval: BillingInterval; code?: string; locale?: string; app?: string }): Promise<{ url: string }>;
  /** Stripe Billing Portal (501 not_configured when Stripe is missing). */
  subscriptionPortal(): Promise<{ url: string }>;
  sponsorClaim(taskId: string): Promise<Task>;
  // Shared lists
  sharedTasks(): Promise<Task[]>;
  addItem(taskId: string, body: { text: string; note?: string; link?: string }): Promise<Task>;
  deleteItem(taskId: string, itemId: string): Promise<Task>;
  reserve(taskId: string, itemId: string): Promise<Task>;
  unreserve(taskId: string, itemId: string): Promise<Task>;
  share(taskId: string, body: { mode: ShareMode; role: "editor" | "viewer" }): Promise<ShareResult>;
  revokeShare(taskId: string): Promise<Task>;
  invite(token: string): Promise<InvitePreview>;
  acceptInvite(token: string): Promise<Task>;
  members(taskId: string): Promise<Member[]>;
  removeMember(taskId: string, memberId: string): Promise<Task>;
  // Business lookup, location, push («Tilføjelse 6»)
  searchBusinesses(q: { q: string; lat?: number; lng?: number; city?: string }): Promise<Business[]>;
  /** One request for everything the shell shows (GET /privat/bootstrap). */
  bootstrap(): Promise<Bootstrap>;
  setLocation(body: LocationBody): Promise<Balance>;
  setAssistantName(name: string, pronoun?: "han" | "hun" | "den"): Promise<Balance>;
  /** The app language, saved on the user (PATCH /auth/me) so e-mails and other devices follow it. */
  setLocale(locale: string): Promise<unknown>;
  pushPublicKey(): Promise<{ public_key: string }>;
  pushSubscribe(body: PushSubscriptionBody): Promise<{ id: string }>;
  pushUnsubscribe(endpoint: string): Promise<void>;
  pushTest(): Promise<{ sent: number }>;
  // Groups («Mine folk»)
  groups(): Promise<Group[]>;
  createGroup(body: { name: string; members?: { name: string; phone: string | null; user_id?: string | null }[] }): Promise<Group>;
  updateGroup(id: string, body: { name: string }): Promise<Group>;
  deleteGroup(id: string): Promise<void>;
  addGroupMembers(id: string, members: { name: string; phone: string | null; user_id?: string | null }[]): Promise<Group>;
  removeGroupMember(id: string, memberId: string): Promise<Group>;
  suggestedPeople(): Promise<SuggestedPerson[]>;
  shareGroup(taskId: string, body: { group_id: string; mode: ShareMode; role: "editor" | "viewer"; style: "group_sms" | "one_by_one" }): Promise<ShareGroupResult>;
  inviteStatus(taskId: string): Promise<InviteStatus[]>;
  groupJoinLink(groupId: string): Promise<GroupJoinLink>;
  revokeGroupJoinLink(groupId: string): Promise<void>;
  groupInvite(code: string): Promise<GroupInvitePreview>;
  joinGroup(code: string, body: { name: string; phone?: string; code?: string }): Promise<GroupJoinResult>;
  /** Invites by short code (dialogbot.app/i/K7Q2M9XA). */
  inviteByCode(code: string): Promise<InvitePreview>;
  acceptInviteByCode(code: string): Promise<Task>;
  /** Generic invite for any shareable add-on. */
  addonInvite(key: string, body: { resource_id?: string; mode?: ShareMode; role?: "editor" | "viewer" }): Promise<ShareResult>;
  /** «Inviter venner»: a general Dialogbot link with the user's referral token. */
  referralLink(): Promise<ShareResult>;
  // Invitations as growth
  referrals(): Promise<Referrals>;
  // Add-ons
  addons(): Promise<Addon[]>;
  enableAddon(key: string): Promise<Addon>;
  disableAddon(key: string): Promise<Addon>;
  /** How many setup steps are done («Trin 2 af 3»). */
  addonSetup(key: string, done: number): Promise<Addon>;
  /** «Giv mig besked» for a «Kommer snart» app (stored on the account). */
  addonNotify(key: string): Promise<Addon>;
  /** Delete a switched-off app's saved data (409 addon_enabled / not_deletable). */
  deleteAddonData(key: string): Promise<{ deleted: number; addon: Addon }>;
  // Kalender app (docs/privat-api.md «Kalender»)
  calendar(): Promise<CalendarState>;
  newCalendarFeed(): Promise<{ url: string; webcal_url: string }>;
  dropCalendarFeed(): Promise<void>;
  connectCalendar(provider: CalendarProvider): Promise<{ url: string }>;
  disconnectCalendar(provider: CalendarProvider): Promise<void>;
  removeAppointment(id: string): Promise<Appointment>;
  // Fødselsdage app
  birthdays(): Promise<{ items: Birthday[] }>;
  addBirthday(body: { name: string; date: string; remind_days_before?: number }): Promise<Birthday & { created: boolean }>;
  updateBirthday(id: string, body: { remind_days_before: number }): Promise<Birthday>;
  removeBirthday(id: string): Promise<void>;
  // Regninger app
  bills(): Promise<{ items: Bill[]; month: BillsMonth }>;
  addBill(body: { name: string; amount?: string; frequency?: BillFrequency; due_date?: string; due_day?: number; remind_days_before?: number }): Promise<Bill & { created: boolean }>;
  updateBill(id: string, body: { remind_days_before: number }): Promise<Bill>;
  removeBill(id: string): Promise<void>;
  // Madplan, Læge & tandlæge, Bil & syn, Pakker
  foodPreferences(): Promise<FoodPreferences>;
  saveFoodPreferences(body: Partial<FoodPreferences>): Promise<FoodPreferences>;
  healthContacts(): Promise<{ items: HealthContact[] }>;
  removeHealthContact(kind: string): Promise<void>;
  car(): Promise<CarInfo>;
  saveCar(body: { plate?: string; inspection_due?: string; service_due?: string; tire_reminders?: boolean }): Promise<CarInfo>;
  parcels(): Promise<{ items: Parcel[] }>;
  addParcel(body: { number: string; label?: string }): Promise<Parcel>;
  removeParcel(number: string): Promise<void>;
  refreshParcel(number: string): Promise<Parcel>;
  // Rejser
  searchTrips(body: TripSearch): Promise<TripResult>;
  latestTrips(): Promise<{ search: TripResult | null }>;
  // The household apps (Abonnementer, Håndværker & tilbud, Fælles udgifter, Garanti, Fest, Flytning, Kæledyr, Hus, Fitness)
  appOverview(key: string): Promise<AppOverview>;
  removeAppItem(key: string, id: string): Promise<void>;
  uploadAppPhoto(key: string, id: string, file: Blob): Promise<{ ok: boolean }>;
  // Wishes, group gifts and design (docs/privat-api.md «Ønsker, fællesgaver og design»)
  /** 503 search_unavailable when product search is not configured – then offer link/manual. */
  searchWishes(q: string): Promise<{ results: WishSearchResult[] }>;
  importWish(link: string): Promise<WishImport>;
  uploadWishImage(file: Blob): Promise<{ image_key: string; image: { url: string; url_sm: string } | null }>;
  addWish(taskId: string, body: WishBody): Promise<Task>;
  editWish(taskId: string, itemId: string, body: Partial<WishBody>): Promise<Task>;
  /** Join/change my pledge (minor units). 409 pledge_exceeds_remaining carries remaining_minor. */
  pledge(taskId: string, itemId: string, amountMinor: number, key: string): Promise<Task>;
  withdrawPledge(taskId: string, itemId: string): Promise<Task>;
  giftCoordinator(taskId: string, itemId: string, action: "take" | "transfer" | "accept" | "decline" | "cancel_transfer" | "release", to?: string): Promise<Task>;
  giftBought(taskId: string, itemId: string, bought: boolean): Promise<Task>;
  saveDesign(taskId: string, body: { title?: string; design: WishDesignBody | null }): Promise<Task>;
  uploadCover(taskId: string, file: Blob): Promise<{ key: string; image: { url: string; url_sm: string } | null; width: number; height: number }>;
}

// ---------- Household apps (one generic overview) ----------
export type AppPartner = { category: string; name: string; url: string; text: string; note: string };
export type AppOverview = {
  summary: string;
  items: { id: string; text: string; sub: string; share_text?: string; photo?: boolean; photo_url?: string | null }[];
  partner: AppPartner | null;
};

// ---------- Rejser ----------
export type TripSearch = {
  origin: string; destinations: string[]; depart_date?: string; month?: string; nights?: number;
  adults: number; children: number; budget_dkk?: number; trip_type?: string; direct_only?: boolean;
};
export type TripOffer = {
  id: string; provider: string; origin: string; destination: string; total_dkk: number; airline: string;
  depart_at: string; return_at: string; stops: number | null; book_url: string; price_note: string; sponsored?: boolean;
};
export type TripResult = { id: string; at: string; params: TripSearch; offers: TripOffer[]; over_budget: number; errors: string[] };

// ---------- Madplan, Læge & tandlæge, Bil & syn, Pakker ----------
export type FoodPreferences = { people: number | null; avoid: string; likes: string };
export type HealthContact = { kind: "laege" | "tandlaege"; label: string; name: string; phone_display: string };
export type CarInfo = {
  plate: string | null; inspection_due: string | null; service_due: string | null; tire_reminders: boolean; summary: string;
  workshop: { name: string; phone_display: string } | null;
};
export type Parcel = { number: string; label: string | null; status: string | null; text: string; event: string; carrier: string; done: boolean; updated_at?: string };

// ---------- Regninger ----------
export type BillFrequency = "monthly" | "quarterly" | "half_yearly" | "yearly" | "once";
export type Bill = {
  id: string; name: string; amount_minor: number | null; amount_text: string; frequency: BillFrequency; frequency_text: string;
  next_due: string; due_text: string; days_until: number; remind_days_before: number;
};
export type BillsMonth = { month: string; total_minor: number; total_text: string; without_amount: number; items: (Bill & { due_in_month: string })[] };

// ---------- Fødselsdage ----------
export type Birthday = {
  id: string; name: string; month: number; day: number; year: number | null; date_text: string;
  next_date: string; days_until: number; turns: number | null; remind_days_before: number;
};

// ---------- Kalender ----------
export type CalendarProvider = "google" | "microsoft";
export type Appointment = {
  id: string; task_id: string | null; source: "call" | "browser" | "manual"; title: string; location: string; notes: string;
  starts_at: string; ends_at: string; status: "confirmed" | "cancelled"; when_text: string;
  /** /api/v1/privat/appointments/{id}.ics – fetch through the BFF as /api/backend/privat/appointments/{id}.ics */
  ics_path: string;
  sync: Record<string, { synced: boolean; error: string | null }>;
};
export type CalendarProviderState = { available: boolean; connected: boolean; status: string; account_label: string; error: string | null };
export type CalendarState = {
  enabled: boolean;
  /** The secret subscription link is shown only once (newCalendarFeed); here only whether it exists. */
  feed: { active: boolean; created_at: string | null };
  providers: Record<CalendarProvider, CalendarProviderState>;
  appointments: Appointment[];
};
/** Same-origin download link for an appointment's .ics file (the BFF adds the login). */
export const icsHref = (a: { ics_path: string }) => `/api/backend${a.ics_path.replace(/^\/api\/v1/, "")}`;

const P = "/privat";
const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body ?? {}) });
const idem = (init: RequestInit): RequestInit => ({ ...init, headers: { ...(init.headers as Record<string, string> | undefined), "idempotency-key": newKey() } });
const enc = encodeURIComponent;

export function newKey(): string {
  try { return crypto.randomUUID(); } catch { return `${Date.now()}-${Math.random().toString(36).slice(2)}`; }
}

export const realPrivat: PrivatApi = {
  account: () => api(`${P}/account`, json({})),
  me: () => api(`${P}/me`),
  day: () => api(`${P}/day`),
  tasks: (status) => api(`${P}/tasks${status ? `?status=${enc(status)}` : ""}`),
  task: (id) => api(`${P}/tasks/${enc(id)}`),
  toggleItem: (taskId, itemId) => api(`${P}/tasks/${enc(taskId)}/items/${enc(itemId)}/toggle`, json({})),
  activate: (taskId, method) => api(`${P}/tasks/${enc(taskId)}/activate`, json({ method })),
  messages: (taskId) => api(`${P}/messages${taskId ? `?task_id=${enc(taskId)}` : ""}`),
  send: (text, aboutTaskId) => api(`${P}/messages`, idem(json(aboutTaskId ? { text, about_task_id: aboutTaskId } : { text }))),
  pickOption: (messageId, optionId) => api(`${P}/messages/${enc(messageId)}/options/${enc(optionId)}`, json({})),
  approveCall: (taskId, body) => api(`${P}/calls/${enc(taskId)}/approve`, idem(json(body))),
  declineCall: (taskId) => api(`${P}/calls/${enc(taskId)}/decline`, json({})),
  retryCall: (taskId) => api(`${P}/calls/${enc(taskId)}/retry`, json({})),
  deleteCall: (taskId) => api(`${P}/calls/${enc(taskId)}`, { method: "DELETE" }),
  deleteMessage: (messageId) => api(`${P}/messages/${enc(messageId)}`, { method: "DELETE" }),
  phoneStart: (phone) => api(`${P}/phone/start`, json({ phone })),
  phoneVerify: (code) => api(`${P}/phone/verify`, json({ code })),
  checkout: (body) => api(`${P}/balance/checkout`, json(body ?? {})),
  ledger: () => api(`${P}/ledger`),
  subscription: (sessionId, currency) => {
    const q = [sessionId ? `session_id=${enc(sessionId)}` : "", currency ? `currency=${enc(currency)}` : ""].filter(Boolean).join("&");
    return api(`${P}/subscription${q ? `?${q}` : ""}`);
  },
  // One subscription per account (PC-SUB-07): with a running one the API answers 409 subscription_exists – then the
  // customer goes to Stripe's Billing Portal (change plan/interval there) instead of a second Checkout.
  subscriptionCheckout: async (body) => {
    try { return await api<{ url: string }>(`${P}/subscription/checkout`, json(body)); }
    catch (e) {
      if ((e as Partial<ApiError>)?.code === "subscription_exists") return api<{ url: string }>(`${P}/subscription/portal`, json({}));
      throw e;
    }
  },
  subscriptionPortal: () => api(`${P}/subscription/portal`, json({})),
  sponsorClaim: (taskId) => api(`${P}/sponsor/claim`, json({ task_id: taskId })),
  sharedTasks: () => api(`${P}/tasks?shared=1`),
  addItem: (taskId, body) => api(`${P}/tasks/${enc(taskId)}/items`, json(body)),
  deleteItem: (taskId, itemId) => api(`${P}/tasks/${enc(taskId)}/items/${enc(itemId)}`, { method: "DELETE" }),
  reserve: (taskId, itemId) => api(`${P}/tasks/${enc(taskId)}/items/${enc(itemId)}/reserve`, json({})),
  unreserve: (taskId, itemId) => api(`${P}/tasks/${enc(taskId)}/items/${enc(itemId)}/unreserve`, json({})),
  share: (taskId, body) => api(`${P}/tasks/${enc(taskId)}/share`, json(body)),
  revokeShare: (taskId) => api(`${P}/tasks/${enc(taskId)}/share/revoke`, json({})),
  invite: (token) => api(`${P}/invites/${enc(token)}`),
  acceptInvite: (token) => api(`${P}/invites/${enc(token)}/accept`, json({})),
  members: (taskId) => api(`${P}/tasks/${enc(taskId)}/members`),
  removeMember: (taskId, memberId) => api(`${P}/tasks/${enc(taskId)}/members/${enc(memberId)}`, { method: "DELETE" }),
  referrals: () => api(`${P}/referrals`),
  searchBusinesses: (q) => {
    const p = new URLSearchParams({ q: q.q });
    if (q.lat != null && q.lng != null) { p.set("lat", String(q.lat)); p.set("lng", String(q.lng)); }
    if (q.city) p.set("city", q.city);
    return api(`${P}/businesses/search?${p}`);
  },
  bootstrap: () => api(`${P}/bootstrap`),
  setLocation: (body) => api(`${P}/me/location`, { method: "PATCH", body: JSON.stringify(body) }),
  setAssistantName: (name, pronoun) => api(`${P}/me/assistant`, { method: "PATCH", body: JSON.stringify({ name, pronoun: pronoun ?? null }) }),
  setLocale: (locale) => api("/auth/me", { method: "PATCH", body: JSON.stringify({ locale }) }),
  pushPublicKey: () => api(`${P}/push/public-key`),
  pushSubscribe: (body) => api(`${P}/push/subscriptions`, json(body)),
  pushUnsubscribe: (endpoint) => api(`${P}/push/subscriptions`, { method: "DELETE", body: JSON.stringify({ endpoint }) }),
  pushTest: () => api(`${P}/push/test`, json({})),
  groups: () => api(`${P}/groups`),
  createGroup: (body) => api(`${P}/groups`, json(body)),
  updateGroup: (id, body) => api(`${P}/groups/${enc(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteGroup: (id) => api(`${P}/groups/${enc(id)}`, { method: "DELETE" }),
  addGroupMembers: (id, members) => api(`${P}/groups/${enc(id)}/members`, json({ members })),
  removeGroupMember: (id, memberId) => api(`${P}/groups/${enc(id)}/members/${enc(memberId)}`, { method: "DELETE" }),
  suggestedPeople: () => api(`${P}/people/suggested`),
  shareGroup: (taskId, body) => api(`${P}/tasks/${enc(taskId)}/share-group`, json(body)),
  inviteStatus: (taskId) => api(`${P}/tasks/${enc(taskId)}/invite-status`),
  groupJoinLink: (groupId) => api(`${P}/groups/${enc(groupId)}/join-link`, json({})),
  revokeGroupJoinLink: (groupId) => api(`${P}/groups/${enc(groupId)}/join-link/revoke`, json({})),
  groupInvite: (code) => api(`${P}/group-invites/by-code/${enc(code)}`),
  joinGroup: (code, body) => api(`${P}/group-invites/by-code/${enc(code)}/join`, json(body)),
  inviteByCode: (code) => api(`${P}/invites/by-code/${enc(code)}`),
  acceptInviteByCode: (code) => api(`${P}/invites/by-code/${enc(code)}/accept`, json({})),
  addonInvite: (key, body) => api(`${P}/addons/${enc(key)}/invites`, json(body)),
  referralLink: () => api(`${P}/referrals/link`, json({})),
  addons: () => api(`${P}/addons`),
  enableAddon: (key) => api(`${P}/addons/${enc(key)}/enable`, json({})),
  disableAddon: (key) => api(`${P}/addons/${enc(key)}/disable`, json({})),
  addonSetup: (key, done) => api(`${P}/addons/${enc(key)}/setup`, { method: "PUT", body: JSON.stringify({ done }) }),
  addonNotify: (key) => api(`${P}/addons/${enc(key)}/notify`, json({})),
  deleteAddonData: (key) => api(`${P}/addons/${enc(key)}/data`, { method: "DELETE" }),
  calendar: () => api(`${P}/calendar`),
  newCalendarFeed: () => api(`${P}/calendar/feed`, json({})),
  dropCalendarFeed: () => api(`${P}/calendar/feed`, { method: "DELETE" }),
  connectCalendar: (provider) => api(`${P}/calendar/connect/${enc(provider)}`, json({})),
  disconnectCalendar: (provider) => api(`${P}/calendar/connect/${enc(provider)}`, { method: "DELETE" }),
  removeAppointment: (id) => api(`${P}/appointments/${enc(id)}`, { method: "DELETE" }),
  birthdays: () => api(`${P}/birthdays`),
  addBirthday: (body) => api(`${P}/birthdays`, json(body)),
  updateBirthday: (id, body) => api(`${P}/birthdays/${enc(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
  removeBirthday: (id) => api(`${P}/birthdays/${enc(id)}`, { method: "DELETE" }),
  bills: () => api(`${P}/bills`),
  addBill: (body) => api(`${P}/bills`, json(body)),
  updateBill: (id, body) => api(`${P}/bills/${enc(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
  removeBill: (id) => api(`${P}/bills/${enc(id)}`, { method: "DELETE" }),
  foodPreferences: () => api(`${P}/meals/preferences`),
  saveFoodPreferences: (body) => api(`${P}/meals/preferences`, { method: "PUT", body: JSON.stringify(body) }),
  healthContacts: () => api(`${P}/health-contacts`),
  removeHealthContact: (kind) => api(`${P}/health-contacts/${enc(kind)}`, { method: "DELETE" }),
  car: () => api(`${P}/car`),
  saveCar: (body) => api(`${P}/car`, { method: "PUT", body: JSON.stringify(body) }),
  parcels: () => api(`${P}/parcels`),
  addParcel: (body) => api(`${P}/parcels`, json(body)),
  removeParcel: (number) => api(`${P}/parcels/${enc(number)}`, { method: "DELETE" }),
  refreshParcel: (number) => api(`${P}/parcels/${enc(number)}/refresh`, json({})),
  appOverview: (key) => api(`${P}/apps/${enc(key)}/overview`),
  removeAppItem: (key, id) => api(`${P}/apps/${enc(key)}/items/${enc(id)}`, { method: "DELETE" }),
  uploadAppPhoto: (key, id, file) => api(`${P}/apps/${enc(key)}/items/${enc(id)}/photo`,
    { method: "POST", body: file, headers: { "content-type": file.type || "application/octet-stream" } }),
  searchWishes: (q) => api(`${P}/wishes/search?q=${enc(q)}`),
  importWish: (link) => api(`${P}/wishes/import`, json({ link })),
  uploadWishImage: (file) => api(`${P}/wishes/images`, { method: "POST", body: file, headers: { "content-type": file.type || "application/octet-stream" } }),
  addWish: (taskId, body) => api(`${P}/tasks/${enc(taskId)}/wishes`, json(body)),
  editWish: (taskId, itemId, body) => api(`${P}/tasks/${enc(taskId)}/wishes/${enc(itemId)}`, { method: "PATCH", body: JSON.stringify(body) }),
  pledge: (taskId, itemId, amount_minor, key) => api(`${P}/tasks/${enc(taskId)}/items/${enc(itemId)}/gift/pledge`,
    { method: "PUT", body: JSON.stringify({ amount_minor }), headers: { "idempotency-key": key } }),
  withdrawPledge: (taskId, itemId) => api(`${P}/tasks/${enc(taskId)}/items/${enc(itemId)}/gift/pledge`, { method: "DELETE" }),
  giftCoordinator: (taskId, itemId, action, to) => api(`${P}/tasks/${enc(taskId)}/items/${enc(itemId)}/gift/coordinator`, json({ action, to })),
  giftBought: (taskId, itemId, bought) => api(`${P}/tasks/${enc(taskId)}/items/${enc(itemId)}/gift/bought`, json({ bought })),
  saveDesign: (taskId, body) => api(`${P}/tasks/${enc(taskId)}/design`, { method: "PUT", body: JSON.stringify(body) }),
  uploadCover: (taskId, file) => api(`${P}/tasks/${enc(taskId)}/design/cover`, { method: "POST", body: file, headers: { "content-type": file.type || "application/octet-stream" } }),
  searchTrips: (body) => api(`${P}/trips/search`, json(body)),
  latestTrips: () => api(`${P}/trips/latest`),
};

/** The Privat API is not there (not merged/deployed) or switched off: the UI falls back to the simulation. */
export function isUnavailable(e: unknown): boolean {
  const err = e as Partial<ApiError> | undefined;
  if (!err) return false;
  if (err.code === "privat_account_missing" || err.code === "invite_invalid" || err.code === "invite_not_found") return false;
  return err.status === 404 || err.code === "privat_not_enabled" || err.code === "feature_disabled" || err.code === "privat_disabled";
}
/** Clarify option ids the web handles itself: ask for the location (geolocation only after a tap, or a typed city/postcode),
 *  then the same message is sent again. Business results use ids "place:<place_id>" (demo results "place:demo-…"). */
export const LOCATION_OPTION = { geo: "location:geo", city: "location:city" } as const;
export const isPlaceOption = (id: string) => id.startsWith("place:");
export const isDemoPlace = (id: string) => id.startsWith("place:demo");

/** Short invite codes: 8 characters, A–Z and 2–9 without look-alikes. Anything else is a long token. */
export const isShortCode = (s: string) => /^[A-HJ-NP-Z2-9]{8}$/.test(s);

/** 409 codes from POST /calls/{id}/approve and /tasks/{id}/activate. */
export const CONFLICT = { needsPhone: "needs_phone", insufficientBalance: "insufficient_balance", outsideHours: "outside_hours", sponsorLimit: "sponsor_limit", addonDisabled: "addon_disabled", comingSoon: "coming_soon",
  demoBusiness: "demo_business", sharingPaused: "sharing_paused", accountMissing: "privat_account_missing",
  emailNotVerified: "email_not_verified", viewAsNotAllowed: "view_as_not_allowed",
  needsBusinessPhone: "needs_business_phone", businessClosed: "business_closed", confirmBusiness: "confirm_business",
  rateLimited: "rate_limited",
  /** 409 from /addons/{key}/enable and /calls/{id}/approve: needs trial/Plus/Familie. */
  needsPlan: "needs_plan", notConfigured: "not_configured" } as const;

/** Plan rights apply (trial, active or past_due). */
export const entitled = (b: Balance | Subscription | null | undefined): boolean => !!b?.entitled;
