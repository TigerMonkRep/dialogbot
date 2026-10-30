import { ChannelOff, NotOperator, SalgFrame, dt, load } from "../shared";
import { DataRequestForm } from "./client";

type Req = { id: string; subject: string; value: string; kind: string; status: string; handled_at: string | null; created_at: string };
const KIND: Record<string, string> = { access: "Indsigt", erasure: "Sletning", objection: "Indsigelse" };
const SUBJECT: Record<string, string> = { phone: "Telefon", email: "E-mail", cvr: "CVR" };

export default async function RightsPage() {
  const r = await load<{ items: Req[] }>("/operator/salg/data-requests");
  if (!r.ok) {
    if (r.status === 501) return <SalgFrame active="/app/operator/salg/rettigheder" title="Indsigt og sletning"><ChannelOff message={r.message} /></SalgFrame>;
    return <NotOperator status={r.status} message={r.message} />;
  }
  return (
    <SalgFrame active="/app/operator/salg/rettigheder" title="Indsigt og sletning" intro="Anmodninger om Dialogbots eget salg: indsigt (alt vi har om et nummer, en e-mail eller et CVR-nummer som JSON), sletning (transskripter, opsummeringer, lyd og kontakter – også hos telefonudbyderen) og indsigelse (spærring). Nummeret spærres altid ved sletning, så vi ikke ringer igen. Svar den registrerede inden for 30 dage.">
      <DataRequestForm />
      <section className="rounded-2xl border-2 border-ink bg-paper p-space-md">
        <h2 className="font-display font-bold text-[18px] mb-2">Tidligere anmodninger</h2>
        {r.data.items.length === 0 ? <p className="text-muted text-[14px]">Ingen endnu.</p> : (
          <ul className="flex flex-col gap-1 text-[14px]">{r.data.items.map((x) => (
            <li key={x.id}>{dt(x.created_at)} · {KIND[x.kind] ?? x.kind} · {SUBJECT[x.subject] ?? x.subject} {x.value} · {x.status === "done" ? `behandlet ${dt(x.handled_at)}` : x.status}</li>))}</ul>
        )}
      </section>
      <p className="text-[13px] text-muted">Faste frister (miljøet): lyd SALES_RETENTION_AUDIO_DAYS, transskript SALES_RETENTION_TRANSCRIPT_DAYS, opsummering SALES_RETENTION_SUMMARY_DAYS. Workeren sletter dagligt efter kl. 3. Udkast til tekst på /privatliv: docs/sales/privatliv-udkast.md (skal godkendes).</p>
    </SalgFrame>
  );
}
