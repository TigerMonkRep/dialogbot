"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button, ErrorBox, Field, Input } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import { dataExport, dataExportHref, deleteAccount, requestDataExport, type DataExport } from "@/lib/privat/account-api";
import { LINK } from "./bits";
import { usePrivat } from "./store";

/** Konto → «Dine data»: export (worker → e-mail link → ?eksport=<token> here) and «Slet min konto» with the e-mail
 *  typed again. No orange button: the screen's one primary action is elsewhere; delete is the danger variant. */
export function MyDataSection() {
  const t = useT("privat");
  const { mode, session } = usePrivat();
  const params = useSearchParams();
  const token = params.get("eksport");
  const [exp, setExp] = useState<DataExport | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [email, setEmail] = useState("");
  useEffect(() => { if (mode === "real") dataExport().then(setExp).catch(() => setExp(null)); }, [mode]);
  if (mode !== "real") return null;
  const ask = async () => {
    setBusy(true); setError(null);
    try { setExp(await requestDataExport()); } catch (e) { setError(e as ApiError); } finally { setBusy(false); }
  };
  const remove = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      await deleteAccount(email.trim());
      await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } }).catch(() => {});
      window.location.assign("/privat");
    } catch (x) { setError(x as ApiError); setBusy(false); }
  };
  const queued = exp?.status === "queued";
  return (
    <section className="rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5" aria-labelledby="mydata-h" data-testid="my-data">
      <h3 id="mydata-h" className="m-0 font-display font-bold text-[19px]">{t("myData.title")}</h3>
      {token ? (
        exp?.status === "ready"
          ? <><p className="m-0 text-[15px] font-semibold">{t("myData.ready")}</p>
            <a href={dataExportHref(token)} className={LINK} download data-testid="export-download">{t("myData.download")}</a></>
          : <p className="m-0 text-[15px]">{t("myData.expired")}</p>
      ) : <p className="m-0 text-[14px] text-ink-soft">{queued ? t("myData.queued") : t("myData.exportText")}</p>}
      {!queued && <Button variant="outline" className="self-start border-2 rounded-full" icon="download" onClick={ask} disabled={busy}>{t("myData.export")}</Button>}
      {!confirming ? (
        <button type="button" className={`${LINK} text-danger hover:text-danger`} onClick={() => setConfirming(true)}>{t("myData.delete")}</button>
      ) : (
        <form onSubmit={remove} className="flex flex-col gap-2.5 border-t-[1.5px] border-line pt-3" data-testid="delete-account">
          <p className="m-0 text-[15px]">{t("myData.deleteText")}</p>
          <Field label={t("myData.deleteLabel")}>
            <Input type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={session.email ?? ""} />
          </Field>
          <div className="flex gap-2 flex-wrap">
            <Button type="submit" variant="danger" disabled={busy || email.trim().toLowerCase() !== (session.email ?? "").toLowerCase()}>{busy ? t("myData.deleting") : t("myData.deleteConfirm")}</Button>
            <Button type="button" variant="ghost" onClick={() => { setConfirming(false); setEmail(""); }}>{t("myData.cancel")}</Button>
          </div>
        </form>
      )}
      <ErrorBox error={error} />
    </section>
  );
}
