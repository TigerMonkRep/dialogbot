"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client";
import { useSubmit } from "@/components/ui";
import { useT } from "@/i18n/client";

/** E07: the business's opt-in to also send the customer's booking messages by SMS (off by default; each SMS counts in
 *  the usage). Owners and admins only (bookings.manage); everyone else sees the state. */
export function SmsToggle({ wsId, enabled, canManage }: { wsId: string; enabled: boolean; canManage: boolean }) {
  const router = useRouter();
  const t = useT("app");
  const [on, setOn] = useState(enabled);
  const { run, pending, error } = useSubmit(async (next: boolean) => {
    const r = await api<{ sms_enabled: boolean }>(`/workspaces/${wsId}/bookings/messages/settings`, {
      method: "PUT", body: JSON.stringify({ sms_enabled: next }),
    });
    setOn(r.sms_enabled);
    router.refresh();
  });
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-4">
        <span id="sms-toggle-label" className="text-[15px] font-semibold text-ink">{t("bookings.messages.sending.smsLabel")}</span>
        <button type="button" role="switch" aria-checked={on} aria-labelledby="sms-toggle-label" aria-describedby="sms-toggle-help"
          disabled={!canManage || pending} onClick={() => run(!on)}
          className={`shrink-0 inline-flex items-center w-[84px] h-11 p-1 rounded-full transition-colors disabled:cursor-not-allowed ${on ? "bg-accent justify-end" : "bg-muted justify-start"} ${canManage ? "" : "opacity-60"}`}>
          <span className="w-9 h-9 rounded-full bg-paper" />
        </button>
      </div>
      <p id="sms-toggle-help" className="text-[14px] leading-relaxed text-ink-soft">{t("bookings.messages.sending.smsHelp")}</p>
      <p className="text-[13px] text-muted">{t("bookings.messages.sending.blocked")}</p>
      <p role="status" data-testid="sms-state" className="text-[14px] font-semibold text-ink">
        {on ? t("bookings.messages.sending.on") : t("bookings.messages.sending.off")}
      </p>
      {!canManage && <p className="text-[13px] text-muted">{t("bookings.messages.sending.readOnly")}</p>}
      {error && <p role="alert" className="text-[14px] font-semibold text-danger">{t("bookings.messages.sending.error")}</p>}
    </div>
  );
}
