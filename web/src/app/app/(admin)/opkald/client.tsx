"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { ErrorBox, inputCls, useSubmit } from "@/components/ui";
import { useT } from "@/i18n/client";

const BTN = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper text-[15px] font-semibold text-ink hover:bg-panel disabled:opacity-50";

/** «Marker som klaret»: closes the open tasks of the conversation and hands a taken-over chat back to the assistant. */
export function ResolveButton({ wsId, conversationId, disabled }: { wsId: string; conversationId: string; disabled?: boolean }) {
  const router = useRouter();
  const t = useT("app");
  const done = useSubmit(async () => {
    await api(`/workspaces/${wsId}/conversations/${conversationId}/resolve`, { method: "POST" });
    router.refresh();
  });
  return <><button type="button" className={BTN} disabled={disabled || done.pending} onClick={() => done.run()}>{t("calls.resolve")}</button><ErrorBox error={done.error} /></>;
}

export function CreateLeadButton({ wsId, conversationId, need }: { wsId: string; conversationId: string; need: string }) {
  const router = useRouter();
  const t = useT("app");
  const create = useSubmit(async () => {
    const l = await api<{ id: string }>(`/workspaces/${wsId}/leads`, { method: "POST", body: JSON.stringify({ conversation_id: conversationId, need_summary: need }) });
    router.push(`/app/opkald/henvendelser/${l.id}`);
  });
  return <><button type="button" className={BTN} disabled={create.pending} onClick={() => create.run()}>{t("calls.saveAsLead")}</button><ErrorBox error={create.error} /></>;
}

/** Keeps an open webchat fresh while a colleague is answering (server component re-render). */
export function AutoRefresh({ seconds = 5 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => { const t = setInterval(() => router.refresh(), seconds * 1000); return () => clearInterval(t); }, [router, seconds]);
  return null;
}

export function ReplyBox({ wsId, conversationId, mode }: { wsId: string; conversationId: string; mode: string }) {
  const router = useRouter();
  const t = useT("app");
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
    <form className="flex flex-col gap-3 p-4 rounded-2xl border-2 border-ink" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send.run(); }}>
      <label htmlFor={`reply-${conversationId}`} className="text-[14px] font-semibold text-ink">{t("calls.reply.label")}</label>
      <textarea id={`reply-${conversationId}`} rows={3} maxLength={2000} className={inputCls} value={text} onChange={(e) => setText(e.target.value)}
        placeholder={mode === "staff" ? t("calls.reply.placeholderStaff") : t("calls.reply.placeholderAi")} />
      <ErrorBox error={send.error ?? handBack.error} />
      <div className="flex flex-wrap gap-3">
        <button type="submit" disabled={send.pending || !text.trim()} className="inline-flex items-center min-h-[44px] px-4 rounded-xl bg-accent text-white text-[15px] font-semibold hover:bg-accent-deep disabled:opacity-50">{t("calls.reply.send")}</button>
        {mode === "staff" && <button type="button" className={BTN} disabled={handBack.pending} onClick={() => handBack.run()}>{t("calls.reply.handBack")}</button>}
      </div>
    </form>
  );
}
