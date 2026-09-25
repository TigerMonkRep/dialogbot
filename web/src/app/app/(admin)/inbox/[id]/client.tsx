"use client";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client";
import { Button, ErrorBox, useSubmit } from "@/components/ui";

export function CreateLeadButton({ wsId, conversationId, need }: { wsId: string; conversationId: string; need: string }) {
  const router = useRouter();
  const create = useSubmit(async () => {
    const l = await api<{ id: string }>(`/workspaces/${wsId}/leads`, { method: "POST", body: JSON.stringify({ conversation_id: conversationId, need_summary: need }) });
    router.push(`/app/leads/${l.id}`);
  });
  return <div className="flex flex-col gap-space-xs"><Button icon="person_add" variant="tonal" disabled={create.pending} onClick={() => create.run()}>Opret henvendelse</Button><ErrorBox error={create.error} /></div>;
}
