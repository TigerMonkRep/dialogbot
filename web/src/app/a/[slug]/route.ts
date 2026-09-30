import { NextRequest, NextResponse } from "next/server";
import { API_BASE_URL, REFERRAL_COOKIE, REFERRAL_MAX_AGE } from "@/lib/config";
import { PREVIEW_COOKIE, PREVIEW_MAX_AGE, cookieValue, gateEnabled } from "@/lib/preview-gate";

/** An ambassador's personal link: dialogbot.dk/a/{slug}.
 *  Counts the visit, remembers the ambassador for 90 days (first-party cookie, used when the customer creates a
 *  workspace) and opens the front page with the ambassador's welcome. An approved ambassador's link also works
 *  as an invitation past the preview gate. Unknown or inactive links just open the front page. */
export async function GET(req: NextRequest, ctx: { params: Promise<{ slug: string }> }) {
  const { slug } = await ctx.params;
  const ref = slug.toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 60);
  const home = new URL("/", req.url);
  let active = false;
  try {
    const r = await fetch(`${API_BASE_URL}/api/v1/public/ambassadors/${encodeURIComponent(ref)}`, { cache: "no-store" });
    active = r.ok;
    if (active) await fetch(`${API_BASE_URL}/api/v1/public/ambassadors/${encodeURIComponent(ref)}/visit`, { method: "POST", cache: "no-store" });
  } catch { /* the page still opens */ }
  if (active) home.searchParams.set("anbefalet", ref);
  const res = NextResponse.redirect(home);
  res.headers.set("cache-control", "no-store");
  if (active) {
    const secure = process.env.NODE_ENV === "production";
    res.cookies.set(REFERRAL_COOKIE, ref, { httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: REFERRAL_MAX_AGE });
    const v = gateEnabled() ? await cookieValue() : null;
    if (v) res.cookies.set(PREVIEW_COOKIE, v, { httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: PREVIEW_MAX_AGE });
  }
  return res;
}
