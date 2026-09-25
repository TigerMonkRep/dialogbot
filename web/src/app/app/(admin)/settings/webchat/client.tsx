"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Button, ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";

export type WebchatSettings = {
  version: number; enabled: boolean; widget_key: string; allowed_origins: string[]; greeting: string; effective_greeting: string;
  available: boolean; unavailable_reasons: string[]; last_seen_at: string | null; last_seen_origin: string | null; embed_code: string;
  limits: { max_message_chars: number; max_visitor_messages: number; max_new_conversations_per_hour: number };
};

export function WebchatForm({ wsId, initial, canManage }: { wsId: string; initial: WebchatSettings; canManage: boolean }) {
  const router = useRouter();
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
    if (!confirm("Lav en ny widgetnøgle? Den nuværende indlejringskode holder op med at virke med det samme.")) return;
    const next = await api<WebchatSettings>(`/workspaces/${wsId}/webchat/rotate-key`, { method: "POST" });
    setS(next); router.refresh();
  });
  const copy = async () => { await navigator.clipboard.writeText(s.embed_code).catch(() => undefined); setCopied(true); setTimeout(() => setCopied(false), 2000); };
  const notReady = save.error?.code === "webchat_not_ready";
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
      <form className="lg:col-span-7 bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md"
        onSubmit={(e) => { e.preventDefault(); save.run(); }}>
        <h3 className="font-headline-sm text-headline-sm text-primary">Indstillinger</h3>
        <label className="flex items-center justify-between gap-space-md p-space-md rounded-lg bg-surface-container-low cursor-pointer">
          <span><span className="block font-label-lg text-label-lg text-on-surface">Vis widgetten på hjemmesiden</span><span className="block font-body-sm text-body-sm text-on-surface-variant">Kunder kan skrive med assistenten på de domæner, I angiver nedenfor.</span></span>
          <input type="checkbox" role="switch" aria-label="Vis widgetten på hjemmesiden" checked={enabled} disabled={!canManage} onChange={(e) => setEnabled(e.target.checked)} className="w-5 h-5 rounded text-primary focus:ring-primary" />
        </label>
        <div>
          <label htmlFor="origins" className="block font-label-md text-label-md text-on-surface font-semibold mb-1">Godkendte domæner</label>
          <textarea id="origins" rows={3} disabled={!canManage} className={`${inputCls} font-mono`} placeholder={"https://www.dinvirksomhed.dk"} value={origins} onChange={(e) => setOrigins(e.target.value)} aria-describedby="origins-hint" />
          <p id="origins-hint" className="font-body-sm text-body-sm text-on-surface-variant mt-1">Ét pr. linje, med https:// og uden sti. Widgetten kan ikke indlejres andre steder.</p>
          {fieldError(save.error, "allowed_origins") && <p role="alert" className="text-label-md text-error mt-1">Ugyldigt domæne: {fieldError(save.error, "allowed_origins")}</p>}
        </div>
        <div>
          <label htmlFor="greeting" className="block font-label-md text-label-md text-on-surface font-semibold mb-1">Velkomsthilsen</label>
          <input id="greeting" maxLength={300} disabled={!canManage} className={inputCls} placeholder={s.effective_greeting} value={greeting} onChange={(e) => setGreeting(e.target.value)} />
          <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">Tom = standardhilsen.</p>
        </div>
        {notReady ? <p role="alert" className="p-space-sm rounded-lg bg-error-container text-on-error-container font-body-sm text-body-sm">Widgetten kan ikke slås til endnu – se punkterne ovenfor.</p> : <ErrorBox error={save.error} />}
        {canManage ? <div><Button type="submit" icon="save" disabled={save.pending}>{save.pending ? "Gemmer…" : "Gem indstillinger"}</Button></div>
          : <p className="font-body-sm text-body-sm text-on-surface-variant">Kun ejere og administratorer kan ændre webchat.</p>}
      </form>

      <div className="lg:col-span-5 flex flex-col gap-space-lg">
        <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
          <h3 className="font-headline-sm text-headline-sm text-primary">Indlejringskode</h3>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Indsæt koden lige før <code>&lt;/body&gt;</code> på alle sider, hvor chatten skal vises.</p>
          <pre className="p-space-sm rounded-lg bg-surface-container-low font-mono text-[12px] whitespace-pre-wrap break-all" aria-label="Indlejringskode">{s.embed_code}</pre>
          <div className="flex flex-wrap gap-space-sm">
            <Button type="button" variant="tonal" icon={copied ? "check" : "content_copy"} onClick={copy}>{copied ? "Kopieret" : "Kopiér kode"}</Button>
            {canManage && <Button type="button" variant="ghost" icon="autorenew" onClick={() => rotate.run()} disabled={rotate.pending}>Ny nøgle</Button>}
          </div>
          <ErrorBox error={rotate.error} />
        </section>
        <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-xs">
          <h3 className="font-headline-sm text-headline-sm text-primary">Installation</h3>
          {s.last_seen_at
            ? <p className="font-body-sm text-body-sm text-on-surface flex items-center gap-space-xs"><Icon name="check_circle" size={18} className="text-secondary" />Chatten blev sidst åbnet på {s.last_seen_origin} {new Date(s.last_seen_at).toLocaleString("da-DK")}.</p>
            : <p className="font-body-sm text-body-sm text-on-surface-variant">Chatten er endnu ikke åbnet på et af jeres domæner. Åbn den på hjemmesiden og kør tjekket i opsætningsguiden.</p>}
          <p className="font-body-sm text-body-sm text-on-surface-variant">Grænser: {s.limits.max_visitor_messages} beskeder pr. samtale, {s.limits.max_new_conversations_per_hour} nye samtaler i timen, {s.limits.max_message_chars} tegn pr. besked.</p>
        </section>
      </div>
    </div>
  );
}
