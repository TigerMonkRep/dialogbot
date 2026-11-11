"use client";
/** Rejser app (step 1): the search – from where, where to (or a trip type, then Peter picks in the chat), when, how
 *  long, who, the total budget – and the offers with REAL prices, cheapest first. «Book» opens the seller's own page;
 *  nothing is booked or paid in Dialogbot. */
import { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import type { TripResult } from "@/lib/privat/api";
import { Eyebrow } from "./bits";
import { usePrivat } from "./store";

const INPUT = "w-full min-h-[44px] rounded-xl border-2 border-ink bg-paper px-3 text-[15px] text-ink";
const kr = (v: number) => `${v.toLocaleString("da-DK")} kr.`;

export function TravelPanel() {
  const t = useT("privat");
  const { api } = usePrivat();
  const [f, setF] = useState({ origin: "CPH", destinations: "", when: "", flexMonth: "", nights: "7", adults: "2", children: "0", budget: "", direct: false });
  const [res, setRes] = useState<TripResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.latestTrips().then((r) => setRes(r.search)).catch(() => {}); }, [api]);

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      setRes(await api.searchTrips({
        origin: f.origin.trim().toUpperCase(), destinations: f.destinations.split(/[\s,]+/).filter(Boolean).map((d) => d.toUpperCase()),
        ...(f.when ? { depart_date: f.when } : f.flexMonth ? { month: f.flexMonth } : {}),
        ...(f.nights ? { nights: Number(f.nights) } : {}), adults: Number(f.adults) || 1, children: Number(f.children) || 0,
        ...(f.budget ? { budget_dkk: Number(f.budget) } : {}), direct_only: f.direct,
      }));
    } catch (x) { setErr((x as ApiError).message); } finally { setBusy(false); }
  };
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <div className="flex flex-col gap-4" data-testid="travel-panel">
      <form onSubmit={search} className="rounded-[18px] border-[1.5px] border-ink bg-panel p-3.5 flex flex-col gap-2">
        <Eyebrow>{t("travel.search")}</Eyebrow>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-[13px] text-muted flex flex-col gap-1">{t("travel.origin")}<input value={f.origin} onChange={set("origin")} maxLength={3} className={INPUT} /></label>
          <label className="text-[13px] text-muted flex flex-col gap-1">{t("travel.destinations")}<input value={f.destinations} onChange={set("destinations")} placeholder="BCN, LIS" className={INPUT} /></label>
          <label className="text-[13px] text-muted flex flex-col gap-1">{t("travel.date")}<input type="date" value={f.when} onChange={set("when")} className={INPUT} /></label>
          <label className="text-[13px] text-muted flex flex-col gap-1">{t("travel.orMonth")}<input type="month" value={f.flexMonth} onChange={set("flexMonth")} className={INPUT} /></label>
          <label className="text-[13px] text-muted flex flex-col gap-1">{t("travel.nights")}<input type="number" min={1} max={60} value={f.nights} onChange={set("nights")} className={INPUT} /></label>
          <label className="text-[13px] text-muted flex flex-col gap-1">{t("travel.budget")}<input type="number" min={100} value={f.budget} onChange={set("budget")} className={INPUT} /></label>
          <label className="text-[13px] text-muted flex flex-col gap-1">{t("travel.adults")}<input type="number" min={1} max={9} value={f.adults} onChange={set("adults")} className={INPUT} /></label>
          <label className="text-[13px] text-muted flex flex-col gap-1">{t("travel.children")}<input type="number" min={0} max={8} value={f.children} onChange={set("children")} className={INPUT} /></label>
        </div>
        <label className="text-[14px] flex items-center gap-2 min-h-[44px]"><input type="checkbox" checked={f.direct} onChange={set("direct")} />{t("travel.direct")}</label>
        <Button type="submit" className="rounded-full self-start" disabled={busy}>{busy ? t("travel.searching") : t("travel.find")}</Button>
        <p className="m-0 text-[13px] text-muted">{t("travel.typeHint")}</p>
      </form>
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      {res && (
        <section className="flex flex-col gap-2" aria-labelledby="trip-results">
          <h3 id="trip-results" className="m-0 text-[15px] font-semibold font-body">{t("travel.results")}</h3>
          {res.offers.length === 0 && <p className="m-0 text-[14px] text-muted">{t("travel.none")}</p>}
          {res.offers.map((o) => (
            <div key={o.id} className="rounded-[16px] border-[1.5px] border-ink bg-paper p-3 flex flex-col gap-1">
              <span className="font-display font-bold text-[18px]">{kr(o.total_dkk)}</span>
              <span className="text-[14px]">{o.origin} → {o.destination} · {o.depart_at.slice(0, 10)}{o.return_at ? ` – ${o.return_at.slice(0, 10)}` : ""}</span>
              <span className="text-[13px] text-ink-soft">{[o.airline, o.stops === 0 ? t("travel.directShort") : o.stops ? t("travel.stops", { n: o.stops }) : "", o.price_note].filter(Boolean).join(" · ")}</span>
              {/* affiliate (F-PX-04, markedsføringsloven): marked as an ad, rel="sponsored" */}
              {o.sponsored && <span className="text-[12px] font-semibold text-muted" data-testid="trip-sponsored">{t("travel.sponsored")}</span>}
              <a href={o.book_url} target="_blank" rel={o.sponsored ? "sponsored noopener noreferrer" : "noopener noreferrer"} className="self-start mt-1 inline-flex items-center min-h-[44px] px-4 rounded-full bg-accent text-white font-semibold text-[15px]">{t("travel.book")}</a>
            </div>
          ))}
          {res.over_budget > 0 && <p className="m-0 text-[13px] text-muted">{t("travel.overBudget", { n: res.over_budget })}</p>}
          <p className="m-0 text-[13px] text-muted">{t("travel.disclaimer")}</p>
        </section>
      )}
    </div>
  );
}
