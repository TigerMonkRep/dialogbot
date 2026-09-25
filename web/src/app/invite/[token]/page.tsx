import Link from "next/link";
import { API_BASE_URL } from "@/lib/config";
import { isLoggedIn } from "@/lib/api.server";
import { Icon } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { AcceptButton } from "./accept";

const ROLE: Record<string, string> = { owner: "Ejer", admin: "Administrator", staff: "Medarbejder", reader: "Læser" };
const STATUS: Record<string, [string, string]> = {
  pending: ["Afventer svar", "bg-secondary-container text-on-secondary-container"], accepted: ["Accepteret", "bg-surface-container-high text-primary"],
  revoked: ["Tilbagekaldt", "bg-surface-container-highest text-on-surface-variant"], expired: ["Udløbet", "bg-error-container text-on-error-container"],
};

/** A05: public preview of an invitation; acceptance requires login with the invited address. */
export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const r = await fetch(`${API_BASE_URL}/api/v1/invitations/${encodeURIComponent(token)}`, { cache: "no-store" });
  const loggedIn = await isLoggedIn();
  const inv = r.ok ? await r.json() : null;
  const [statusLabel, statusCls] = STATUS[inv?.status] ?? [inv?.status, "bg-surface-container-high text-on-surface"];
  return (
    <AuthFrame code="A05" icon="group_add" title={inv ? `Invitation til ${inv.workspace_name}` : "Invitation"} subtitle={inv ? "Du er inviteret til et arbejdsrum i Dialogbot." : undefined}>
      {!inv ? <p role="alert" className="font-body-md text-body-md text-error">Invitationen findes ikke. Bed en administrator om et nyt link.</p> : (
        <div className="space-y-space-md">
          <dl className="rounded-lg bg-surface-container-low p-space-md grid grid-cols-[auto,1fr] gap-x-space-md gap-y-2 font-body-md text-body-md">
            <dt className="text-on-surface-variant">Arbejdsrum</dt><dd className="font-semibold text-primary">{inv.workspace_name}</dd>
            <dt className="text-on-surface-variant">Rolle</dt><dd className="font-semibold text-primary">{ROLE[inv.role] ?? inv.role}</dd>
            <dt className="text-on-surface-variant">E-mail</dt><dd className="break-all">{inv.email}</dd>
            <dt className="text-on-surface-variant">Status</dt><dd><span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm font-bold ${statusCls}`}>{statusLabel}</span></dd>
          </dl>
          {inv.status !== "pending" ? <p className="font-body-sm text-body-sm text-on-surface-variant">Invitationen kan ikke længere bruges. Bed en administrator om en ny.</p>
            : loggedIn ? <AcceptButton token={token} />
            : (
              <div className="space-y-space-sm">
                <p className="font-body-sm text-body-sm text-on-surface-variant">Log ind eller opret en konto med adressen <strong className="text-on-surface">{inv.email}</strong> for at acceptere.</p>
                <Link className="w-full h-12 rounded-lg bg-primary text-on-primary font-label-lg text-label-lg flex items-center justify-center gap-space-xs hover:bg-primary-container" href={`/login?next=/invite/${token}`}><Icon name="login" size={18} />Log ind og acceptér</Link>
                <Link className="w-full h-12 rounded-lg bg-surface-container text-primary font-label-lg text-label-lg flex items-center justify-center gap-space-xs hover:bg-surface-container-high" href={`/signup?next=/invite/${token}`}><Icon name="person_add" size={18} />Opret konto</Link>
              </div>
            )}
        </div>
      )}
    </AuthFrame>
  );
}
