import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { AutoRefresh, CreateLeadButton, ReplyBox } from "./client";

type Msg = { id: string; role: string; text: string; created_at: string };
type Run = { id: string; label: string; status: "ok" | "failed" | "refused"; error: string | null; simulated: boolean; created_at: string };
type Detail = { id: string; channel: string; origin: string | null; status: string; mode: string; created_at: string; messages: Msg[]; actions?: Run[] };
const RUN: Record<Run["status"], [string, string]> = {
  ok: ["Udført", "bg-secondary-container text-on-secondary-container"],
  failed: ["Fejlede", "bg-error-container text-on-error-container"],
  refused: ["Ikke udført", "bg-tertiary-fixed text-on-tertiary-fixed"],
};

/** One conversation, read-only. Replies from staff and hand-over arrive with the lead/task model. */
export default async function ConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const ws = await requireWorkspace();
  const { id } = await params;
  const [c, owned] = await Promise.all([
    backend<Detail>(`/workspaces/${ws.id}/conversations/${encodeURIComponent(id)}`),
    backend<{ lead: { id: string; contact_name: string } | null }>(`/workspaces/${ws.id}/conversations/${encodeURIComponent(id)}/lead`),
  ]);
  const firstVisitor = c.messages.find((m) => m.role === "visitor")?.text ?? "";
  return (
    <div className="flex flex-col gap-space-lg max-w-3xl">
      <Link href="/app/inbox" className="self-start font-label-md text-label-md text-primary flex items-center gap-1"><Icon name="arrow_back" size={18} />Indbakke</Link>
      <div className="flex flex-wrap items-start justify-between gap-space-md">
      <div>
        <h1 className="font-headline-md text-headline-md text-primary">{c.channel === "phone" ? "Telefonopkald" : "Webchat-samtale"}</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant">Startet {new Date(c.created_at).toLocaleString("da-DK")}{c.origin ? (c.channel === "phone" ? ` fra ${c.origin}` : ` på ${c.origin}`) : ""}. Assistenten svarer kun ud fra godkendt viden.</p>
      </div>
      {owned.lead
        ? <Link href={`/app/leads/${owned.lead.id}`} className="font-label-lg text-label-lg text-primary flex items-center gap-1"><Icon name="contact_support" size={18} />Henvendelse: {owned.lead.contact_name || "uden navn"}</Link>
        : <CreateLeadButton wsId={ws.id} conversationId={c.id} need={firstVisitor} />}
      </div>
      <ol className="flex flex-col gap-space-sm bg-surface-container-low rounded-xl p-space-md" aria-label="Beskeder">
        {[...c.messages.map((m) => ({ kind: "msg" as const, at: m.created_at, m })), ...(c.actions ?? []).map((r) => ({ kind: "run" as const, at: r.created_at, r }))]
          .sort((a, b) => a.at.localeCompare(b.at)).map((x) => x.kind === "run" ? (
          <li key={x.r.id} className={`self-center w-full max-w-[85%] flex items-start gap-space-sm rounded-lg px-space-md py-space-sm font-body-sm text-body-sm ${RUN[x.r.status][1]}`} data-action-run>
            <Icon name="bolt" size={18} className="shrink-0 mt-0.5" />
            <span><strong>{RUN[x.r.status][0]}:</strong> {x.r.label}{x.r.simulated ? " (simuleret)" : ""} · {new Date(x.r.created_at).toLocaleTimeString("da-DK", { timeStyle: "short" })}{x.r.error ? <><br />{x.r.error}</> : null}</span>
          </li>
        ) : (() => { const m = x.m; return (
          <li key={m.id} className={`flex flex-col gap-0.5 max-w-[85%] ${m.role === "visitor" ? "self-end items-end" : "self-start"}`}>
            <span className="font-label-sm text-label-sm text-on-surface-variant">{m.role === "visitor" ? "Kunde" : m.role === "staff" ? "Medarbejder" : "Assistent"} · {new Date(m.created_at).toLocaleTimeString("da-DK", { timeStyle: "short" })}</span>
            <span className={`px-space-md py-space-sm rounded-xl whitespace-pre-wrap font-body-md text-body-md ${m.role === "visitor" ? "bg-primary text-on-primary rounded-tr-none" : m.role === "staff" ? "bg-secondary-fixed text-on-secondary-fixed rounded-tl-none" : "bg-surface-container-lowest text-on-surface rounded-tl-none shadow-sm"}`}>{m.text}</span>
          </li>
        ); })())}
      </ol>
      {c.channel === "webchat" ? (
        <>
          {c.mode === "staff" && <p className="p-space-sm rounded-lg bg-tertiary-fixed text-on-tertiary-fixed font-body-sm text-body-sm">En medarbejder har overtaget samtalen – assistenten svarer ikke, før den gives tilbage.</p>}
          <ReplyBox wsId={ws.id} conversationId={c.id} mode={c.mode} />
          <AutoRefresh />
        </>
      ) : <p className="font-body-sm text-body-sm text-on-surface-variant">Telefonopkald kan ikke besvares her – følg op via henvendelsen og dens opgaver.</p>}
    </div>
  );
}
