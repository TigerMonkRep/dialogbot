"use client";
import { useEffect, useId, useRef, useState } from "react";
import { useT } from "@/i18n/client";
import { Ico } from "@/components/privat/icons";
import { inputCls } from "@/components/ui";
import type { Place } from "@/lib/funnel/api";
import { useFunnel } from "./provider";

/** «Hvad hedder virksomheden?» – a text field with suggestions from GET /funnel/places?q=&industry= (Google Places
 *  through the backend). Picking a suggestion fills the name and keeps the place_id; typing a name nobody finds is
 *  fine too (place = null). The results carry Google's attribution line. */
export function PlaceSearch({ value, place, industry, onChange, labelledBy = "funnel-q" }: {
  value: string; place: Place | null; industry?: string | null; labelledBy?: string;
  onChange: (name: string, place: Place | null) => void;
}) {
  const t = useT("site.funnel.places");
  const { api } = useFunnel();
  const id = useId();
  const [items, setItems] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [active, setActive] = useState(-1);
  const seq = useRef(0);
  const q = value.trim();

  useEffect(() => {
    if (place || q.length < 2) { setItems([]); setSearching(false); return; }
    const n = ++seq.current;
    setSearching(true);
    const h = window.setTimeout(async () => {
      try { const r = await api.places(q, industry); if (seq.current === n) { setItems(r); setOpen(true); } }
      catch { if (seq.current === n) setItems([]); }
      finally { if (seq.current === n) setSearching(false); }
    }, 300);
    return () => window.clearTimeout(h);
  }, [q, industry, place, api]);

  const pick = (p: Place) => { onChange(p.name, p); setItems([]); setOpen(false); setActive(-1); };
  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || items.length === 0) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(-1, a - 1)); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(items[active]); }
    else if (e.key === "Escape") setOpen(false);
  };
  const listId = `${id}-list`;
  return (
    <div className="flex flex-col gap-2 relative">
      <label htmlFor={id} className="text-[13px] font-semibold text-ink">{t("label")}</label>
      <div className="relative">
        <input id={id} type="text" value={value} autoComplete="organization" autoFocus enterKeyHint="next" aria-labelledby={labelledBy}
          role="combobox" aria-expanded={open && items.length > 0} aria-controls={listId} aria-autocomplete="list" aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          placeholder={t("placeholder")} onKeyDown={onKey} onFocus={() => items.length && setOpen(true)} onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onChange={(e) => { onChange(e.target.value, null); setActive(-1); }}
          className={`${inputCls} min-h-[52px] text-[17px] pr-11`} />
        {place && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-success" aria-hidden><Ico name="check" size={22} stroke={3} /></span>}
      </div>
      {place && <p className="m-0 text-[14px] text-ink-soft" data-place>{[place.address, place.phone_display].filter(Boolean).join(" · ")}</p>}
      {!place && q.length >= 2 && (searching || open) && (
        <div className="rounded-2xl border-2 border-ink bg-white overflow-hidden" aria-live="polite">
          {searching && items.length === 0 && <p className="m-0 px-4 py-3 text-[14px] text-muted">{t("searching")}</p>}
          {!searching && items.length === 0 && <p className="m-0 px-4 py-3 text-[14px] text-muted">{t("none")}</p>}
          {items.length > 0 && (
            <ul id={listId} role="listbox" className="m-0 p-0 list-none max-h-[300px] overflow-y-auto">
              {items.map((p, i) => (
                <li key={p.place_id} id={`${listId}-${i}`} role="option" aria-selected={i === active}>
                  <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(p)}
                    className={`w-full min-h-[52px] px-4 py-2 text-left flex flex-col cursor-pointer border-0 ${i === active ? "bg-panel" : "bg-white hover:bg-panel"}`}>
                    <span className="font-semibold text-[15px] text-ink">{p.name}</span>
                    <span className="text-[13px] text-muted">{p.address}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {items.length > 0 && <p className="m-0 px-4 py-1.5 text-[11px] text-muted border-t border-line">{t("google")}</p>}
        </div>
      )}
    </div>
  );
}
