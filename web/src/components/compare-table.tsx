import { getT } from "@/i18n/server";

/** Plain comparison table for the /viden comparison pages. Rows: [what, Dialogbot, the other]. */
export async function CompareTable({ other, rows }: { other: string; rows: [string, string, string][] }) {
  const t = await getT("landing.compareTable");
  return (
    <div className="overflow-x-auto -mx-1 px-1">
      <table className="w-full min-w-[520px] border-collapse text-[15px] leading-snug text-left">
        <thead>
          <tr className="border-b-2 border-ink">
            <th scope="col" className="py-2.5 pr-3 font-display font-bold text-ink"><span className="sr-only">{t("difference")}</span></th>
            <th scope="col" className="py-2.5 pr-3 font-display font-bold text-ink">Dialogbot</th>
            <th scope="col" className="py-2.5 font-display font-bold text-ink">{other}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([what, a, b]) => (
            <tr key={what} className="border-b border-line align-top">
              <th scope="row" className="py-3 pr-3 font-semibold text-ink">{what}</th>
              <td className="py-3 pr-3">{a}</td>
              <td className="py-3">{b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
