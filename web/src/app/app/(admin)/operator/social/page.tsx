import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { SocialDashboard, type Dashboard } from "./client";

/** Operator: followers and engagement per platform, the posts waiting for approval, what is scheduled and what went out. */
export default async function OperatorSocialPage({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
  await requireWorkspace();
  const { days: raw } = await searchParams;
  const days = [7, 30, 90].includes(Number(raw)) ? Number(raw) : 30;
  let data: Dashboard;
  try {
    data = await backend<Dashboard>(`/operator/social/dashboard?days=${days}`);
  } catch {
    return <p className="bg-surface-container-lowest rounded-2xl p-space-lg border-2 border-ink font-body-md text-body-md text-on-surface-variant">Sociale medier er kun for Dialogbot-operatører.</p>;
  }
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="eyebrow">Operatør</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Sociale medier</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">Dialogbots egne profiler på Facebook, Instagram og TikTok: følgere og engagement, de opslag der venter på din godkendelse, og det der er gået ud. Tallene hentes én gang i timen; alle handlinger logges.</p>
      </div>
      <SocialDashboard data={data} />
    </section>
  );
}
