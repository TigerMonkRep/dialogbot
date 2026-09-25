import Link from "next/link";
import { API_BASE_URL } from "@/lib/config";
import { isLoggedIn } from "@/lib/api.server";
import { Badge, Card } from "@/components/ui";
import { AcceptButton } from "./accept";

/** A05: public preview of an invitation; acceptance requires login with the invited address. */
export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const r = await fetch(`${API_BASE_URL}/api/v1/invitations/${encodeURIComponent(token)}`, { cache: "no-store" });
  const loggedIn = await isLoggedIn();
  const inv = r.ok ? await r.json() : null;
  return (
    <main className="mx-auto max-w-md px-4 py-12">
      <h1 className="mb-6 font-display text-headline-lg text-primary">Invitation</h1>
      <Card>
        {!inv ? <p className="text-body-sm text-error">Invitationen findes ikke.</p> : (
          <div className="space-y-4 text-body-sm">
            <p>Du er inviteret til <strong>{inv.workspace_name}</strong> som <strong>{inv.role}</strong> ({inv.email}).</p>
            <p>Status: <Badge status={inv.status} /></p>
            {inv.status !== "pending" ? <p className="text-on-surface-variant">Invitationen kan ikke længere bruges. Bed en administrator om en ny.</p>
              : loggedIn ? <AcceptButton token={token} />
              : <p>Log ind eller opret en konto med adressen <strong>{inv.email}</strong>, og vend tilbage til dette link.
                  <span className="mt-3 flex gap-4"><Link className="font-semibold text-primary underline" href={`/login?next=/invite/${token}`}>Log ind</Link><Link className="font-semibold text-primary underline" href={`/signup?next=/invite/${token}`}>Opret konto</Link></span></p>}
          </div>
        )}
      </Card>
    </main>
  );
}
