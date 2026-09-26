import Link from "next/link";
import { Card, Icon } from "@/components/ui";

/** Honest placeholder for areas that are not built yet. Never a fake screen. */
export default async function NotYet({ searchParams }: { searchParams: Promise<{ area?: string }> }) {
  const { area } = await searchParams;
  const plan: Record<string, string> = { Kampagner: "sammen med kampagner og betaling", Bookinger: "sammen med kalenderforbindelsen", Notifikationer: "sammen med e-mail og notifikationer", Hjælp: "sammen med hjælpepanelet", Kundesupport: "sammen med hjælpepanelet" };
  return (
    <div className="mx-auto max-w-2xl">
      <Card label="Ikke implementeret endnu" title={area ?? "Dette område"}>
        <p className="text-body-md text-on-surface-variant flex items-start gap-space-sm"><Icon name="construction" size={20} className="text-secondary shrink-0" />Området er ikke bygget endnu og vises derfor ikke som en fungerende skærm. Det kommer <strong>{plan[area ?? ""] ?? "senere"}</strong>.</p>
        <Link href="/app/setup" className="inline-flex items-center gap-space-xs text-label-lg text-primary underline">Tilbage til opsætningsguiden</Link>
      </Card>
    </div>
  );
}
