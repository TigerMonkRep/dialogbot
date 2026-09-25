"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Badge, Button, ErrorBox, Field, Input, Textarea, useSubmit } from "@/components/ui";

type Profile = Record<string, unknown>;

export function BusinessForm({ wsId, profile, canEdit }: { wsId: string; profile: Profile; canEdit: boolean }) {
  const router = useRouter();
  const [f, setF] = useState<Profile>(profile);
  const [saved, setSaved] = useState(false);
  const dirty = JSON.stringify(f) !== JSON.stringify(profile);
  const { run, pending, error } = useSubmit(async () => {
    await api(`/workspaces/${wsId}/profile`, { method: "PUT", body: JSON.stringify({ ...f, expected_version: profile.version, website_url: f.website_url || null }) });
    setSaved(true); router.refresh();
  });
  const s = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => { setSaved(false); setF({ ...f, [k]: e.target.value }); };
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-4">
      {!canEdit && <Alert kind="info">Din rolle (læser) kan se, men ikke redigere.</Alert>}
      <ErrorBox error={error} />
      {error?.code === "version_conflict" && <Button variant="secondary" type="button" onClick={() => router.refresh()}>Genindlæs</Button>}
      {saved && <Alert kind="ok">Gemt.</Alert>}
      <Field label="Officielt navn" error={fieldError(error, "legal_name")}><Input required value={String(f.legal_name ?? "")} onChange={s("legal_name")} disabled={!canEdit} /></Field>
      <Field label="Kort beskrivelse og speciale" hint="Bruges som grundkontekst for assistenten" error={fieldError(error, "description")}><Textarea value={String(f.description ?? "")} onChange={s("description")} disabled={!canEdit} /></Field>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(f.manual_setup)} onChange={(e) => setF({ ...f, manual_setup: e.target.checked })} disabled={!canEdit} /> Manuel opsætning uden hjemmeside</label>
      <Field label="Hjemmeside (valgfri)" hint="Automatisk indlæsning af hjemmesider er ikke implementeret endnu" error={fieldError(error, "website_url")}><Input placeholder="https://" value={String(f.website_url ?? "")} onChange={s("website_url")} disabled={!canEdit} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="CVR (valgfri)"><Input value={String(f.cvr ?? "")} onChange={s("cvr")} disabled={!canEdit} /></Field>
        <Field label="Telefon (valgfri)"><Input value={String(f.phone ?? "")} onChange={s("phone")} disabled={!canEdit} /></Field>
        <Field label="Postnummer"><Input value={String(f.postal_code ?? "")} onChange={s("postal_code")} disabled={!canEdit} /></Field>
        <Field label="By"><Input value={String(f.city ?? "")} onChange={s("city")} disabled={!canEdit} /></Field>
        <Field label="Tidszone" error={fieldError(error, "timezone")}><Input value={String(f.timezone ?? "Europe/Copenhagen")} onChange={s("timezone")} disabled={!canEdit} /></Field>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={pending || !canEdit || !dirty}>{pending ? "Gemmer…" : "Gem"}</Button>
        {dirty && <span className="text-xs text-muted">Ugemte ændringer</span>}
        <Button type="button" variant="ghost" onClick={() => { if (!dirty || confirm("Du har ugemte ændringer. Fortsæt alligevel?")) router.push("/onboarding/goals"); }}>Fortsæt til mål →</Button>
      </div>
    </form>
  );
}

export function Categories({ wsId, categories, suggested, canEdit }: { wsId: string; categories: { id: string; label: string; slug: string; is_custom: boolean; is_primary: boolean }[]; suggested: { slug: string; label: string }[]; canEdit: boolean }) {
  const router = useRouter();
  const [custom, setCustom] = useState("");
  const { run, pending, error } = useSubmit(async () => { if (custom.trim()) { await api(`/workspaces/${wsId}/categories`, { method: "POST", body: JSON.stringify({ label: custom.trim() }) }); setCustom(""); router.refresh(); } });
  const add = async (slug: string, label: string) => { await api(`/workspaces/${wsId}/categories`, { method: "POST", body: JSON.stringify({ slug, label, is_primary: categories.length === 0 }) }); router.refresh(); };
  const remove = async (id: string) => { await api(`/workspaces/${wsId}/categories/${id}`, { method: "DELETE" }); router.refresh(); };
  const has = new Set(categories.map((c) => c.slug));
  return (
    <div className="space-y-4 text-sm">
      <ErrorBox error={error} />
      <ul className="flex flex-wrap gap-2">
        {categories.length === 0 && <li className="text-muted">Ingen kategorier endnu – vælg mindst én.</li>}
        {categories.map((c) => (
          <li key={c.id} className="flex items-center gap-2 rounded-full bg-accent px-3 py-1 font-semibold text-primary-dark">
            {c.label}{c.is_primary && <Badge status="approved" />}{c.is_custom && <span className="text-xs">(egen)</span>}
            {canEdit && <button aria-label={`Fjern ${c.label}`} onClick={() => remove(c.id)} className="ml-1 text-primary-dark/70 hover:text-danger">×</button>}
          </li>
        ))}
      </ul>
      {canEdit && (
        <>
          <p className="text-muted">Forslag:</p>
          <div className="flex flex-wrap gap-2">
            {suggested.filter((s) => !has.has(s.slug)).map((s) => <Button key={s.slug} variant="ghost" className="border border-line" onClick={() => add(s.slug, s.label)}>+ {s.label}</Button>)}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); run(); }} className="flex gap-2">
            <Input placeholder="Egen kategori, fx Poolservice" value={custom} onChange={(e) => setCustom(e.target.value)} />
            <Button type="submit" variant="secondary" disabled={pending || !custom.trim()}>Tilføj</Button>
          </form>
        </>
      )}
    </div>
  );
}
