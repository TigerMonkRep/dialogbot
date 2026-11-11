import { createHmac } from "node:crypto";

/** The visitor's public IP as Vercel reports it (`x-real-ip`, else the first `x-forwarded-for` entry; Vercel overwrites
 *  both, so a client cannot spoof them). Server-side calls forward it in X-Forwarded-For so the backend's per-IP limits
 *  (e.g. the public invite and group-link lookups) count each visitor, not the web server. */
export function visitorIp(h: Headers): string | null {
  const ip = h.get("x-real-ip")?.trim() || h.get("x-forwarded-for")?.split(",")[0]?.trim();
  return ip && /^[0-9a-fA-F:.]{3,45}$/.test(ip) ? ip : null;
}

/** Headers that carry the visitor's IP to the backend. With CLIENT_IP_SECRET (server-only, same value as the API's) the
 *  IP is also signed, and the backend then trusts only the signed value or the address Render's edge appended – a
 *  forged X-Forwarded-For no longer moves the per-IP limits (F-PS-02, app/modules/privat/lookup_limits.client_ip). */
export function visitorIpHeaders(h: Headers): Record<string, string> {
  const ip = visitorIp(h);
  if (!ip) return {};
  const out: Record<string, string> = { "x-forwarded-for": ip };
  const secret = process.env.CLIENT_IP_SECRET;
  if (secret) {
    out["x-dialogbot-client-ip"] = ip;
    out["x-dialogbot-client-ip-sig"] = createHmac("sha256", secret).update(`client-ip:${ip}`).digest("hex");
  }
  return out;
}
