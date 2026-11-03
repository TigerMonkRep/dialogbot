"use client";
import { useState } from "react";
import { api } from "@/lib/client";
import { ErrorBox, inputCls, useSubmit } from "@/components/ui";
import { useT } from "@/i18n/client";

type Initial = { email_enabled: boolean; send_hour_local: number; timezone: string };

/** Direct editing of the daily report (the assistant does the same through «Godkend»). Saves on the button, shows «Gemt». */
export function ReportSettingsForm({ wsId, initial }: { wsId: string; initial: Initial }) {
  const t = useT("app");
  const [enabled, setEnabled] = useState(initial.email_enabled);
  const [hour, setHour] = useState(initial.send_hour_local);
  const [saved, setSaved] = useState(false);
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/reports/settings`, { method: "PUT", body: JSON.stringify({ email_enabled: enabled, send_hour_local: hour }) });
    setSaved(true); setTimeout(() => setSaved(false), 2500);
  });
  return (
    <details className="group">
      <summary className="list-none [&::-webkit-details-marker]:hidden cursor-pointer inline-flex items-center min-h-[44px] px-4 rounded-xl border-[1.5px] border-ink text-[14px] font-semibold text-ink hover:bg-panel">{t("week.form.edit")}</summary>
      <form className="mt-3 flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
        <label className="flex items-center gap-3 text-[15px] text-ink">
          <input type="checkbox" checked={enabled} onChange={(e) => { setEnabled(e.target.checked); setSaved(false); }} className="w-5 h-5 accent-[#2456F6]" />
          {t("week.form.email")}
        </label>
        <label className="flex flex-wrap items-center gap-3 text-[15px] text-ink" htmlFor="r-hour">{t("week.form.at")}
          <select id="r-hour" className={`${inputCls} w-28`} value={hour} onChange={(e) => { setHour(Number(e.target.value)); setSaved(false); }}>
            {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
          </select>
        </label>
        <ErrorBox error={save.error} />
        <div className="flex items-center gap-3">
          <button type="submit" disabled={save.pending} className="inline-flex items-center min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-50">{t("common.save")}</button>
          {saved && <span role="status" className="text-[14px] font-semibold text-success">{t("common.saved")}</span>}
        </div>
      </form>
    </details>
  );
}
