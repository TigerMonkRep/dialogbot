"use client";
/** Regninger app (inside the app sheet when it is on, and /privat/regninger): this month's bills with the total, every
 *  bill by next due date, how many days before the reminder comes, add one by hand, remove one. Dialogbot never pays. */
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import type { Bill, BillFrequency, BillsMonth } from "@/lib/privat/api";
import { Eyebrow } from "./bits";
import { usePrivat } from "./store";

const DAYS = [0, 1, 3, 7, 14];
const FREQS: BillFrequency[] = ["monthly", "quarterly", "half_yearly", "yearly", "once"];

export function BillsPanel() {
  const t = useT("privat");
  const { api } = usePrivat();
  const [data, setData] = useState<{ items: Bill[]; month: BillsMonth } | null>(null);
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [due, setDue] = useState("");
  const [freq, setFreq] = useState<BillFrequency>("monthly");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setData(await api.bills()); } catch (e) { setErr((e as ApiError).message); }
  }, [api]);
  useEffect(() => { void load(); }, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    setErr(null);
    try { await fn(); await load(); } catch (e) { setErr((e as ApiError).message); }
  };
  const add = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !due) return;
    void run(async () => {
      await api.addBill({ name: name.trim(), due_date: due, frequency: freq, ...(amount.trim() ? { amount: amount.trim() } : {}) });
      setName(""); setAmount(""); setDue("");
    });
  };
  const when = (b: Bill) => b.days_until === 0 ? t("bills.today") : b.days_until === 1 ? t("bills.tomorrow") : t("bills.inDays", { n: b.days_until });

  return (
    <div className="flex flex-col gap-4" data-testid="bills-panel">
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      {data && data.month.items.length > 0 && (
        <section className="rounded-[18px] border-[1.5px] border-ink bg-panel p-3.5 flex flex-col gap-1" aria-labelledby="bills-month">
          <Eyebrow><span id="bills-month">{t("bills.month", { month: data.month.month })}</span></Eyebrow>
          <span className="font-display font-bold text-[22px]">{data.month.total_text}</span>
          {data.month.without_amount > 0 && <span className="text-[13px] text-muted">{t("bills.withoutAmount", { n: data.month.without_amount })}</span>}
        </section>
      )}
      <section className="flex flex-col gap-2" aria-labelledby="bills-list">
        <h3 id="bills-list" className="m-0 text-[15px] font-semibold font-body">{t("bills.title")}</h3>
        {data === null ? <p className="m-0 text-[14px] text-muted">{t("bills.loading")}</p>
          : data.items.length === 0 ? <p className="m-0 text-[14px] text-muted">{t("bills.none")}</p> : (
          <ul className="m-0 p-0 list-none flex flex-col gap-2">
            {data.items.map((b) => (
              <li key={b.id} className="rounded-[16px] border-[1.5px] border-ink bg-paper p-3 flex flex-col gap-1.5">
                <span className="font-semibold text-[15px] [overflow-wrap:anywhere]">{b.name}{b.amount_text ? ` · ${b.amount_text}` : ""}</span>
                <span className="text-[14px] text-ink-soft">{b.due_text} · {when(b)} · {t(`bills.freq.${b.frequency}`)}</span>
                <span className="flex gap-2 flex-wrap items-center">
                  <label className="text-[13px] text-muted flex items-center gap-1.5">
                    {t("bills.remind")}
                    <select value={b.remind_days_before} onChange={(e) => void run(() => api.updateBill(b.id, { remind_days_before: Number(e.target.value) }))}
                      className="min-h-[40px] rounded-xl border-2 border-ink bg-paper px-2 text-[14px]">
                      {Array.from(new Set([...DAYS, b.remind_days_before])).sort((x, y) => x - y).map((d) => (
                        <option key={d} value={d}>{d === 0 ? t("bills.onTheDay") : t("bills.daysBefore", { n: d })}</option>
                      ))}
                    </select>
                  </label>
                  <Button variant="outline" className="rounded-full border-2" onClick={() => void run(() => api.removeBill(b.id))} aria-label={`${t("bills.remove")}: ${b.name}`}>{t("bills.remove")}</Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <form onSubmit={add} className="rounded-[18px] border-[1.5px] border-ink bg-panel p-3.5 flex flex-col gap-2" aria-labelledby="bills-add">
        <Eyebrow><span id="bills-add">{t("bills.add")}</span></Eyebrow>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("bills.namePlaceholder")} aria-label={t("bills.name")} maxLength={100}
          className="w-full min-h-[44px] rounded-xl border-2 border-ink bg-paper px-3 text-[15px]" />
        <input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={t("bills.amountPlaceholder")} aria-label={t("bills.amount")} maxLength={40} inputMode="decimal"
          className="w-full min-h-[44px] rounded-xl border-2 border-ink bg-paper px-3 text-[15px]" />
        <label className="text-[13px] text-muted flex flex-col gap-1">{t("bills.nextDue")}
          <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className="w-full min-h-[44px] rounded-xl border-2 border-ink bg-paper px-3 text-[15px] text-ink" />
        </label>
        <label className="text-[13px] text-muted flex flex-col gap-1">{t("bills.how")}
          <select value={freq} onChange={(e) => setFreq(e.target.value as BillFrequency)} className="min-h-[44px] rounded-xl border-2 border-ink bg-paper px-2 text-[15px] text-ink">
            {FREQS.map((f) => <option key={f} value={f}>{t(`bills.freq.${f}`)}</option>)}
          </select>
        </label>
        <Button type="submit" className="rounded-full self-start" disabled={!name.trim() || !due}>{t("bills.save")}</Button>
        <p className="m-0 text-[13px] text-muted">{t("bills.never")}</p>
      </form>
    </div>
  );
}
