"use client";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { api } from "@/lib/client";
import { useT } from "@/i18n/client";
import { Button, ErrorBox, Field, Input, Select, Textarea, useSubmit } from "@/components/ui";
import type { Ticket } from "./shared";

const MAX_BYTES = 4 * 1024 * 1024;
const ACCEPT = "image/png,image/jpeg,application/pdf,text/plain,.log,.txt,.csv";

/** File picker with the same limits the API enforces (count, 4 MB), checked before anything is sent. */
function Files({ id, max, onChange, error }: { id: string; max: number; onChange: (f: File[]) => void; error: string | null }) {
  const t = useT("app");
  return (
    <Field label={t("support.new.files")} hint={t("support.new.filesHint", { n: max })} error={error ?? undefined}>
      <input id={id} type="file" multiple accept={ACCEPT} onChange={(e) => onChange([...(e.target.files ?? [])])}
        className="block w-full text-[14px] file:mr-3 file:min-h-[44px] file:px-4 file:rounded-xl file:border-2 file:border-ink file:bg-paper file:font-semibold file:text-ink" />
    </Field>
  );
}

function checkFiles(t: ReturnType<typeof useT>, files: File[], max: number): string | null {
  if (files.length > max) return t("support.new.tooMany", { n: max });
  const big = files.find((f) => f.size > MAX_BYTES);
  return big ? t("support.new.tooBig", { name: big.name }) : null;
}

/** «Opret ny sag»: subject, category, description and up to `max` files; opens the new ticket afterwards. */
export function NewTicketForm({ wsId, categories, max, context }: { wsId: string; categories: string[]; max: number; context?: string }) {
  const t = useT("app");
  const router = useRouter();
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState("other");
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const submit = useSubmit(async () => {
    const fd = new FormData();
    fd.set("subject", subject);
    fd.set("category", category);
    fd.set("body", body);
    if (context) fd.set("context", context);
    files.forEach((f) => fd.append("files", f, f.name));
    const created = await api<Ticket>(`/workspaces/${wsId}/support/tickets`, { method: "POST", body: fd });
    router.push(`/app/support/${created.number}`);
  });
  return (
    <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); const err = checkFiles(t, files, max); setFileError(err); if (!err) submit.run(); }}>
      <Field label={t("support.new.subject")}><Input name="subject" required minLength={3} maxLength={160} value={subject} onChange={(e) => setSubject(e.target.value)} /></Field>
      <Field label={t("support.new.category")}>
        <Select name="category" value={category} onChange={(e) => setCategory(e.target.value)}>
          {categories.map((c) => <option key={c} value={c}>{t(`support.category.${c}`)}</option>)}
        </Select>
      </Field>
      <Field label={t("support.new.body")} hint={t("support.new.bodyHint")}><Textarea name="body" required maxLength={5000} rows={5} value={body} onChange={(e) => setBody(e.target.value)} /></Field>
      <Files id="support-new-files" max={max} onChange={setFiles} error={fileError} />
      <p className="text-body-sm text-muted">{t("support.new.note")}</p>
      <ErrorBox error={submit.error} />
      <Button type="submit" icon="add_circle" disabled={submit.pending} className="min-h-[52px]">{t("support.new.submit")}</Button>
    </form>
  );
}

/** The customer's side of the thread: write a reply (with files), mark resolved, reopen. */
export function TicketActions({ wsId, number, status, max }: { wsId: string; number: number; status: string; max: number }) {
  const t = useT("app");
  const router = useRouter();
  const form = useRef<HTMLFormElement>(null);
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const base = `/workspaces/${wsId}/support/tickets/${number}`;
  const send = useSubmit(async () => {
    const fd = new FormData();
    fd.set("body", body);
    files.forEach((f) => fd.append("files", f, f.name));
    await api(`${base}/messages`, { method: "POST", body: fd });
    setBody(""); setFiles([]); form.current?.reset();
    router.refresh();
  });
  const act = useSubmit(async (what: "resolve" | "reopen") => { await api(`${base}/${what}`, { method: "POST" }); router.refresh(); });
  return (
    <div className="flex flex-col gap-3">
      <form ref={form} className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); const err = checkFiles(t, files, max); setFileError(err); if (!err) send.run(); }}>
        <Field label={t("support.ticket.reply")} hint={t("support.ticket.replyHint")}><Textarea name="body" required maxLength={5000} rows={4} value={body} onChange={(e) => setBody(e.target.value)} /></Field>
        <Files id="support-reply-files" max={max} onChange={setFiles} error={fileError} />
        <ErrorBox error={send.error} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" icon="send" disabled={send.pending || !body.trim()}>{t("support.ticket.send")}</Button>
          {status === "resolved"
            ? <Button type="button" variant="outline" icon="restart_alt" disabled={act.pending} onClick={() => act.run("reopen")}>{t("support.ticket.reopen")}</Button>
            : <Button type="button" variant="outline" icon="task_alt" disabled={act.pending} onClick={() => act.run("resolve")}>{t("support.ticket.resolve")}</Button>}
        </div>
      </form>
      <ErrorBox error={act.error} />
    </div>
  );
}
