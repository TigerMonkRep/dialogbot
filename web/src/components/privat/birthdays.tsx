"use client";
/** Fødselsdage app (inside the app sheet when it is on, and /privat/foedselsdage): the saved birthdays in the order
 *  they come, how many days before the reminder comes, add one by hand, remove one. Peter does the same in the chat. */
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import type { Birthday } from "@/lib/privat/api";
import { Eyebrow } from "./bits";
import { usePrivat } from "./store";

const DAYS = [0, 1, 3, 7, 14];

export function BirthdaysPanel() {
  const t = useT("privat");
  const { api } = usePrivat();
  const [items, setItems] = useState<Birthday[] | null>(null);
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setItems((await api.birthdays()).items); } catch (e) { setErr((e as ApiError).message); }
  }, [api]);
  useEffect(() => { void load(); }, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    setErr(null);
    try { await fn(); await load(); } catch (e) { setErr((e as ApiError).message); }
  };
  const add = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !date.trim()) return;
    void run(async () => { await api.addBirthday({ name: name.trim(), date: date.trim() }); setName(""); setDate(""); });
  };
  const when = (b: Birthday) => b.days_until === 0 ? t("birthdays.today") : b.days_until === 1 ? t("birthdays.tomorrow") : t("birthdays.inDays", { n: b.days_until });

  return (
    <div className="flex flex-col gap-4" data-testid="birthdays-panel">
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      <section className="flex flex-col gap-2" aria-labelledby="bd-list">
        <h3 id="bd-list" className="m-0 text-[15px] font-semibold font-body">{t("birthdays.title")}</h3>
        {items === null ? <p className="m-0 text-[14px] text-muted">{t("birthdays.loading")}</p>
          : items.length === 0 ? <p className="m-0 text-[14px] text-muted">{t("birthdays.none")}</p> : (
          <ul className="m-0 p-0 list-none flex flex-col gap-2">
            {items.map((b) => (
              <li key={b.id} className="rounded-[16px] border-[1.5px] border-ink bg-paper p-3 flex flex-col gap-1.5">
                <span className="font-semibold text-[15px] [overflow-wrap:anywhere]">
                  {b.name}{b.turns ? ` · ${t("birthdays.turns", { n: b.turns })}` : ""}
                </span>
                <span className="text-[14px] text-ink-soft">{b.date_text} · {when(b)}</span>
                <span className="flex gap-2 flex-wrap items-center">
                  <label className="text-[13px] text-muted flex items-center gap-1.5">
                    {t("birthdays.remind")}
                    <select value={b.remind_days_before} onChange={(e) => void run(() => api.updateBirthday(b.id, { remind_days_before: Number(e.target.value) }))}
                      className="min-h-[40px] rounded-xl border-2 border-ink bg-paper px-2 text-[14px]">
                      {Array.from(new Set([...DAYS, b.remind_days_before])).sort((x, y) => x - y).map((d) => (
                        <option key={d} value={d}>{d === 0 ? t("birthdays.onTheDay") : t("birthdays.daysBefore", { n: d })}</option>
                      ))}
                    </select>
                  </label>
                  <Button variant="outline" className="rounded-full border-2" onClick={() => void run(() => api.removeBirthday(b.id))} aria-label={`${t("birthdays.remove")}: ${b.name}`}>{t("birthdays.remove")}</Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <form onSubmit={add} className="rounded-[18px] border-[1.5px] border-ink bg-panel p-3.5 flex flex-col gap-2" aria-labelledby="bd-add">
        <Eyebrow><span id="bd-add">{t("birthdays.add")}</span></Eyebrow>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("birthdays.namePlaceholder")} aria-label={t("birthdays.name")} maxLength={100}
          className="w-full min-h-[44px] rounded-xl border-2 border-ink bg-paper px-3 text-[15px]" />
        <input value={date} onChange={(e) => setDate(e.target.value)} placeholder={t("birthdays.datePlaceholder")} aria-label={t("birthdays.date")} maxLength={40}
          className="w-full min-h-[44px] rounded-xl border-2 border-ink bg-paper px-3 text-[15px]" />
        <Button type="submit" className="rounded-full self-start" disabled={!name.trim() || !date.trim()}>{t("birthdays.save")}</Button>
        <p className="m-0 text-[13px] text-muted">{t("birthdays.hint")}</p>
      </form>
    </div>
  );
}
