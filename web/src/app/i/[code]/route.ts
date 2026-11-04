import { NextRequest, NextResponse } from "next/server";

/** Short invite link used in SMS texts (dialogbot.app/i/K7Q2M9XA): 8 characters, A–Z and 2–9 without look-alikes.
 *  The backend accepts the short code wherever it accepts an invite token, so this only redirects. */
export async function GET(req: NextRequest, ctx: { params: Promise<{ code: string }> }) {
  const { code } = await ctx.params;
  const clean = code.toUpperCase();
  if (!/^[A-HJ-NP-Z2-9]{8}$/.test(clean)) return NextResponse.redirect(new URL("/privat", req.url), 307);
  return NextResponse.redirect(new URL(`/privat/invitation/${clean}`, req.url), 307);
}
