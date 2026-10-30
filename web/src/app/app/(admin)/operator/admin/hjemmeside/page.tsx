import Link from "next/link";
import { Advanced, AdminFrame, NotOperator, dt, load } from "../shared";

/** Website statistics: Vercel Web Analytics (cookieless, every visitor) and Google Analytics 4 (only visitors who
 *  said yes to the cookie banner). Both are read by the backend with cached results; see docs/website-analytics.md. */

type Row = { key: string; visitors?: number; pageviews?: number; sessions?: number };
type Vercel = { configured: boolean; dashboard: string; error: string | null; visitors?: number; pageviews?: number;
  by_day?: Row[]; pages?: Row[]; referrers?: Row[]; countries?: Row[]; devices?: Row[] };
type Ga = { configured: boolean; dashboard: string; property_id: string | null; error: string | null; users?: number; sessions?: number;
  pageviews?: number; by_day?: Row[]; pages?: Row[]; sources?: Row[] };
type Stats = { days: number; fetched_at: string; vercel: Vercel; ga: Ga };

const box = "rounded-2xl bg-paper border-2 border-ink p-space-md";
const RANGES = [7, 30, 90] as const;
const COUNTRY: Record<string, string> = { DK: "Danmark", SE: "Sverige", NO: "Norge", DE: "Tyskland", GB: "Storbritannien", US: "USA", NL: "Holland" };
const DEVICE: Record<string, string> = { desktop: "Computer", mobile: "Mobil", tablet: "Tablet" };
const n = (v?: number) => (v ?? 0).toLocaleString("da-DK");

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className={box}><p className="eyebrow">{label}</p><p className="font-display font-extrabold text-[32px] tabular-nums">{value}</p>
      {hint && <p className="text-[13px] text-muted m-0">{hint}</p>}</div>
  );
}

function Bars({ rows, metric }: { rows: Row[]; metric: "visitors" | "pageviews" }) {
  if (rows.length === 0) return <p className="text-on-surface-variant m-0">Ingen data i perioden endnu.</p>;
  const max = Math.max(1, ...rows.map((r) => r[metric] ?? 0));
  return (
    <div className="flex items-end gap-[3px] h-[120px]" role="img" aria-label={`${metric === "visitors" ? "Besøgende" : "Sidevisninger"} pr. dag`}>
      {rows.map((r) => (
        <div key={r.key} title={`${r.key}: ${n(r[metric])}`} className="flex-1 min-w-[3px] bg-accent rounded-t-[3px]"
          style={{ height: `${Math.max(2, ((r[metric] ?? 0) / max) * 100)}%` }} />
      ))}
    </div>
  );
}

function Top({ title, rows, metric, label }: { title: string; rows?: Row[]; metric: "visitors" | "pageviews" | "sessions"; label?: (k: string) => string }) {
  const list = (rows ?? []).filter((r) => r.key !== "");
  return (
    <section className={box}>
      <h2 className="font-display font-bold text-[18px] mb-2">{title}</h2>
      {list.length === 0 ? <p className="text-on-surface-variant m-0">Ingen data endnu.</p> : (
        <ol className="m-0 p-0 list-none divide-y divide-line">
          {list.map((r) => (
            <li key={r.key} className="flex justify-between gap-3 py-1.5 text-[14px]">
              <span className="truncate text-ink">{label ? label(r.key) : r.key || "(direkte)"}</span>
              <span className="tabular-nums font-semibold shrink-0">{n(r[metric])}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function NotConfigured({ what, steps, dashboard }: { what: string; steps: string[]; dashboard: string }) {
  return (
    <section className={`${box} bg-panel`}>
      <h2 className="font-display font-bold text-[18px] mb-1">{what} – ikke sat op endnu</h2>
      <ol className="m-0 pl-5 text-[14px] text-ink-soft flex flex-col gap-1">{steps.map((s) => <li key={s}>{s}</li>)}</ol>
      <p className="text-[14px] mt-2 m-0">Indtil da: <a className="underline font-semibold text-ink" href={dashboard} target="_blank" rel="noreferrer">åbn tallene hos {what.split(" ")[0]}</a>.</p>
    </section>
  );
}

export default async function Website({ searchParams }: { searchParams: Promise<{ dage?: string }> }) {
  const { dage = "30" } = await searchParams;
  const days = RANGES.includes(Number(dage) as (typeof RANGES)[number]) ? Number(dage) : 30;
  const st = await load<Stats>(`/operator/analytics/website?days=${days}`);
  if (!st) return <NotOperator />;
  const v = st.vercel;
  const g = st.ga;
  return (
    <AdminFrame active="/app/operator/admin/hjemmeside" title="Hjemmeside" intro="Hvor mange besøger dialogbot.dk, hvor kommer de fra, og hvad læser de? Vercel tæller alle besøgende uden cookies; Google Analytics tæller dem, der har sagt ja til cookies, og giver flere detaljer.">
      <div className="flex flex-wrap items-center gap-2">
        {RANGES.map((r) => (
          <Link key={r} href={`?dage=${r}`} aria-current={r === days ? "page" : undefined}
            className={`px-3 py-1.5 rounded-full border-2 border-ink text-[13px] font-semibold ${r === days ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`}>Seneste {r} dage</Link>
        ))}
        <span className="text-[13px] text-muted ml-auto">Hentet {dt(st.fetched_at)} · opdateres hvert 10. minut</span>
      </div>

      <h2 className="font-display font-extrabold text-[22px] -mb-3">Vercel Web Analytics <span className="text-[14px] font-body font-normal text-muted">· alle besøgende, ingen cookies · <a className="underline" href={v.dashboard} target="_blank" rel="noreferrer">åbn hos Vercel</a></span></h2>
      {!v.configured ? (
        <NotConfigured what="Vercel Web Analytics" dashboard={v.dashboard} steps={[
          "Slå Web Analytics til under projektet dialogbot → Analytics på vercel.com (én knap).",
          "Lav et API-token under Account → Tokens (scope: rene-simonsens-projects, læseadgang er nok).",
          "Læg det ind som VERCEL_API_TOKEN på backend-tjenesten i Render og genstart.",
        ]} />
      ) : v.error ? <p className={`${box} text-danger`}>{v.error}</p> : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-space-md">
            <Tile label="Besøgende" value={n(v.visitors)} hint={`seneste ${days} dage`} />
            <Tile label="Sidevisninger" value={n(v.pageviews)} />
            <Tile label="Pr. besøg" value={v.visitors ? (v.pageviews! / v.visitors).toLocaleString("da-DK", { maximumFractionDigits: 1 }) : "–"} hint="sider pr. besøgende" />
            <Tile label="Pr. dag" value={n(Math.round((v.visitors ?? 0) / days))} hint="besøgende i gennemsnit" />
          </div>
          <section className={box}><h2 className="font-display font-bold text-[18px] mb-2">Besøgende pr. dag</h2><Bars rows={v.by_day ?? []} metric="visitors" /></section>
          <div className="grid md:grid-cols-2 gap-space-md">
            <Top title="Mest læste sider" rows={v.pages} metric="pageviews" />
            <Top title="Hvor kommer de fra" rows={v.referrers} metric="visitors" label={(k) => k || "Direkte / ukendt"} />
            <Top title="Lande" rows={v.countries} metric="visitors" label={(k) => COUNTRY[k] ?? k} />
            <Top title="Enheder" rows={v.devices} metric="visitors" label={(k) => DEVICE[k] ?? k} />
          </div>
        </>
      )}

      <h2 className="font-display font-extrabold text-[22px] -mb-3 mt-2">Google Analytics 4 <span className="text-[14px] font-body font-normal text-muted">· kun besøgende med cookie-ja · <a className="underline" href={g.dashboard} target="_blank" rel="noreferrer">åbn hos Google</a></span></h2>
      {!g.configured ? (
        <NotConfigured what="Google Analytics" dashboard={g.dashboard} steps={[
          "Opret en GA4-ejendom for dialogbot.dk på analytics.google.com og find Målings-id (G-…) under Administrer → Datastreams.",
          "Læg id'et ind som NEXT_PUBLIC_GA_MEASUREMENT_ID i Vercel (projektet dialogbot → Settings → Environment Variables) og deploy igen – så kører banneret og scriptet på siden.",
          "For at se tallene her: opret en servicekonto i Google Cloud med Google Analytics Data API slået til, hent dens JSON-nøgle, og giv servicekontoens e-mail rollen Læser (Viewer) på GA4-ejendommen under Administrer → Adgangsstyring.",
          "Læg GA4_PROPERTY_ID (det numeriske ejendoms-id) og GA_SERVICE_ACCOUNT_JSON (hele JSON-nøglen på én linje) ind på backend-tjenesten i Render og genstart.",
        ]} />
      ) : g.error ? <p className={`${box} text-danger`}>{g.error}</p> : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-space-md">
            <Tile label="Brugere" value={n(g.users)} hint={`seneste ${days} dage`} />
            <Tile label="Sessioner" value={n(g.sessions)} />
            <Tile label="Sidevisninger" value={n(g.pageviews)} />
          </div>
          <section className={box}><h2 className="font-display font-bold text-[18px] mb-2">Brugere pr. dag</h2><Bars rows={g.by_day ?? []} metric="visitors" /></section>
          <div className="grid md:grid-cols-2 gap-space-md">
            <Top title="Mest læste sider" rows={g.pages} metric="pageviews" />
            <Top title="Kilder" rows={g.sources} metric="sessions" />
          </div>
        </>
      )}
      <Advanced data={st} />
    </AdminFrame>
  );
}
