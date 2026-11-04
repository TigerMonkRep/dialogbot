/** The visitor's public IP as Vercel reports it (`x-real-ip`, else the first `x-forwarded-for` entry; Vercel overwrites
 *  both, so a client cannot spoof them). Server-side calls forward it in X-Forwarded-For so the backend's per-IP limits
 *  (e.g. the public invite and group-link lookups) count each visitor, not the web server. */
export function visitorIp(h: Headers): string | null {
  const ip = h.get("x-real-ip")?.trim() || h.get("x-forwarded-for")?.split(",")[0]?.trim();
  return ip && /^[0-9a-fA-F:.]{3,45}$/.test(ip) ? ip : null;
}
