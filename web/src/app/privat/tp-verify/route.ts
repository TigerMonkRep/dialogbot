import { TP_FRAME_SANDBOX, TP_SCRIPT_SRC, travelpayoutsVerifyEnabled } from "@/lib/travelpayouts";

export const dynamic = "force-dynamic";

const NOT_FOUND = () => new Response("Not found", { status: 404, headers: { "cache-control": "no-store", "x-robots-tag": "noindex" } });

/** The sandboxed document that carries the Travelpayouts site script (see lib/travelpayouts.ts). Only the /privat
 *  landing embeds it; 404 while NEXT_PUBLIC_TRAVELPAYOUTS_VERIFY is not 1. Served only as a same-origin iframe
 *  (Sec-Fetch-Dest/Site): a sandboxed document that is itself the top-level page may still navigate itself, so opened
 *  directly it would be a redirect to wherever the script wants – there it is a 404 instead (fails closed in browsers
 *  without Fetch Metadata). */
export function GET(req: Request) {
  if (!travelpayoutsVerifyEnabled()) return NOT_FOUND();
  if (req.headers.get("sec-fetch-dest") !== "iframe" || req.headers.get("sec-fetch-site") !== "same-origin") return NOT_FOUND();
  const html = `<!doctype html><html lang="da"><head><meta charset="utf-8"><meta name="robots" content="noindex"><title>Travelpayouts</title><script async src="${TP_SCRIPT_SRC}"></script></head><body></body></html>`;
  return new Response(html, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      // Second lock: the document is sandboxed even if the iframe attribute on /privat were ever lost.
      "content-security-policy": `sandbox ${TP_FRAME_SANDBOX}; frame-ancestors 'self'`,
      "x-robots-tag": "noindex",
      "referrer-policy": "strict-origin-when-cross-origin",
      "cache-control": "no-store",
    },
  });
}
