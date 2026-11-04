/** Invitations go out from the user's OWN phone: we open their Messages app (or WhatsApp) with the text filled in.
 *  Dialogbot never sends an invite SMS itself, and contacts picked with the Contact Picker never leave the phone. */
export type Platform = "ios" | "android" | "other";

export function platformOf(ua: string): Platform {
  if (/iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && /Mobile/i.test(ua))) return "ios";
  if (/Android/i.test(ua)) return "android";
  return "other";
}

/** iOS: `sms:+45…,+45…?&body=…`; Android (and others): `sms:+45…;+45…?body=…`. */
export function smsHref(body: string, recipients: string[], platform: Platform): string {
  const to = recipients.map((r) => r.replace(/[^\d+]/g, "")).filter(Boolean);
  const enc = encodeURIComponent(body);
  return platform === "ios" ? `sms:${to.join(",")}?&body=${enc}` : `sms:${to.join(";")}?body=${enc}`;
}

export const whatsappHref = (body: string) => `https://wa.me/?text=${encodeURIComponent(body)}`;

/** The link as it reads in an SMS: no scheme ("dialogbot.app/i/K7Q2M9XA"). */
export const bareLink = (url: string) => url.replace(/^https?:\/\//, "").replace(/\/$/, "");

/** GSM-7 can carry æøå; we keep invites to one segment and without emoji. */
export const SMS_LIMIT = 160;
export const hasEmoji = (s: string) => /\p{Extended_Pictographic}/u.test(s);

type ContactsManager = { select(props: string[], opts: { multiple: boolean }): Promise<{ name?: string[]; tel?: string[] }[]> };
export const contactPickerAvailable = () => typeof navigator !== "undefined" && "contacts" in navigator;

/** Android Chrome's Contact Picker: returns phone numbers only, read on the device. */
export async function pickContacts(): Promise<string[]> {
  const c = (navigator as unknown as { contacts: ContactsManager }).contacts;
  const picked = await c.select(["name", "tel"], { multiple: true });
  return picked.map((p) => p.tel?.[0]).filter((x): x is string => !!x);
}

/** Danish numbers to E.164 (+45…). Returns null when it does not look like a phone number. */
export function normalizeDk(raw: string): string | null {
  let d = raw.trim().replace(/[\s().-]/g, "");
  if (d.startsWith("00")) d = `+${d.slice(2)}`;
  if (/^\d{8}$/.test(d)) return `+45${d}`;
  if (/^45\d{8}$/.test(d)) return `+${d}`;
  if (/^\+\d{8,15}$/.test(d)) return d;
  return null;
}
/** Comma/semicolon/newline separated numbers → unique E.164 numbers, plus what could not be read. */
export function parseNumbers(text: string): { ok: string[]; bad: string[] } {
  const ok: string[] = []; const bad: string[] = [];
  for (const part of text.split(/[,;\n]+/).map((x) => x.trim()).filter(Boolean)) {
    const n = normalizeDk(part);
    if (n) { if (!ok.includes(n)) ok.push(n); } else bad.push(part);
  }
  return { ok, bad };
}
/** +4512345678 → "+45 12 34 56 78". */
export const prettyPhone = (e164: string) => e164.startsWith("+45") && e164.length === 11 ? `+45 ${e164.slice(3).replace(/(\d{2})(?=\d)/g, "$1 ")}` : e164;
