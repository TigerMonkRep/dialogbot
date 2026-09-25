import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";

type Detail = { id: string; channel: string; origin: string | null; status: string; created_at: string; messages: { id: string; role: string; text: string; created_at: string }[] };

/** One conversation, read-only. Replies from staff and hand-over arrive with the lead/task model. */
export default async function ConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const ws = await requireWorkspace();
  const { id } = await params;
  const c = await backend<Detail>(`/workspaces/${ws.id}/conversations/${encodeURIComponent(id)}`);
  return (
    <div className="flex flex-col gap-space-lg max-w-3xl">
      <Link href="/app/inbox" className="self-start font-label-md text-label-md text-primary flex items-center gap-1"><Icon name="arrow_back" size={18} />Indbakke</Link>
      <div>
        <h1 className="font-headline-md text-headline-md text-primary">Webchat-samtale</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant">Startet {new Date(c.created_at).toLocaleString("da-DK")}{c.origin ? ` på ${c.origin}` : ""}. Assistenten svarer kun ud fra godkendt viden.</p>
      </div>
      <ol className="flex flex-col gap-space-sm bg-surface-container-low rounded-xl p-space-md" aria-label="Beskeder">
        {c.messages.map((m) => (
          <li key={m.id} className={`flex flex-col gap-0.5 max-w-[85%] ${m.role === "visitor" ? "self-end items-end" : "self-start"}`}>
            <span className="font-label-sm text-label-sm text-on-surface-variant">{m.role === "visitor" ? "Kunde" : "Assistent"} · {new Date(m.created_at).toLocaleTimeString("da-DK", { timeStyle: "short" })}</span>
            <span className={`px-space-md py-space-sm rounded-xl whitespace-pre-wrap font-body-md text-body-md ${m.role === "visitor" ? "bg-primary text-on-primary rounded-tr-none" : "bg-surface-container-lowest text-on-surface rounded-tl-none shadow-sm"}`}>{m.text}</span>
          </li>
        ))}
      </ol>
      <p className="font-body-sm text-body-sm text-on-surface-variant">Svar fra medarbejdere og overdragelse til en opgave kommer sammen med leads og opgaver.</p>
    </div>
  );
}
