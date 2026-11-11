import { ImageResponse } from "next/og";
import { headers } from "next/headers";
import { API_BASE_URL } from "@/lib/config";
import { visitorIpHeaders } from "@/lib/visitor-ip";
import { DEFAULT_LOCALE, isLocale } from "@/i18n/config";
import { messagesFor } from "@/i18n/server";
import { makeT } from "@/i18n/translate";

export const alt = "Dialogbot – invitation";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

type Preview = { title: string; owner_first_name: string; inviter_first_name?: string; share_mode?: string; list_type?: string | null; lang?: string };

/** Link preview for an invite: the list's title, the inviter's first name and the Dialogbot mark – never the items or
 *  wishes (privacy). Falls back to a generic card when the invite cannot be read. The line is in the INVITATION's
 *  language (`lang` from the API: the inviter's), not the crawler's – a preview fetched by a messenger has no cookie. */
export default async function Image({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  let p: Preview | null = null;
  try {
    const r = await fetch(`${API_BASE_URL}/api/v1/privat/invites/${encodeURIComponent(token)}`,
      { cache: "no-store", headers: visitorIpHeaders(await headers()) });
    if (r.ok) p = (await r.json()) as Preview;
  } catch { /* generic card */ }
  const name = p?.inviter_first_name ?? p?.owner_first_name;
  const wish = p?.share_mode === "wishlist" || p?.list_type === "wishlist";
  const lang = isLocale(p?.lang) ? p.lang : DEFAULT_LOCALE;
  const t = makeT(messagesFor(lang), messagesFor(DEFAULT_LOCALE), "privat.inviteOg", lang);
  const line = name ? t(wish ? "wishlist" : "list", { name }) : t("generic");
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", background: "#FFF4E6", padding: 64, color: "#14213D", fontFamily: "sans-serif" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 24, background: "#FFFFFF", border: "4px solid #14213D", borderRadius: 32, padding: 48, boxShadow: "16px 16px 0 #14213D" }}>
          <div style={{ fontSize: 34, color: "#3C4659" }}>{line}</div>
          <div style={{ fontSize: 76, fontWeight: 800, lineHeight: 1.05, letterSpacing: -2 }}>{(p?.title ?? "Dialogbot").slice(0, 60)}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ width: 72, height: 72, borderRadius: 20, background: "#C4461A", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 4z" /></svg>
          </div>
          <div style={{ fontSize: 44, fontWeight: 800 }}>Dialogbot</div>
        </div>
      </div>
    ),
    size,
  );
}
