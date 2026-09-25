"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Textarea, inputCls, useSubmit } from "@/components/ui";

type Profile = Record<string, unknown>;

/** O01 basic parameters. Submitted by the sticky action bar via form="business-form". */
export function BusinessForm({ wsId, profile, canEdit }: { wsId: string; profile: Profile; canEdit: boolean }) {
  const router = useRouter();
  const [f, setF] = useState<Profile>(profile);
  const [saved, setSaved] = useState(false);
  // Adopt the server copy after a save/refresh (new version) without losing the "Gemt" notice.
  useEffect(() => { setF(profile); }, [profile.version]); // eslint-disable-line react-hooks/exhaustive-deps
  const FIELDS = ["legal_name", "description", "manual_setup", "website_url", "cvr", "phone", "postal_code", "city", "timezone"];
  const dirty = FIELDS.some((k) => (f[k] ?? "") !== (profile[k] ?? ""));
  const { run, pending, error } = useSubmit(async () => {
    await api(`/workspaces/${wsId}/profile`, { method: "PUT", body: JSON.stringify({ ...f, expected_version: profile.version, website_url: f.website_url || null }) });
    setSaved(true); router.refresh(); return true;
  });
  const s = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => { setSaved(false); setF({ ...f, [k]: e.target.value }); };
  const manual = Boolean(f.manual_setup);
  // The sticky bar's "Gem" and "Fortsæt" both submit this form; "Fortsæt" saves first, then moves on.
  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const next = ((e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null)?.value === "next";
    const ok = canEdit && dirty ? await run() : true;
    if (next && ok) router.push("/onboarding/goals");
  };
  return (
    <form id="business-form" onSubmit={onSubmit} className="space-y-space-lg">
      {!canEdit && <Alert kind="info">Din rolle (læser) kan se, men ikke redigere.</Alert>}
      <ErrorBox error={error} />
      {error?.code === "version_conflict" && <Button variant="secondary" type="button" onClick={() => router.refresh()}>Genindlæs</Button>}
      {saved && !dirty && <Alert kind="ok">Gemt.</Alert>}
      {dirty && <p role="status" className="font-label-sm text-label-sm text-on-surface-variant">Ugemte ændringer{pending ? " – gemmer…" : ""}</p>}
      <Field label="Virksomhedens officielle navn" hint="Dette navn bruges af assistenten over for kunderne." error={fieldError(error, "legal_name")}>
        <div className="relative">
          <Input required value={String(f.legal_name ?? "")} onChange={s("legal_name")} disabled={!canEdit} />
          {profile.legal_name ? <Icon name="verified" size={18} className="absolute right-3 top-2.5 text-secondary" /> : null}
        </div>
      </Field>
      <Field label="Kort virksomhedsbeskrivelse & speciale" hint="Bruges som grundkontekst for assistenten." error={fieldError(error, "description")}>
        <Textarea rows={3} className="resize-none" value={String(f.description ?? "")} onChange={s("description")} disabled={!canEdit} />
      </Field>
      <div className="p-space-md rounded-xl bg-surface-container-low flex items-start gap-space-md">
        <div className="p-2 rounded-lg bg-surface-container text-secondary mt-0.5"><Icon name={manual ? "public_off" : "public"} size={20} /></div>
        <div className="flex-1 space-y-2">
          <label className="flex items-center justify-between gap-space-sm cursor-pointer">
            <span className="font-label-md text-label-md text-primary font-bold">Manuel opsætning uden hjemmeside{manual ? " er aktiv" : ""}</span>
            <span className="relative inline-block w-10 flex-shrink-0">
              <input type="checkbox" role="switch" className="sr-only peer" checked={manual} disabled={!canEdit} onChange={(e) => { setSaved(false); setF({ ...f, manual_setup: e.target.checked }); }} />
              <span className="block h-5 rounded-full bg-outline-variant peer-checked:bg-primary peer-focus-visible:ring-2 peer-focus-visible:ring-secondary-container transition-colors" />
              <span className="absolute top-0.5 left-0.5 bg-on-primary w-4 h-4 rounded-full transition-transform peer-checked:translate-x-5" />
            </span>
          </label>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Der hentes intet automatisk fra en hjemmeside. Alle oplysninger, priser og svar kommer udelukkende fra den godkendte viden.</p>
          {!manual && (
            <Field label="Hjemmeside" hint="Automatisk indlæsning af hjemmesider er ikke bygget endnu – adressen gemmes kun." error={fieldError(error, "website_url")}>
              <Input placeholder="https://" value={String(f.website_url ?? "")} onChange={s("website_url")} disabled={!canEdit} />
            </Field>
          )}
        </div>
      </div>
      <div className="grid gap-space-md grid-cols-2">
        <Field label="CVR"><Input inputMode="numeric" value={String(f.cvr ?? "")} onChange={s("cvr")} disabled={!canEdit} /></Field>
        <Field label="Telefon"><Input type="tel" value={String(f.phone ?? "")} onChange={s("phone")} disabled={!canEdit} /></Field>
        <Field label="Postnummer"><Input inputMode="numeric" value={String(f.postal_code ?? "")} onChange={s("postal_code")} disabled={!canEdit} /></Field>
        <Field label="By"><Input value={String(f.city ?? "")} onChange={s("city")} disabled={!canEdit} /></Field>
        <div className="col-span-2"><Field label="Tidszone" error={fieldError(error, "timezone")}><Input value={String(f.timezone ?? "Europe/Copenhagen")} onChange={s("timezone")} disabled={!canEdit} /></Field></div>
      </div>
    </form>
  );
}

type Cat = { id: string; label: string; slug: string; is_custom: boolean; is_primary: boolean };

export function Categories({ wsId, categories, suggested, canEdit }: { wsId: string; categories: Cat[]; suggested: { slug: string; label: string }[]; canEdit: boolean }) {
  const router = useRouter();
  const [custom, setCustom] = useState("");
  const { run, pending, error } = useSubmit(async () => { if (custom.trim()) { await api(`/workspaces/${wsId}/categories`, { method: "POST", body: JSON.stringify({ label: custom.trim() }) }); setCustom(""); router.refresh(); } });
  const add = async (slug: string, label: string) => { await api(`/workspaces/${wsId}/categories`, { method: "POST", body: JSON.stringify({ slug, label, is_primary: categories.length === 0 }) }); router.refresh(); };
  const remove = async (id: string) => { await api(`/workspaces/${wsId}/categories/${id}`, { method: "DELETE" }); router.refresh(); };
  const has = new Set(categories.map((c) => c.slug));
  const q = custom.trim().toLowerCase();
  const matches = suggested.filter((s) => !has.has(s.slug) && (!q || s.label.toLowerCase().includes(q)));
  return (
    <div className="space-y-space-md">
      <ErrorBox error={error} />
      <ul className="flex flex-wrap gap-2">
        {categories.length === 0 && <li className="font-body-sm text-body-sm text-on-surface-variant">Ingen kategorier endnu – vælg mindst én.</li>}
        {categories.map((c) => {
          const cls = c.is_primary ? "bg-primary text-on-primary shadow-sm" : c.is_custom ? "bg-secondary-container text-on-secondary-container font-semibold" : "bg-surface-container text-primary";
          return (
            <li key={c.id} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-label-md text-label-md ${cls}`}>
              <Icon name={c.is_primary ? "star" : c.is_custom ? "handyman" : "layers"} size={16} className={c.is_primary ? "text-secondary-fixed" : "text-secondary"} />
              <span>{c.label}</span>
              {c.is_primary && <span className="text-[10px] bg-primary-container text-secondary-fixed px-1.5 rounded font-bold uppercase ml-1">Primær</span>}
              {c.is_custom && !c.is_primary && <span className="text-[10px] bg-secondary text-on-secondary px-1.5 rounded-full font-bold uppercase ml-1">Egen</span>}
              {canEdit && !c.is_primary && <button type="button" aria-label={`Fjern ${c.label}`} onClick={() => remove(c.id)} className="ml-0.5 text-on-surface-variant hover:text-error"><Icon name="close" size={16} /></button>}
            </li>
          );
        })}
      </ul>
      {canEdit && (
        <>
          <form onSubmit={(e) => { e.preventDefault(); run(); }} className="flex items-center gap-2 pt-1">
            <div className="relative flex-1">
              <Icon name="search" size={18} className="absolute left-3 top-2 text-on-surface-variant" />
              <input aria-label="Søg eller opret kategori" className={`${inputCls} pl-9 py-1.5 font-body-sm text-body-sm`} placeholder="Søg eller opret ny kategori…" value={custom} onChange={(e) => setCustom(e.target.value)} />
            </div>
            <button type="submit" disabled={pending || !custom.trim()} className="px-3 py-1.5 rounded-lg bg-surface-container text-primary font-label-sm text-label-sm font-semibold hover:bg-surface-container-highest transition-colors flex items-center gap-1 disabled:opacity-50"><Icon name="add" size={16} />Tilføj</button>
          </form>
          {matches.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {matches.slice(0, 8).map((s) => <button type="button" key={s.slug} onClick={() => add(s.slug, s.label)} className="px-2.5 py-1 rounded-lg bg-surface-container-low hover:bg-surface-container text-primary font-label-sm text-label-sm">+ {s.label}</button>)}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function ApproveButton({ wsId, versionId, label }: { wsId: string; versionId: string; label: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  return (
    <button disabled={pending} className="px-3 py-1 rounded bg-secondary-container hover:bg-secondary text-on-secondary-container hover:text-on-secondary font-label-sm text-label-sm font-bold transition-colors disabled:opacity-60"
      onClick={async () => { setPending(true); try { await api(`/workspaces/${wsId}/knowledge/versions/${versionId}/approve`, { method: "POST", headers: { "idempotency-key": `approve-${versionId}` } }); router.refresh(); } catch (e) { alert((e as { message: string }).message); } finally { setPending(false); } }}>
      {pending ? "Godkender…" : label}
    </button>
  );
}

export function SelfManagedButton({ wsId, goals }: { wsId: string; goals: Record<string, unknown> }) {
  const router = useRouter();
  const self = goals.guidance_mode === "self_managed";
  return (
    <button type="button" className="px-space-md py-2.5 rounded-lg bg-surface hover:bg-surface-container text-primary font-label-md text-label-md font-semibold flex items-center gap-2 transition-colors"
      onClick={async () => { await api(`/workspaces/${wsId}/goals`, { method: "PUT", body: JSON.stringify({ ...goals, guidance_mode: self ? "guided" : "self_managed", expected_version: goals.version }) }); router.refresh(); }}>
      <Icon name="alt_route" size={18} />{self ? "Skift til guidet opsætning" : "Skift til selvstyret opsætning"}
    </button>
  );
}
