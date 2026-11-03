"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Button, ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";

export type WebchatSettings = {
  version: number; enabled: boolean; widget_key: string; allowed_origins: string[]; greeting: string; effective_greeting: string;
  available: boolean; unavailable_reasons: string[]; last_seen_at: string | null; last_seen_origin: string | null; embed_code: string;
  limits: { max_message_chars: number; max_visitor_messages: number; max_new_conversations_per_hour: number };
};

export function WebchatForm({ wsId, initial, canManage }: { wsId: string; initial: WebchatSettings; canManage: boolean }) {
  const router = useRouter();
  const t = useT("settings");
  const locale = useLocale();
  const [s, setS] = useState(initial);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [origins, setOrigins] = useState(initial.allowed_origins.join("\n"));
  const [greeting, setGreeting] = useState(initial.greeting);
  const [copied, setCopied] = useState(false);
  const save = useSubmit(async () => {
    const next = await api<WebchatSettings>(`/workspaces/${wsId}/webchat`, { method: "PUT", body: JSON.stringify({
      expected_version: s.version, enabled, greeting, allowed_origins: origins.split(/[\s,]+/).filter(Boolean) }) });
    setS(next); setOrigins(next.allowed_origins.join("\n")); setEnabled(next.enabled);
    router.refresh();
  });
  const rotate = useSubmit(async () => {
    if (!confirm(t("webchat.form.rotateConfirm"))) return;
    const next = await api<WebchatSettings>(`/workspaces/${wsId}/webchat/rotate-key`, { method: "POST" });
    setS(next); router.refresh();
  });
  const copy = async () => { await navigator.clipboard.writeText(s.embed_code).catch(() => undefined); setCopied(true); setTimeout(() => setCopied(false), 2000); };
  const notReady = save.error?.code === "webchat_not_ready";
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
      <form className="lg:col-span-7 bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-3"
        onSubmit={(e) => { e.preventDefault(); save.run(); }}>
        <h3 className="font-display text-headline-sm text-ink">{t("webchat.form.title")}</h3>
        <label className="flex items-center justify-between gap-3 p-3 rounded-lg bg-panel cursor-pointer">
          <span><span className="block text-label-lg text-ink">{t("webchat.form.show")}</span><span className="block text-body-sm text-ink-soft">{t("webchat.form.showHelp")}</span></span>
          <input type="checkbox" role="switch" aria-label={t("webchat.form.show")} checked={enabled} disabled={!canManage} onChange={(e) => setEnabled(e.target.checked)} className="w-5 h-5 rounded text-ink focus:ring-ink" />
        </label>
        <div>
          <label htmlFor="origins" className="block text-label-md text-ink font-semibold mb-1">{t("webchat.form.origins")}</label>
          <textarea id="origins" rows={3} disabled={!canManage} className={`${inputCls} font-mono`} placeholder={t("webchat.form.originsPlaceholder")} value={origins} onChange={(e) => setOrigins(e.target.value)} aria-describedby="origins-hint" />
          <p id="origins-hint" className="text-body-sm text-ink-soft mt-1">{t("webchat.form.originsHint")}</p>
          {fieldError(save.error, "allowed_origins") && <p role="alert" className="text-label-md text-danger mt-1">{t("webchat.form.invalidOrigin", { value: fieldError(save.error, "allowed_origins") ?? "" })}</p>}
        </div>
        <div>
          <label htmlFor="greeting" className="block text-label-md text-ink font-semibold mb-1">{t("webchat.form.greeting")}</label>
          <input id="greeting" maxLength={300} disabled={!canManage} className={inputCls} placeholder={s.effective_greeting} value={greeting} onChange={(e) => setGreeting(e.target.value)} />
          <p className="text-body-sm text-ink-soft mt-1">{t("webchat.form.greetingHint")}</p>
        </div>
        {notReady ? <p role="alert" className="p-2 rounded-lg bg-danger-soft text-danger text-body-sm">{t("webchat.form.notReady")}</p> : <ErrorBox error={save.error} />}
        {canManage ? <div><Button type="submit" icon="save" disabled={save.pending}>{save.pending ? t("webchat.form.saving") : t("webchat.form.save")}</Button></div>
          : <p className="text-body-sm text-ink-soft">{t("webchat.form.onlyAdmins")}</p>}
      </form>

      <div className="lg:col-span-5 flex flex-col gap-4">
        <section className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-2">
          <h3 className="font-display text-headline-sm text-ink">{t("webchat.form.embedTitle")}</h3>
          <p className="text-body-sm text-ink-soft">{t("webchat.form.embedBefore")} <code>&lt;/body&gt;</code> {t("webchat.form.embedAfter")}</p>
          <pre className="p-2 rounded-lg bg-panel font-mono text-[12px] whitespace-pre-wrap break-all" aria-label={t("webchat.form.embedTitle")}>{s.embed_code}</pre>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="tonal" icon={copied ? "check" : "content_copy"} onClick={copy}>{copied ? t("webchat.form.copied") : t("webchat.form.copy")}</Button>
            {canManage && <Button type="button" variant="ghost" icon="autorenew" onClick={() => rotate.run()} disabled={rotate.pending}>{t("webchat.form.newKey")}</Button>}
          </div>
          <ErrorBox error={rotate.error} />
        </section>
        <section className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-1">
          <h3 className="font-display text-headline-sm text-ink">{t("webchat.form.install")}</h3>
          {s.last_seen_at
            ? <p className="text-body-sm text-ink flex items-center gap-1"><Icon name="check_circle" size={18} className="text-muted" />{t("webchat.form.lastSeen", { origin: s.last_seen_origin ?? "", when: new Date(s.last_seen_at).toLocaleString(HTML_LANG[locale]) })}</p>
            : <p className="text-body-sm text-ink-soft">{t("webchat.form.notSeen")}</p>}
          <p className="text-body-sm text-ink-soft">{t("webchat.form.limits", { messages: s.limits.max_visitor_messages, conversations: s.limits.max_new_conversations_per_hour, chars: s.limits.max_message_chars })}</p>
        </section>
      </div>
    </div>
  );
}
