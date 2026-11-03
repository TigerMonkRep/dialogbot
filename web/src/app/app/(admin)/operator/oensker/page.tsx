import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { AdminFrame, NotOperator } from "../admin/shared";
import { Wishes, type WishList } from "./client";

const STATUSES = ["new", "planned", "done", "declined"];

/** Operator: what customers asked the assistant for that Dialogbot cannot do yet – across every workspace. Set a status
 *  and a note; repeats from the same workspace are counted on one row. */
export default async function OperatorWishesPage({ searchParams }: { searchParams: Promise<{ status?: string; category?: string; q?: string }> }) {
  await requireWorkspace();
  const sp = await searchParams;
  const status = sp.status && STATUSES.includes(sp.status) ? sp.status : sp.status === "all" ? "" : "new";
  const qs = new URLSearchParams();
  if (status) qs.set("status", status);
  if (sp.category && /^[a-z]{2,20}$/.test(sp.category)) qs.set("category", sp.category);
  if (sp.q?.trim()) qs.set("q", sp.q.trim().slice(0, 100));
  qs.set("limit", "300");
  let data: WishList;
  try {
    data = await backend<WishList>(`/operator/assistant/requests?${qs}`);
  } catch {
    return <NotOperator />;
  }
  return (
    <AdminFrame active="/app/operator/oensker" title="Ønsker fra kunderne" eyebrow="Admin · ønsker"
      intro="Det, kunderne har bedt assistenten om, som Dialogbot ikke kan endnu – med kundens egne ord. Gentagelser fra samme kunde tælles på samme ønske. Sæt en status og en note; alt logges.">
      <Wishes data={data} status={status || "all"} category={qs.get("category") ?? ""} q={qs.get("q") ?? ""} />
    </AdminFrame>
  );
}
