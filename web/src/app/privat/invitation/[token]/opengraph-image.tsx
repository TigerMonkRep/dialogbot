import { ImageResponse } from "next/og";
import { API_BASE_URL } from "@/lib/config";

export const alt = "Dialogbot – invitation";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

type Preview = { title: string; owner_first_name: string; inviter_first_name?: string; share_mode?: string; list_type?: string | null };

/** Link preview for an invite: the list's title, the inviter's first name and the Dialogbot mark – never the items or
 *  wishes (privacy). Falls back to a generic card when the invite cannot be read. */
export default async function Image({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  let p: Preview | null = null;
  try {
    const r = await fetch(`${API_BASE_URL}/api/v1/privat/invites/${encodeURIComponent(token)}`, { cache: "no-store" });
    if (r.ok) p = (await r.json()) as Preview;
  } catch { /* generic card */ }
  const name = p?.inviter_first_name ?? p?.owner_first_name;
  const wish = p?.share_mode === "wishlist" || p?.list_type === "wishlist";
  const line = name ? (wish ? `${name} har delt sin ønskeliste med dig` : `${name} har delt en liste med dig`) : "Du er inviteret til en liste";
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", background: "#EEF4FB", padding: 64, color: "#14213D", fontFamily: "sans-serif" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 24, background: "#FFFFFF", border: "4px solid #14213D", borderRadius: 32, padding: 48, boxShadow: "16px 16px 0 #14213D" }}>
          <div style={{ fontSize: 34, color: "#3C4659" }}>{line}</div>
          <div style={{ fontSize: 76, fontWeight: 800, lineHeight: 1.05, letterSpacing: -2 }}>{(p?.title ?? "Dialogbot").slice(0, 60)}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ width: 72, height: 72, borderRadius: 20, background: "#2456F6", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 4z" /></svg>
          </div>
          <div style={{ fontSize: 44, fontWeight: 800 }}>Dialogbot</div>
        </div>
      </div>
    ),
    size,
  );
}
