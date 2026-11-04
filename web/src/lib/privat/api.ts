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
};
export type ListType = "shopping" | "wishlist" | "todo";
export type ShareMode = "group" | "wishlist";
export type MemberRole = "owner" | "editor" | "viewer";
export type Member = { id: string; name: string; role: MemberRole; is_me: boolean };
export type TaskEvent = { at: string; text: string };
export type TaskCall = {
  business_name: string; address: string; phone_display: string;
  may_ask: string; may_agree: string; may_not: string; window: string; max_credits: number;
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
  list_type?: ListType | null; shared?: boolean; share_mode?: ShareMode | null; my_role?: MemberRole;
  members?: Member[]; updated_at?: string;
};
export type Balance = {
  free_used: number; free_limit: number; credits: number; reserved: number; sponsor_left_today: number;
  phone_display: string | null; phone_verified: boolean;
  /** «Tilføjelse 6» */
  push_enabled?: boolean; location_city?: string | null;
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
export type ChatMessageKind = "text" | "task" | "move" | "clarify" | "call_proposal" | "draft" | "waiting" | "addon" | "share_proposal";
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
export type LedgerEntry = { id: string; kind: string; amount: number; text: string; created_at: string };
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
export type Referrals = { invited: number; joined: number; activated: number; credits_earned: number; monthly_left: number };
export type GrowthRow = { invites_created: number; opened: number; accepted: number; new_users_from_invites: number; activated: number; k_factor: number };
export type Growth = GrowthRow & { by_addon: Record<string, Partial<GrowthRow>> };
export type AddonStatus = "available" | "beta" | "coming_soon";
/** Add-on shop (contract: «Tilføjelse 2»). The catalog comes from the API; the web hard-codes none of it. */
export type Addon = {
  key: string; name: string; tagline: string; description: string; icon: string; category: string; price_text: string;
  pricing: "free" | "credits" | "monthly"; monthly_price_minor: number | null; status: AddonStatus;
  permissions: string[]; requires: string[]; enabled: boolean; enabled_at: string | null;
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
  activate(taskId: string, method: "credit" | "sponsor"): Promise<Task>;
  messages(taskId?: string): Promise<ChatMessage[]>;
  send(text: string, aboutTaskId?: string | null): Promise<SendResult>;
  pickOption(messageId: string, optionId: string): Promise<SendResult>;
  approveCall(taskId: string, body: ApproveBody): Promise<Task>;
  declineCall(taskId: string): Promise<Task>;
  retryCall(taskId: string): Promise<Task>;
  phoneStart(phone: string): Promise<{ sent: true }>;
  phoneVerify(code: string): Promise<Balance>;
  checkout(): Promise<{ url: string }>;
  ledger(): Promise<LedgerEntry[]>;
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
  setLocation(body: LocationBody): Promise<Balance>;
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
}

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
  phoneStart: (phone) => api(`${P}/phone/start`, json({ phone })),
  phoneVerify: (code) => api(`${P}/phone/verify`, json({ code })),
  checkout: () => api(`${P}/credits/checkout`, json({})),
  ledger: () => api(`${P}/ledger`),
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
  setLocation: (body) => api(`${P}/me/location`, { method: "PATCH", body: JSON.stringify(body) }),
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
export const CONFLICT = { needsPhone: "needs_phone", insufficientCredits: "insufficient_credits", outsideHours: "outside_hours", sponsorLimit: "sponsor_limit", addonDisabled: "addon_disabled", comingSoon: "coming_soon",
  demoBusiness: "demo_business", sharingPaused: "sharing_paused", accountMissing: "privat_account_missing",
  emailNotVerified: "email_not_verified", viewAsNotAllowed: "view_as_not_allowed",
  needsBusinessPhone: "needs_business_phone", businessClosed: "business_closed", confirmBusiness: "confirm_business",
  rateLimited: "rate_limited" } as const;
