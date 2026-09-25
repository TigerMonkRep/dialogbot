"use client";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client";
import { Button, ErrorBox, useSubmit } from "@/components/ui";

export function AcceptButton({ token }: { token: string }) {
  const router = useRouter();
  const { run, pending, error } = useSubmit(async () => {
    const ws = await api<{ id: string }>("/invitations/accept", { method: "POST", body: JSON.stringify({ token }) });
    await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: ws.id }) });
    router.push("/app/setup"); router.refresh();
  });
  return <div className="space-y-3"><ErrorBox error={error} /><Button icon="check_circle" disabled={pending} onClick={run} className="w-full h-12 rounded-lg">{pending ? "Accepterer…" : "Acceptér invitation"}</Button></div>;
}
