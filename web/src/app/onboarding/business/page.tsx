import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Breadcrumb, SectionLabel, Steps } from "@/components/ui";
import { BusinessForm, Categories } from "./form";

/** O01/S01 — after Stitch "a06_o01_o02" right module: basic parameters, categories, manual setup path. */
export default async function BusinessPage() {
  const ws = await requireWorkspace();
  const [profile, cats, suggested] = await Promise.all([
    backend<Record<string, unknown>>(`/workspaces/${ws.id}/profile`),
    backend<{ id: string; label: string; slug: string; is_custom: boolean; is_primary: boolean }[]>(`/workspaces/${ws.id}/categories`),
    backend<{ items: { slug: string; label: string }[] }>(`/workspaces/${ws.id}/categories/suggested`),
  ]);
  const canEdit = ws.role !== "reader";
  return (
    <div className="flex flex-col gap-space-lg">
      <div className="space-y-1"><Breadcrumb items={[["Onboarding"], ["O01 Virksomhedsopsætning", "/onboarding/business"]]} /><h1 className="font-display text-headline-lg text-primary tracking-tight">Virksomhedsopsætning · {ws.name}</h1></div>
      <Steps current="/onboarding/business" />
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        <div className="lg:col-span-7 rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
          <div><SectionLabel>O01 · Basale parametre</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">Virksomhedens grunddata</h3><p className="text-body-sm text-on-surface-variant">Manuel opsætning uden hjemmeside er en fuldgyldig vej. Automatisk indlæsning af hjemmeside og dokumenter er ikke implementeret endnu.</p></div>
          <BusinessForm wsId={ws.id} profile={profile} canEdit={canEdit} />
        </div>
        <div className="lg:col-span-5 rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
          <div><SectionLabel>O01 · Branche</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">Branchekategorier</h3><p className="text-body-sm text-on-surface-variant">Flere kategorier er tilladt, og du kan skrive din egen. Den primære bruges som assistentens hovedkontekst.</p></div>
          <Categories wsId={ws.id} categories={cats} suggested={suggested.items} canEdit={canEdit} />
        </div>
      </div>
    </div>
  );
}
