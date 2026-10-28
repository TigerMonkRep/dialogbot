import Link from "next/link";
import { API_BASE_URL } from "@/lib/config";
import { isLoggedIn } from "@/lib/api.server";
import { Icon } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { AcceptButton } from "./accept";

const ROLE: Record<string, string> = { owner: "Ejer", admin: "Administrator", staff: "Medarbejder", reader: "Læser" };
const STATUS: Record<string, [string, string]> = {
  pending: ["Afventer svar", "bg-success-soft text-success"], accepted: ["Accepteret", "bg-line text-ink"],
  revoked: ["Tilbagekaldt", "bg-panel-deep text-ink-soft"], expired: ["Udløbet", "bg-danger-soft text-danger"],
};

/** A05: public preview of an invitation; acceptance requires login with the invited address. */
export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const r = await fetch(`${API_BASE_URL}/api/v1/invitations/${encodeURIComponent(token)}`, { cache: "no-store" });
  const loggedIn = await isLoggedIn();
  const inv = r.ok ? await r.json() : null;
  const [statusLabel, statusCls] = STATUS[inv?.status] ?? [inv?.status, "bg-line text-ink"];
  return (
    <AuthFrame icon="group_add" title={inv ? `Invitation til ${inv.workspace_name}` : "Invitation"} subtitle={inv ? "Du er inviteret til et arbejdsrum i Dialogbot." : undefined}>
      {!inv ? <p role="alert" className="text-body-md text-danger">Invitationen findes ikke. Bed en administrator om et nyt link.</p> : (
        <div className="space-y-3">
          <dl className="rounded-lg bg-panel p-3 grid grid-cols-[auto,1fr] gap-x-3 gap-y-2 text-body-md">
            <dt className="text-ink-soft">Arbejdsrum</dt><dd className="font-semibold text-ink">{inv.workspace_name}</dd>
            <dt className="text-ink-soft">Rolle</dt><dd className="font-semibold text-ink">{ROLE[inv.role] ?? inv.role}</dd>
            <dt className="text-ink-soft">E-mail</dt><dd className="break-all">{inv.email}</dd>
            <dt className="text-ink-soft">Status</dt><dd><span className={`px-2 py-0.5 rounded-full text-label-sm font-bold ${statusCls}`}>{statusLabel}</span></dd>
          </dl>
          {inv.status !== "pending" ? <p className="text-body-sm text-ink-soft">Invitationen kan ikke længere bruges. Bed en administrator om en ny.</p>
            : loggedIn ? <AcceptButton token={token} />
            : (
              <div className="space-y-2">
                <p className="text-body-sm text-ink-soft">Log ind eller opret en konto med adressen <strong className="text-ink">{inv.email}</strong> for at acceptere.</p>
                <Link className="w-full h-12 rounded-lg bg-ink text-paper text-label-lg flex items-center justify-center gap-1 hover:bg-ink" href={`/login?next=/invite/${token}`}><Icon name="login" size={18} />Log ind og acceptér</Link>
                <Link className="w-full h-12 rounded-lg bg-panel-deep text-ink text-label-lg flex items-center justify-center gap-1 hover:bg-line" href={`/signup?next=/invite/${token}`}><Icon name="person_add" size={18} />Opret konto</Link>
              </div>
            )}
        </div>
      )}
    </AuthFrame>
  );
}
