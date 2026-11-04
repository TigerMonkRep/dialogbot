import { AdminFrame, Advanced, NotOperator, load } from "../admin/shared";

type Row = { invites_created: number; opened: number; accepted: number; new_users_from_invites: number; activated: number; k_factor: number };
type Growth = Row & { by_addon: Record<string, Partial<Row>> };

const COLS: [keyof Row, string][] = [
  ["invites_created", "Invitationer"], ["opened", "Åbnet"], ["accepted", "Accepteret"], ["new_users_from_invites", "Nye brugere"],
  ["activated", "Aktiveret"], ["k_factor", "K-faktor"],
];
const fmt = (k: keyof Row, v: number | undefined) => v === undefined || v === null ? "–" : k === "k_factor" ? v.toLocaleString("da-DK", { maximumFractionDigits: 2 }) : v.toLocaleString("da-DK");
const pct = (a?: number, b?: number) => (a && b ? `${Math.round((a / b) * 100)} %` : "–");

/** Operator: Dialogbot Privat's built-in growth – invitations to shared lists and wishlists, and how many become users.
 *  k-faktor = activated new users per inviting user. Danish only, like the other operator pages. */
export default async function OperatorPrivatGrowthPage() {
  const g = await load<Growth>("/operator/privat/growth");
  if (!g) return <AdminFrame active="/app/operator/privat" title="Privat · vækst" eyebrow="Admin · Privat"><NotOperator /></AdminFrame>;
  const addons = Object.entries(g.by_addon ?? {});
  return (
    <AdminFrame active="/app/operator/privat" title="Privat · vækst" eyebrow="Admin · Privat"
      intro="Invitationer fra Dialogbot Privat (delte lister, ønskelister …) og hvor mange, der bliver til brugere. Aktiveret = bekræftet e-mail og første egne opgave. K-faktor = aktiverede nye brugere pr. inviterende bruger.">
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {COLS.map(([k, label]) => (
          <div key={k} className="rounded-2xl border-2 border-ink bg-paper p-4">
            <span className="eyebrow">{label}</span>
            <div className="font-display font-extrabold text-[32px] leading-none mt-2 tabular-nums">{fmt(k, g[k])}</div>
          </div>
        ))}
      </div>
      <p className="text-[14px] text-ink-soft">Åbnet af invitationer: {pct(g.opened, g.invites_created)} · accepteret af åbnede: {pct(g.accepted, g.opened)} · aktiveret af nye: {pct(g.activated, g.new_users_from_invites)}</p>
      <div className="rounded-2xl border-2 border-ink bg-paper overflow-x-auto">
        <table className="w-full text-[14px] table-stack">
          <thead><tr className="text-left border-b-2 border-ink"><th className="p-3">Tilføjelse</th>{COLS.map(([k, l]) => <th key={k} className="p-3 text-right">{l}</th>)}</tr></thead>
          <tbody>
            {addons.length === 0 && <tr><td className="p-3 text-muted" colSpan={COLS.length + 1}>Ingen invitationer endnu.</td></tr>}
            {addons.map(([key, row]) => (
              <tr key={key} className="border-b-[1.5px] border-line last:border-0">
                <td className="p-3 font-semibold" data-label="Tilføjelse">{key}</td>
                {COLS.map(([k, l]) => <td key={k} className="p-3 text-right tabular-nums stack-inline" data-label={l}>{fmt(k, row[k])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Advanced data={g} />
    </AdminFrame>
  );
}
