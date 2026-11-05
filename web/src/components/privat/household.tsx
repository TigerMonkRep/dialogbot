"use client";
/** One panel for the household apps (Abonnementer, Håndværker & tilbud, Fælles udgifter, Garanti & kvitteringer,
 *  Fest & invitationer, Flytning, Kæledyr, Hus & vedligehold, Fitness & sundhed): the app's summary, its items with
 *  «Fjern», «Kopiér» for texts meant to be sent on, and – only when configured – one partner link marked «Annonce».
 *  Everything else is done in the chat. */
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import type { AppOverview } from "@/lib/privat/api";
import { Eyebrow } from "./bits";
import { usePrivat } from "./store";

export const HOUSEHOLD_APPS = new Set(["abonnementer", "haandvaerker", "faelles-udgifter", "garanti", "fest", "flytning",
  "kaeledyr", "hus-og-vedligehold", "fitness-og-sundhed"]);

const CARD = "rounded-[16px] border-[1.5px] border-ink bg-paper p-3 flex flex-col gap-1.5";

export function HouseholdPanel({ appKey, name }: { appKey: string; name: string }) {
  const t = useT("privat");
  const { api } = usePrivat();
  const [data, setData] = useState<AppOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setData(await api.appOverview(appKey)); } catch (e) { setErr((e as ApiError).message); }
  }, [api, appKey]);
  useEffect(() => { void load(); }, [load]);
  const remove = async (id: string) => {
    setErr(null);
    try { await api.removeAppItem(appKey, id); await load(); } catch (e) { setErr((e as ApiError).message); }
  };
  const photo = async (id: string, f: File | undefined) => {
    if (!f) return;
    setErr(null);
    try { await api.uploadAppPhoto(appKey, id, await shrink(f)); await load(); } catch (e) { setErr((e as ApiError).message); }
  };
  const copy = async (id: string, text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(id); } catch { setErr(t("household.copyFailed")); }
  };
  return (
    <section className="flex flex-col gap-2" data-testid="household-panel">
      <Eyebrow>{name}</Eyebrow>
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      {data && <p className="m-0 text-[14px] text-ink-soft whitespace-pre-line">{data.summary}</p>}
      {data?.items.map((i) => (
        <div key={i.id} className={CARD}>
          <span className="font-semibold text-[15px] [overflow-wrap:anywhere]">{i.text}</span>
          {i.sub && <span className="text-[13px] text-ink-soft [overflow-wrap:anywhere]">{i.sub}</span>}
          <span className="flex gap-2 flex-wrap">
            {i.share_text && (
              <Button variant="outline" className="rounded-full border-2" onClick={() => void copy(i.id, i.share_text!)}>
                {copied === i.id ? t("household.copied") : t("household.copy")}
              </Button>
            )}
            {i.photo && (
              <label className="inline-flex items-center min-h-[44px] px-4 rounded-full border-2 border-ink text-[15px] font-semibold cursor-pointer">
                {i.photo_url ? t("household.photoReplace") : t("household.photoAdd")}
                <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => void photo(i.id, e.target.files?.[0])} />
              </label>
            )}
            {i.photo_url && <a href={i.photo_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center min-h-[44px] text-[14px] text-accent underline">{t("household.photoOpen")}</a>}
            <Button variant="outline" className="rounded-full border-2" onClick={() => void remove(i.id)}>{t("moreApps.remove")}</Button>
          </span>
        </div>
      ))}
      {data?.partner && (
        <a href={data.partner.url} target="_blank" rel="sponsored noopener noreferrer"
          className="rounded-[16px] border-[1.5px] border-dashed border-ink-soft p-3 flex flex-col gap-0.5 no-underline text-ink"
          data-testid="partner-link">
          <span className="text-[11px] uppercase tracking-wide text-muted">{t("household.ad")}</span>
          <span className="font-semibold text-[15px]">{data.partner.text}</span>
          <span className="text-[12px] text-muted">{data.partner.name} · {data.partner.note}</span>
        </a>
      )}
      <p className="m-0 text-[13px] text-muted">{t("household.hint")}</p>
    </section>
  );
}

/** A phone photo is often 4–8 MB: scale it to at most 1600 px as JPEG before upload (the web proxy takes ~4 MB).
 *  Formats the browser cannot draw (HEIC outside Safari) go up as they are. */
async function shrink(f: File): Promise<Blob> {
  try {
    const bmp = await createImageBitmap(f);
    const k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
    c.getContext("2d")?.drawImage(bmp, 0, 0, c.width, c.height);
    const out = await new Promise<Blob | null>((res) => c.toBlob(res, "image/jpeg", 0.85));
    return out ?? f;
  } catch {
    return f;
  }
}
