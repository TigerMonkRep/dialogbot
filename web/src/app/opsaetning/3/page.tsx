import { backend } from "@/lib/api.server";
import { setupStatus } from "@/lib/setup.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Need } from "@/components/setup-parts";
import { SetupShell } from "@/components/setup-shell";
import type { Telephony } from "@/app/app/(admin)/settings/telephony/client";
import { Step3, type VoicesData, type Webchat } from "./step3";

/** Trin 3 af 3 – Test & tænd. Stemme, telefon, (valgfrit) webchat – og så tænder man. */
export default async function Trin3() {
  const ws = await requireWorkspace();
  const staff = ws.role !== "reader";
  const [st, profile, voices, t, webchat] = await Promise.all([
    setupStatus(ws.id, ws.role),
    backend<{ legal_name: string; phone: string | null; cvr: string | null; address_line: string | null; postal_code: string | null; city: string | null; website_url: string | null }>(`/workspaces/${ws.id}/profile`),
    backend<VoicesData>(`/workspaces/${ws.id}/voices`),
    staff ? backend<Telephony>(`/workspaces/${ws.id}/telephony`).catch(() => null) : Promise.resolve(null),
    staff ? backend<Webchat>(`/workspaces/${ws.id}/webchat`).catch(() => null) : Promise.resolve(null),
  ]);
  const address = [profile.address_line, [profile.postal_code, profile.city].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  return (
    <SetupShell step={3} steps={st.steps} workspaceName={ws.name} wide>
      <div className="flex flex-col gap-3 mb-6">
        <div className="flex items-center gap-4">
          <span className="w-14 h-14 rounded-[14px] bg-highlight text-ink font-display font-extrabold text-[30px] inline-flex items-center justify-center" aria-hidden>3</span>
          <div>
            <span className="eyebrow">Trin 3 af 3 · sidste trin</span>
            <h1 className="font-display font-extrabold text-[30px] md:text-[40px] leading-[1.05] tracking-[-1px] text-ink">Vælg stemme, forbind telefonen – og tænd</h1>
          </div>
        </div>
        <Need items={[["1×", "en telefon at ringe fra"], ["10", "sekunder til viderestilling"]]} />
      </div>
      <Step3 wsId={ws.id} canManage={ws.role === "owner" || ws.role === "admin"} goals={st.goals} voices={voices} t={t} webchat={webchat}
        company={profile.legal_name} cvr={profile.cvr ?? ""} address={address} phone={profile.phone ?? ""} website={profile.website_url ?? ""} />
    </SetupShell>
  );
}
