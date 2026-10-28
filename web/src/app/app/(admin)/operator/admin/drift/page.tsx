import { Advanced, AdminFrame, NotOperator, dt, load } from "../shared";

type Ops = {
  schema: { ok: boolean; database: string | null; code: string }; outbox_7d: Record<string, number>;
  failed_jobs: { id: string; type: string; status: string; attempts: number; error: string; at: string }[];
  emails: { at: string; to: string; subject: string; status: string; provider_status: string | null; adapter: string }[];
  audit: { at: string; action: string; workspace_id: string | null; actor: string | null; object: string }[];
  links: Record<string, string>;
};
const box = "rounded-2xl bg-paper border-2 border-ink p-space-md";

export default async function Drift() {
  const o = await load<Ops>("/operator/admin/operations");
  if (!o) return <NotOperator />;
  return (
    <AdminFrame active="/app/operator/admin/drift" title="Drift" intro="Er systemet sundt? Databaseversion, opgavekø, fejlede opgaver, sendte e-mails og den seneste logbog på tværs af kunder.">
      <div className="grid md:grid-cols-2 gap-space-md">
        <section className={box}><h2 className="font-display font-bold text-[18px] mb-1">Database og kode</h2>
          <p className={o.schema.ok ? "text-success font-semibold" : "text-danger font-semibold"}>{o.schema.ok ? "Samme version" : "FORSKELLIG version – workeren holder pause"}</p>
          <p className="text-[13px] text-muted">Database {o.schema.database ?? "?"} · kode {o.schema.code}</p></section>
        <section className={box}><h2 className="font-display font-bold text-[18px] mb-1">Opgavekø (7 dage)</h2>
          <p className="text-[14px]">{Object.entries(o.outbox_7d).map(([k, v]) => `${k}: ${v}`).join(" · ") || "tom"}</p>
          <p className="text-[13px] text-muted mt-1">Tjenester: {Object.entries(o.links).map(([k, v]) => <a key={k} className="underline mr-2" href={v} target="_blank" rel="noreferrer">{k}</a>)}</p></section>
      </div>
      <section className={box}><h2 className="font-display font-bold text-[18px] mb-2">Fejlede opgaver</h2>
        <ul className="text-[14px] divide-y divide-line">{o.failed_jobs.map((j) => <li key={j.id} className="py-2"><span className="font-semibold">{j.type}</span> · {j.status} · {j.attempts} forsøg · {dt(j.at)}<span className="block text-[13px] text-danger break-words">{j.error}</span></li>)}{o.failed_jobs.length === 0 && <li className="py-1 text-muted">Ingen.</li>}</ul>
      </section>
      <section className={box}><h2 className="font-display font-bold text-[18px] mb-2">Seneste e-mails</h2>
        <ul className="text-[14px] divide-y divide-line">{o.emails.map((m, i) => <li key={i} className="py-1 flex flex-wrap justify-between gap-2"><span>{dt(m.at)} · {m.to} · {m.subject}</span><span className="text-muted">{m.status}{m.provider_status ? ` / ${m.provider_status}` : ""} ({m.adapter})</span></li>)}</ul>
      </section>
      <section className={box}><h2 className="font-display font-bold text-[18px] mb-2">Logbog (seneste 40)</h2>
        <ul className="text-[13px] divide-y divide-line">{o.audit.map((a, i) => <li key={i} className="py-1">{dt(a.at)} · {a.action} · <span className="text-muted">{a.object}</span></li>)}</ul>
      </section>
      <Advanced data={o} />
    </AdminFrame>
  );
}
