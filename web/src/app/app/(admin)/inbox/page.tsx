import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";

type Conv = { id: string; channel: string; origin: string | null; status: string; visitor_message_count: number; created_at: string; last_message_at: string; preview: string | null };
const PER_PAGE = 25;
const CHANNEL: Record<string, [string, string]> = { webchat: ["Webchat", "chat"], phone: ["Telefon", "call"] };

/** Inbox: customer conversations (webchat today; phone and callback when those channels exist). */
export default async function InboxPage({ searchParams }: { searchParams: Promise<{ page?: string }> }) {
  const ws = await requireWorkspace();
  if (ws.role === "reader") {
    return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Indbakken kan ses af medarbejdere, administratorer og ejere.</p>;
  }
  const pageNo = Math.max(1, Number((await searchParams).page ?? 1) || 1);
  const list = await backend<{ items: Conv[]; total: number }>(`/workspaces/${ws.id}/conversations?limit=${PER_PAGE}&offset=${(pageNo - 1) * PER_PAGE}`);
  const pages = Math.max(1, Math.ceil(list.total / PER_PAGE));
  return (
    <div className="flex flex-col gap-space-lg">
      <div className="flex flex-col gap-space-xs">
        <div className="hidden md:flex items-center gap-space-xs font-label-md text-label-md text-on-surface-variant"><span>Henvendelser</span><Icon name="chevron_right" size={14} /><span className="text-primary font-semibold">Indbakke</span></div>
        <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight">Indbakke</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant">Samtaler fra webchat og telefon, nyeste først.</p>
      </div>
      <section className="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
        {list.items.length === 0 ? (
          <div className="p-space-lg flex flex-col items-start gap-space-sm">
            <p className="font-body-md text-body-md text-on-surface-variant">Ingen samtaler endnu.</p>
            <Link href="/app/settings/webchat" className="font-label-lg text-label-lg text-primary flex items-center gap-1"><Icon name="chat" size={18} />Sæt webchat op</Link>
          </div>
        ) : (
          <ul aria-label="Samtaler">
            {list.items.map((c) => {
              const [label, icon] = CHANNEL[c.channel] ?? [c.channel, "forum"];
              return (
                <li key={c.id} className="border-b border-surface-container last:border-0">
                  <Link href={`/app/inbox/${c.id}`} className="flex items-start gap-space-md p-space-md hover:bg-surface-container-low transition-colors">
                    <span className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-primary shrink-0"><Icon name={icon} size={20} /></span>
                    <span className="flex-1 min-w-0">
                      <span className="flex flex-wrap items-center gap-space-xs font-label-md text-label-md text-on-surface-variant"><span className="font-semibold text-primary">{label}</span>{c.origin && <span>· {c.origin.replace(/^https?:\/\//, "")}</span>}<span>· {c.visitor_message_count} {c.visitor_message_count === 1 ? "besked" : "beskeder"}</span></span>
                      <span className="block font-body-md text-body-md text-on-surface truncate">{c.preview ?? "(ingen besked endnu)"}</span>
                    </span>
                    <time dateTime={c.last_message_at} className="font-label-sm text-label-sm text-on-surface-variant whitespace-nowrap">{new Date(c.last_message_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" })}</time>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      {pages > 1 && (
        <nav className="flex items-center justify-between font-label-md text-label-md" aria-label="Sider">
          {pageNo > 1 ? <Link href={`/app/inbox?page=${pageNo - 1}`} className="text-primary">← Nyere</Link> : <span />}
          <span className="text-on-surface-variant">Side {pageNo} af {pages}</span>
          {pageNo < pages ? <Link href={`/app/inbox?page=${pageNo + 1}`} className="text-primary">Ældre →</Link> : <span />}
        </nav>
      )}
    </div>
  );
}
