import Link from "next/link";
import { Card, Icon } from "@/components/ui";

/** Honest placeholder for areas planned in later milestones. Never a fake screen. */
export default async function NotYet({ searchParams }: { searchParams: Promise<{ area?: string }> }) {
  const { area } = await searchParams;
  const plan: Record<string, string> = { Henvendelser: "Milepæl B (reception og daglig drift)", Kampagner: "Milepæl D (kampagner og økonomi)", Bookinger: "Milepæl C (booking)", Notifikationer: "Milepæl B", Hjælp: "Milepæl A (G04 hjælpepanel)" };
  return (
    <div className="mx-auto max-w-2xl">
      <Card label="Ikke implementeret endnu" title={area ?? "Dette område"}>
        <p className="text-body-md text-on-surface-variant flex items-start gap-space-sm"><Icon name="construction" size={20} className="text-secondary shrink-0" />Området er ikke bygget i den nuværende milepæl og vises derfor ikke som en fungerende skærm. Planlagt: <strong className="ml-1">{plan[area ?? ""] ?? "senere milepæl"}</strong>.</p>
        <Link href="/app/setup" className="inline-flex items-center gap-space-xs text-label-lg text-primary underline">Tilbage til opsætningsguiden</Link>
      </Card>
    </div>
  );
}
