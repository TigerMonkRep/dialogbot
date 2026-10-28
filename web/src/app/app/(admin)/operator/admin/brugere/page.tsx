import Link from "next/link";
import { AdminFrame, NotOperator, dt, load } from "../shared";
import { ViewAsButton } from "../view-as-button";

type U = { id: string; email: string; name: string; active: boolean; verified: boolean; is_operator: boolean; created_at: string; last_seen_at: string | null;
  workspaces: { id: string; name: string; role: string }[]; ambassador: { id: string; status: string; kind: string } | null };

export default async function Users({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = "" } = await searchParams;
  const data = await load<{ items: U[] }>(`/operator/admin/users?q=${encodeURIComponent(q)}`);
  if (!data) return <NotOperator />;
  return (
    <AdminFrame active="/app/operator/admin/brugere" title="Brugere" intro="Alle personer: kunder, kollegaer og ambassadører. &quot;Se som&quot; åbner deres visning (kun læsning, 1 time, logges).">
      <form className="flex gap-2 max-w-xl" role="search">
        <input name="q" defaultValue={q} placeholder="Søg navn eller e-mail" aria-label="Søg" className="flex-1 min-h-[46px] px-3.5 rounded-xl bg-paper border-2 border-ink" />
        <button className="px-5 rounded-xl bg-ink text-paper font-semibold">Søg</button>
      </form>
      <ul className="rounded-2xl bg-paper border-2 border-ink divide-y divide-line">
        {data.items.map((u) => (
          <li key={u.id} className="p-space-md flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="font-semibold">{u.name} <span className="font-normal text-muted">{u.email}</span>{u.is_operator && <span className="ml-2 text-[12px] px-2 py-0.5 rounded-full bg-accent-soft font-semibold">operatør</span>}{!u.active && <span className="ml-2 text-danger">deaktiveret</span>}</p>
              <p className="text-[13px] text-muted">
                {u.workspaces.map((w, i) => <span key={w.id}>{i > 0 && ", "}<Link className="underline" href={`/app/operator/admin/kunder/${w.id}`}>{w.name}</Link> ({w.role})</span>)}
                {u.workspaces.length === 0 && "Ingen kunde"}{u.ambassador && ` · ambassadør (${u.ambassador.status}, ${u.ambassador.kind})`} · sidst set {dt(u.last_seen_at)}
              </p>
            </div>
            {u.active && !u.is_operator && <ViewAsButton userId={u.id} workspaceId={u.workspaces[0]?.id} label={u.ambassador && u.workspaces.length === 0 ? "Se ambassadørsiden som" : "Se som"} />}
          </li>
        ))}
        {data.items.length === 0 && <li className="p-space-md text-muted">Ingen brugere matcher.</li>}
      </ul>
    </AdminFrame>
  );
}
