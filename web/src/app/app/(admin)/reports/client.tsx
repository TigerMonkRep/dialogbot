"use client";
import { useState } from "react";
import { api } from "@/lib/client";
import { Button, ErrorBox, inputCls, useSubmit } from "@/components/ui";

export function ReportSettingsForm({ wsId, initial, canEdit }: { wsId: string; initial: { email_enabled: boolean; send_hour_local: number; timezone: string }; canEdit: boolean }) {
  const [enabled, setEnabled] = useState(initial.email_enabled);
  const [hour, setHour] = useState(initial.send_hour_local);
  const [saved, setSaved] = useState(false);
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/reports/settings`, { method: "PUT", body: JSON.stringify({ email_enabled: enabled, send_hour_local: hour }) });
    setSaved(true); setTimeout(() => setSaved(false), 2500);
  });
  return (
    <form className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <h3 className="font-headline-sm text-headline-sm text-primary">Dagsrapport på e-mail</h3>
      <label className="flex items-center gap-space-sm font-body-md text-body-md">
        <input type="checkbox" checked={enabled} disabled={!canEdit} onChange={(e) => setEnabled(e.target.checked)} className="w-5 h-5 rounded text-primary focus:ring-primary" />
        Send gårsdagens rapport til ejere og administratorer
      </label>
      <label className="flex flex-wrap items-center gap-space-sm font-body-md text-body-md" htmlFor="r-hour">Kl.
        <select id="r-hour" className={`${inputCls} w-24`} value={hour} disabled={!canEdit} onChange={(e) => setHour(Number(e.target.value))}>
          {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
        </select>
        <span className="font-body-sm text-body-sm text-on-surface-variant">({initial.timezone})</span>
      </label>
      <ErrorBox error={save.error} />
      {canEdit && <div className="flex items-center gap-space-sm"><Button type="submit" variant="tonal" icon="save" disabled={save.pending}>Gem</Button>{saved && <span role="status" className="font-label-md text-label-md text-secondary">Gemt</span>}</div>}
    </form>
  );
}
