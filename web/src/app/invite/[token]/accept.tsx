"use client";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client";
import { useT } from "@/i18n/client";
import { Button, ErrorBox, useSubmit } from "@/components/ui";

export function AcceptButton({ token }: { token: string }) {
  const router = useRouter();
  const t = useT("auth");
  const { run, pending, error } = useSubmit(async () => {
    const ws = await api<{ id: string }>("/invitations/accept", { method: "POST", body: JSON.stringify({ token }) });
    await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: ws.id }) });
    // A colleague joins an existing company: its app (I dag), never the owner's set-up guide (F-JE-10, A05).
    router.push("/app"); router.refresh();
  });
  return <div className="space-y-3"><ErrorBox error={error} /><Button icon="check_circle" disabled={pending} onClick={run} className="w-full h-12 rounded-lg">{pending ? t("invite.accepting") : t("invite.accept")}</Button></div>;
}
