"use client";
import { useEffect, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, useSubmit } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";

type Scope = { name: string; description: string; write: boolean };
type Key = { id: string; name: string; prefix: string; last4: string; scopes: string[]; status: string; created_at: string; expires_at: string | null; last_used_at: string | null; revoked_at: string | null };

/** «API-nøgler» (X22, F-M2-06-X22): what public-api.md points to – create a key with a name and scopes (the full key is
 *  shown once, right after creation), the list masked (prefix…last4) and revoke. Uses the internal management API
 *  /workspaces/{id}/api-keys (owner/admin). */
export function ApiKeys({ wsId }: { wsId: string }) {
  const t = useT("settings");
  const lang = HTML_LANG[useLocale()];
  const [scopes, setScopes] = useState<Scope[]>([]);
  const [items, setItems] = useState<Key[] | null>(null);
  const [loadErr, setLoadErr] = useState<ApiError | null>(null);
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [shown, setShown] = useState<{ name: string; key: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const base = `/workspaces/${wsId}/api-keys`;
  const load = () => Promise.all([api<Scope[]>(`${base}/scopes`), api<Key[]>(base)])
    .then(([s, k]) => { setScopes(s); setItems(k); setLoadErr(null); })
    .catch((e) => setLoadErr(e as ApiError));
  useEffect(() => { void load(); }, [wsId]); // eslint-disable-line react-hooks/exhaustive-deps

  const create = useSubmit(async () => {
    const r = await api<Key & { key: string | null }>(base, { method: "POST", body: JSON.stringify({ name: name.trim(), scopes: chosen }) });
    if (r.key) setShown({ name: r.name, key: r.key });
    setName(""); setChosen([]); setCopied(false);
    await load();
  });
  const revoke = useSubmit(async (k: Key) => {
    if (!window.confirm(t("apiKeys.revokeConfirm", { name: k.name }))) return;
    await api(`${base}/${k.id}`, { method: "DELETE" });
    await load();
  });
  const date = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(lang, { day: "numeric", month: "short", year: "numeric" }) : "–");
  const toggle = (s: string) => setChosen((c) => (c.includes(s) ? c.filter((x) => x !== s) : [...c, s]));

  return (
    <section aria-labelledby="api-keys-h" className="bg-paper rounded-2xl p-4 border-2 border-ink flex flex-col gap-3">
      <div>
        <h2 id="api-keys-h" className="font-display text-headline-sm text-ink">{t("apiKeys.title")}</h2>
        <p className="text-body-sm text-ink-soft max-w-3xl">{t("apiKeys.intro")}</p>
      </div>
      <ErrorBox error={loadErr} />
      {shown && (
        <div role="status" className="flex flex-col gap-2 rounded-xl border-2 border-ink bg-highlight px-4 py-3">
          <p className="m-0 text-[14px] font-semibold text-ink">{t("apiKeys.onceTitle", { name: shown.name })}</p>
          <code data-api-key className="block break-all rounded-lg bg-paper border-[1.5px] border-ink px-3 py-2 text-[13px]">{shown.key}</code>
          <p className="m-0 text-[13px] text-ink-soft">{t("apiKeys.onceNote")}</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" icon="content_copy" onClick={() => { void navigator.clipboard?.writeText(shown.key).then(() => setCopied(true)).catch(() => {}); }}>{copied ? t("apiKeys.copied") : t("apiKeys.copy")}</Button>
            <Button type="button" variant="outline" onClick={() => setShown(null)}>{t("apiKeys.saved")}</Button>
          </div>
        </div>
      )}
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); create.run(); }}>
        <Field label={t("apiKeys.name")}>
          <Input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder={t("apiKeys.namePlaceholder")} />
        </Field>
        <fieldset className="flex flex-col gap-1.5">
          <legend className="text-label-md font-semibold mb-1">{t("apiKeys.scopes")}</legend>
          {scopes.map((s) => (
            <label key={s.name} className="flex items-start gap-2 text-[14px] text-ink">
              <input type="checkbox" className="mt-1 w-4 h-4 accent-ink" checked={chosen.includes(s.name)} onChange={() => toggle(s.name)} />
              <span><code className="text-[13px] font-semibold">{s.name}</code>{s.write && <span className="ml-1 text-[12px] text-ink-soft">({t("apiKeys.write")})</span>} – <span className="text-ink-soft">{s.description}</span></span>
            </label>
          ))}
        </fieldset>
        <ErrorBox error={create.error} />
        <div><Button type="submit" icon="key" disabled={create.pending || !name.trim() || chosen.length === 0}>{create.pending ? t("apiKeys.creating") : t("apiKeys.create")}</Button></div>
      </form>
      <h3 className="font-display text-[17px] font-bold text-ink">{t("apiKeys.listTitle")}</h3>
      <ErrorBox error={revoke.error} />
      {items === null ? null : items.length === 0 ? <p className="text-[14px] text-ink-soft">{t("apiKeys.none")}</p> : (
        <ul className="flex flex-col">
          {items.map((k) => (
            <li key={k.id} data-api-key-row className="flex flex-wrap items-center gap-2 py-2.5 border-t-[1.5px] border-line text-[14px]">
              <span className="font-semibold text-ink">{k.name}</span>
              <code className="text-[13px] text-ink-soft">{k.prefix}…{k.last4}</code>
              <span className="text-[12px] text-ink-soft">{k.scopes.join(", ")}</span>
              <span className="text-[12px] text-ink-soft">{t("apiKeys.created", { date: date(k.created_at) })} · {k.last_used_at ? t("apiKeys.lastUsed", { date: date(k.last_used_at) }) : t("apiKeys.neverUsed")}</span>
              {k.revoked_at || k.status !== "active"
                ? <span className="ml-auto px-2.5 py-0.5 rounded-full bg-line text-[12px] font-semibold">{k.revoked_at ? t("apiKeys.revoked", { date: date(k.revoked_at) }) : t("apiKeys.expired")}</span>
                : <Button type="button" variant="outline" className="ml-auto" disabled={revoke.pending} onClick={() => revoke.run(k)}>{t("apiKeys.revoke")}</Button>}
            </li>
          ))}
        </ul>
      )}
      {items !== null && <Alert kind="info">{t("apiKeys.docs")}</Alert>}
    </section>
  );
}
