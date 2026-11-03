"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";
import { useT } from "@/i18n/client";

export type Script = { version: number; persona_name: string; address_form: string; greeting: string; collect: string[]; escalation: string; avoid: string; closing: string };
type Suggestion = Pick<Script, "greeting" | "collect" | "escalation" | "avoid" | "closing">;

/** R05 manuscript. Empty script + AI available: a proposal is filled in (not saved) for the owner to edit. */
export function ScriptEditor({ wsId, script, canManage, aiReady }: { wsId: string; script: Script; canManage: boolean; aiReady: boolean }) {
  const router = useRouter();
  const t = useT("app");
  const [f, setF] = useState<Script>(script);
  const [collectText, setCollectText] = useState(script.collect.join("\n"));
  const [note, setNote] = useState<"suggested" | "saved" | null>(null);
  useEffect(() => { setF(script); setCollectText(script.collect.join("\n")); }, [script.version]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/reception/script`, { method: "PUT", body: JSON.stringify({ ...f, collect: collectText.split("\n"), expected_version: script.version }) });
    setNote("saved"); router.refresh();
  });
  const suggest = useSubmit(async () => {
    const s = await api<Suggestion>(`/workspaces/${wsId}/reception/script/suggestions`, { method: "POST", body: "{}" });
    setF((cur) => ({ ...cur, ...s })); setCollectText(s.collect.join("\n")); setNote("suggested");
  });
  const empty = !script.greeting && !script.collect.length && !script.escalation && !script.avoid && !script.closing;
  const auto = useRef(false);
  useEffect(() => {
    if (auto.current || !empty || !canManage || !aiReady) return;
    auto.current = true; suggest.run();
  }, [empty, canManage, aiReady, suggest]);
  const set = (k: keyof Script) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { setNote(null); setF({ ...f, [k]: e.target.value }); };
  const field = (k: keyof Script, label: string, hint: string, rows = 2) => (
    <div>
      <label htmlFor={`rs-${k}`} className="block text-label-md font-semibold mb-1">{label}</label>
      <textarea id={`rs-${k}`} rows={rows} className={`${inputCls} resize-y`} value={String(f[k] ?? "")} onChange={set(k)} disabled={!canManage} />
      <p className="mt-1 text-body-sm text-ink-soft">{hint}</p>
    </div>
  );
  return (
    <form className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-display text-headline-sm text-ink">{t("reception.script.title")}</h2>
          <p className="text-body-sm text-ink-soft max-w-2xl">{t("reception.script.intro")}</p>
        </div>
        {script.version > 0 && <span className="px-2 py-0.5 rounded-full bg-success-soft text-success text-label-sm font-semibold">{t("reception.script.activeVersion", { v: script.version })}</span>}
      </div>
      {!canManage && <Alert kind="info">{t("reception.script.onlyAdmins")}</Alert>}
      {suggest.pending && <p role="status" className="text-body-sm text-ink-soft flex items-center gap-1"><Icon name="auto_awesome" size={18} />{t("reception.script.writing")}</p>}
      {note === "suggested" && <Alert kind="info">{t("reception.script.suggested")}</Alert>}
      {note === "saved" && <Alert kind="ok">{t("reception.script.saved")}</Alert>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label htmlFor="rs-persona" className="block text-label-md font-semibold mb-1">{t("reception.script.persona")}</label>
          <input id="rs-persona" className={inputCls} maxLength={60} placeholder={t("reception.script.personaPlaceholder")} value={f.persona_name} onChange={set("persona_name")} disabled={!canManage} />
        </div>
        <div>
          <label htmlFor="rs-form" className="block text-label-md font-semibold mb-1">{t("reception.script.address")}</label>
          <select id="rs-form" className={inputCls} value={f.address_form} onChange={set("address_form")} disabled={!canManage}><option value="du">{t("reception.script.informal")}</option><option value="De">{t("reception.script.formal")}</option></select>
        </div>
      </div>
      {field("greeting", t("reception.script.greeting"), t("reception.script.greetingHint"))}
      <div>
        <label htmlFor="rs-collect" className="block text-label-md font-semibold mb-1">{t("reception.script.collect")}</label>
        <textarea id="rs-collect" rows={4} className={`${inputCls} resize-y`} value={collectText} onChange={(e) => { setNote(null); setCollectText(e.target.value); }} disabled={!canManage} />
        <p className="mt-1 text-body-sm text-ink-soft">{t("reception.script.collectHint")}</p>
      </div>
      {field("escalation", t("reception.script.escalation"), t("reception.script.escalationHint"))}
      {field("avoid", t("reception.script.avoid"), t("reception.script.avoidHint"))}
      {field("closing", t("reception.script.closing"), t("reception.script.closingHint"), 1)}
      <ErrorBox error={save.error ?? suggest.error} />
      {canManage && (
        <div className="flex flex-wrap justify-end gap-2">
          {aiReady && <Button type="button" variant="ghost" icon="auto_awesome" disabled={suggest.pending} onClick={() => suggest.run()}>{t("reception.script.suggestAgain")}</Button>}
          <Button type="submit" icon="save" disabled={save.pending}>{save.pending ? t("common.saving") : t("reception.script.save")}</Button>
        </div>
      )}
    </form>
  );
}
