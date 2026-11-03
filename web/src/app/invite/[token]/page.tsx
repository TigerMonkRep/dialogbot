import Link from "@/i18n/link";
import { getT } from "@/i18n/server";
import { API_BASE_URL } from "@/lib/config";
import { isLoggedIn } from "@/lib/api.server";
import { Icon } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { AcceptButton } from "./accept";

const ROLES = new Set(["owner", "admin", "staff", "reader"]);
const STATUS: Record<string, string> = {
  pending: "bg-success-soft text-success", accepted: "bg-line text-ink",
  revoked: "bg-panel-deep text-ink-soft", expired: "bg-danger-soft text-danger",
};

/** A05: public preview of an invitation; acceptance requires login with the invited address. */
export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const t = await getT("auth");
  const r = await fetch(`${API_BASE_URL}/api/v1/invitations/${encodeURIComponent(token)}`, { cache: "no-store" });
  const loggedIn = await isLoggedIn();
  const inv = r.ok ? await r.json() : null;
  const known = inv ? STATUS[inv.status] : undefined;
  const [statusLabel, statusCls] = known ? [t(`invite.statuses.${inv.status}`), known] : [inv?.status, "bg-line text-ink"];
  return (
    <AuthFrame icon="group_add" title={inv ? t("invite.title", { workspace: inv.workspace_name }) : t("invite.titleFallback")} subtitle={inv ? t("invite.subtitle") : undefined}>
      {!inv ? <p role="alert" className="text-body-md text-danger">{t("invite.notFound")}</p> : (
        <div className="space-y-3">
          <dl className="rounded-lg bg-panel p-3 grid grid-cols-[auto,1fr] gap-x-3 gap-y-2 text-body-md">
            <dt className="text-ink-soft">{t("invite.workspace")}</dt><dd className="font-semibold text-ink">{inv.workspace_name}</dd>
            <dt className="text-ink-soft">{t("invite.role")}</dt><dd className="font-semibold text-ink">{ROLES.has(inv.role) ? t(`invite.roles.${inv.role}`) : inv.role}</dd>
            <dt className="text-ink-soft">{t("invite.email")}</dt><dd className="break-all">{inv.email}</dd>
            <dt className="text-ink-soft">{t("invite.status")}</dt><dd><span className={`px-2 py-0.5 rounded-full text-label-sm font-bold ${statusCls}`}>{statusLabel}</span></dd>
          </dl>
          {inv.status !== "pending" ? <p className="text-body-sm text-ink-soft">{t("invite.unusable")}</p>
            : loggedIn ? <AcceptButton token={token} />
            : (
              <div className="space-y-2">
                <p className="text-body-sm text-ink-soft">{t("invite.loginBefore")} <strong className="text-ink">{inv.email}</strong> {t("invite.loginAfter")}</p>
                <Link className="w-full h-12 rounded-lg bg-ink text-paper text-label-lg flex items-center justify-center gap-1 hover:bg-ink" href={`/login?next=/invite/${token}`}><Icon name="login" size={18} />{t("invite.loginAccept")}</Link>
                <Link className="w-full h-12 rounded-lg bg-panel-deep text-ink text-label-lg flex items-center justify-center gap-1 hover:bg-line" href={`/signup?next=/invite/${token}`}><Icon name="person_add" size={18} />{t("invite.signup")}</Link>
              </div>
            )}
        </div>
      )}
    </AuthFrame>
  );
}
