"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { Button, ErrorBox, inputCls, useSubmit } from "@/components/ui";

export function CreateLeadButton({ wsId, conversationId, need }: { wsId: string; conversationId: string; need: string }) {
  const router = useRouter();
  const create = useSubmit(async () => {
    const l = await api<{ id: string }>(`/workspaces/${wsId}/leads`, { method: "POST", body: JSON.stringify({ conversation_id: conversationId, need_summary: need }) });
    router.push(`/app/leads/${l.id}`);
  });
  return <div className="flex flex-col gap-space-xs"><Button icon="person_add" variant="tonal" disabled={create.pending} onClick={() => create.run()}>Opret henvendelse</Button><ErrorBox error={create.error} /></div>;
}

/** Keeps an open conversation fresh while a colleague is answering (server component re-render). */
export function AutoRefresh({ seconds = 5 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => { const t = setInterval(() => router.refresh(), seconds * 1000); return () => clearInterval(t); }, [router, seconds]);
  return null;
}

export function ReplyBox({ wsId, conversationId, mode }: { wsId: string; conversationId: string; mode: string }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const send = useSubmit(async () => {
    await api(`/workspaces/${wsId}/conversations/${conversationId}/reply`, { method: "POST", body: JSON.stringify({ text }) });
    setText(""); router.refresh();
  });
  const handBack = useSubmit(async () => {
    await api(`/workspaces/${wsId}/conversations/${conversationId}/mode`, { method: "POST", body: JSON.stringify({ mode: "ai" }) });
    router.refresh();
  });
  return (
    <form className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send.run(); }}>
      <label htmlFor="reply" className="font-label-md text-label-md font-semibold">Svar kunden i chatten</label>
      <textarea id="reply" rows={3} maxLength={2000} className={inputCls} value={text} onChange={(e) => setText(e.target.value)}
        placeholder={mode === "staff" ? "Skriv dit svar…" : "Når du svarer, overtager du samtalen, og assistenten holder pause."} />
      <ErrorBox error={send.error ?? handBack.error} />
      <div className="flex flex-wrap gap-space-sm">
        <Button type="submit" icon="send" disabled={send.pending || !text.trim()}>Send svar</Button>
        {mode === "staff" && <Button type="button" variant="outline" icon="smart_toy" disabled={handBack.pending} onClick={() => handBack.run()}>Giv tilbage til assistenten</Button>}
      </div>
    </form>
  );
}
