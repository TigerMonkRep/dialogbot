"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { Group, GroupJoinLink, SuggestedPerson } from "@/lib/privat/api";
import { bareLink, contactPickerAvailable, normalizeDk, parseNumbers, pickContacts, platformOf, prettyPhone, smsHref, whatsappHref, type Platform } from "@/lib/privat/sms";
import { parseVcf, type VContact } from "@/lib/privat/vcard";
import { Bag } from "@/components/lego";
import { Avatars, BIG, CHIP, Eyebrow, LINK, Pill } from "./bits";
import { Ico } from "./icons";
import { usePrivat } from "./store";

type Draft = { key: string; id?: string; name: string; phone: string | null; user_id?: string | null; dialogbot?: boolean };
const field = "w-full min-w-0 min-h-[48px] rounded-[14px] border-2 border-ink px-3.5 text-[16px] bg-paper text-ink placeholder:text-muted";

/** «Mine folk»: saved groups to share with in one go. Numbers are only used when the user shares from their own phone. */
export function PeoplePage() {
  const t = useT("privat");
  const { groups, mode } = usePrivat();
  const [editing, setEditing] = useState<Group | "new" | null>(null);
  if (editing) return <GroupEditor group={editing === "new" ? null : editing} onDone={() => setEditing(null)} />;
  return (
    <div className="px-4 pt-5 pb-7 flex flex-col gap-4" aria-label={t("people.title")}>
      <h2 className="m-0 font-display font-extrabold text-[28px] tracking-[-0.5px]">{t("people.title")}</h2>
      <p className="m-0 text-[15px] text-ink-soft">{t("people.lead")}</p>
      {groups.length === 0 && mode !== "loading" && <p className="m-0 text-[14px] text-muted">{t("people.empty")}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-1 gap-3">
        {groups.map((g) => (
          <button key={g.id} type="button" onClick={() => setEditing(g)} className="rounded-[18px] border-2 border-ink bg-paper p-4 flex items-center gap-3 text-left hover:bg-panel">
            <span className="flex-1 min-w-0 flex flex-col gap-2">
              <span className="font-display font-bold text-[19px] [overflow-wrap:anywhere]">{t("people.groupCard", { name: g.name, n: g.members.length })}</span>
              <Avatars names={g.members.map((m) => m.name)} size={30} />
            </span>
            <Ico name="chevron" size={20} />
          </button>
        ))}
      </div>
      <Button className={`${BIG} self-start`} onClick={() => setEditing("new")} disabled={mode === "demo"}><Ico name="plus" size={18} />{t("people.new")}</Button>
      <p className="m-0 text-[13px] text-muted">{t("people.privacy")}</p>
    </div>
  );
}

function GroupEditor({ group: initial, onDone }: { group: Group | null; onDone: () => void }) {
  const t = useT("privat");
  const { api, run, groups, refresh } = usePrivat();
  const [savedId, setSavedId] = useState<string | null>(initial?.id ?? null);
  const group = groups.find((g) => g.id === savedId) ?? initial;
  const [platform, setPlatform] = useState<Platform>("other");
  const [removed, setRemoved] = useState<string[]>([]);
  const [name, setName] = useState(group?.name ?? "");
  const [list, setList] = useState<Draft[]>(() => (group?.members ?? []).map((m) => ({ key: m.id, id: m.id, name: m.name, phone: m.phone_e164, user_id: m.user_id, dialogbot: m.has_dialogbot })));
  const [suggested, setSuggested] = useState<SuggestedPerson[]>([]);
  const [picker, setPicker] = useState(false);
  const [one, setOne] = useState({ name: "", phone: "" });
  const [oneErr, setOneErr] = useState<string | null>(null);
  const [paste, setPaste] = useState("");
  const parsed = parseNumbers(paste);
  useEffect(() => {
    api.suggestedPeople().then(setSuggested).catch(() => setSuggested([]));
    const pf = platformOf(navigator.userAgent);
    setPlatform(pf);
    setPicker(contactPickerAvailable() && pf !== "ios");
  }, [api]);
  // People who join through the group link show up while the page is open (the store polls; this merges them in).
  useEffect(() => {
    if (!group) return;
    setList((cur) => [...cur, ...group.members.filter((m) => !cur.some((d) => d.id === m.id) && !removed.includes(m.id))
      .map((m) => ({ key: m.id, id: m.id, name: m.name, phone: m.phone_e164, user_id: m.user_id, dialogbot: m.has_dialogbot }))]);
  }, [group, removed]);
  useEffect(() => {
    if (!savedId) return;
    const id = setInterval(() => { if (document.visibilityState === "visible") refresh().catch(() => {}); }, 5000);
    return () => clearInterval(id);
  }, [savedId, refresh]);
  const has = (d: Pick<Draft, "phone" | "user_id" | "name">) => list.some((x) => (d.user_id && x.user_id === d.user_id) || (d.phone && x.phone === d.phone));
  const add = (ds: Omit<Draft, "key">[]) => setList((cur) => [...cur, ...ds.filter((d) => !cur.some((x) => (d.user_id && x.user_id === d.user_id) || (d.phone && x.phone === d.phone))).map((d, i) => ({ ...d, key: `n${Date.now()}${i}` }))]);
  const addOne = (e: React.FormEvent) => {
    e.preventDefault();
    const p = normalizeDk(one.phone);
    if (!p) { setOneErr(t("people.badNumber")); return; }
    setOneErr(null); add([{ name: one.name.trim() || prettyPhone(p), phone: p }]); setOne({ name: "", phone: "" });
  };
  const fromContacts = async () => {
    try { const tels = await pickContacts(); add(tels.map((x) => normalizeDk(x)).filter((x): x is string => !!x).map((p) => ({ name: prettyPhone(p), phone: p }))); } catch { /* cancelled */ }
  };
  const save = async () => {
    const newcomers = list.filter((d) => !d.id).map((d) => ({ name: d.name, phone: d.phone, user_id: d.user_id ?? null }));
    if (!group) { const r = await run((a) => a.createGroup({ name, members: newcomers })); if (r) onDone(); return; }
    // (an existing group: rename, remove, add)
    const removed = group.members.filter((m) => !list.some((d) => d.id === m.id));
    const ok = await run(async (a) => {
      if (name.trim() && name !== group.name) await a.updateGroup(group.id, { name });
      for (const m of removed) await a.removeGroupMember(group.id, m.id);
      if (newcomers.length) await a.addGroupMembers(group.id, newcomers);
      return true;
    });
    if (ok) onDone();
  };
  const ensureSaved = async (): Promise<string | null> => {
    if (group) return group.id;
    const g = await run((a) => a.createGroup({ name, members: list.map((d) => ({ name: d.name, phone: d.phone, user_id: d.user_id ?? null })) }));
    if (!g) return null;
    setSavedId(g.id);
    setList(g.members.map((m) => ({ key: m.id, id: m.id, name: m.name, phone: m.phone_e164, user_id: m.user_id, dialogbot: m.has_dialogbot })));
    return g.id;
  };
  const blocks: Record<string, React.ReactNode> = {
    suggested: <>{suggested.length > 0 && (
        <section className="flex flex-col gap-2 rounded-[18px] border-2 border-ink p-4">
          <h3 className="m-0 font-body text-[15px] font-semibold">{t("people.suggested")}</h3>
          <div className="flex flex-wrap gap-2">
            {suggested.map((p) => (
              <button key={p.user_id ?? p.name} type="button" className={CHIP} disabled={has({ name: p.name, phone: p.phone_e164 ?? null, user_id: p.user_id })}
                onClick={() => add([{ name: p.name, phone: p.phone_e164 ?? null, user_id: p.user_id ?? null, dialogbot: p.has_dialogbot }])}>
                <Ico name="plus" size={16} />{p.name}{p.has_dialogbot && <Pill tone="ok">Dialogbot</Pill>}
              </button>
            ))}
          </div>
        </section>
      )}</>,
    contacts: <>{picker && (
        <section className="flex flex-col gap-1.5">
          <Button variant="outline" className="border-2 self-start" onClick={fromContacts}><Ico name="users" size={18} />{t("share.contacts")}</Button>
          <p className="m-0 text-[12px] text-muted">{t("share.contactsLocal")}</p>
        </section>
      )}</>,
    type: <><form onSubmit={addOne} className="flex flex-col gap-2 rounded-[18px] border-2 border-ink p-4">
        <h3 className="m-0 font-body text-[15px] font-semibold">{t("people.typeOne")}</h3>
        <div className="flex flex-col sm:flex-row gap-2">
          <input aria-label={t("people.personName")} className={field} value={one.name} onChange={(e) => setOne({ ...one, name: e.target.value })} placeholder={t("people.personName")} autoComplete="off" />
          <input aria-label={t("phone.label")} type="tel" inputMode="tel" className={field} value={one.phone} onChange={(e) => setOne({ ...one, phone: e.target.value })} placeholder="12 34 56 78" />
        </div>
        {oneErr && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{oneErr}</p>}
        <Button type="submit" variant="outline" className="border-2 self-start">{t("people.addPerson")}</Button>
      </form></>,
    paste: <><section className="flex flex-col gap-2 rounded-[18px] border-2 border-ink p-4">
        <label htmlFor="paste-numbers" className="font-semibold text-[15px]">{t("people.paste")}</label>
        <textarea id="paste-numbers" rows={3} className="w-full rounded-[14px] border-2 border-ink p-3 text-[16px]" value={paste} onChange={(e) => setPaste(e.target.value)} placeholder={t("people.pastePlaceholder")} />
        {parsed.ok.length > 0 && (
          <div className="flex flex-wrap gap-1.5" aria-label={t("people.pastePreview")}>
            {parsed.ok.map((p) => <span key={p} className="inline-flex items-center min-h-8 px-2.5 rounded-full bg-panel border-[1.5px] border-ink text-[13px] font-semibold">{prettyPhone(p)}</span>)}
          </div>
        )}
        {parsed.bad.length > 0 && <p className="m-0 text-[13px] text-danger">{t("people.pasteBad", { list: parsed.bad.join(", ") })}</p>}
        <Button variant="outline" className="border-2 self-start" disabled={!parsed.ok.length}
          onClick={() => { add(parsed.ok.map((p) => ({ name: prettyPhone(p), phone: p }))); setPaste(""); }}>{t("people.addNumbers", { n: parsed.ok.length })}</Button>
      </section></>,
    link: <JoinLinkBlock groupId={group?.id ?? null} canCreate={!!name.trim()} ensureSaved={ensureSaved} platform={platform} />,
    vcf: <VcfImport onAdd={(cs) => add(cs.map((c) => ({ name: c.name, phone: normalizeDk(c.phone) ?? c.phone })))} />,
  };
  const order = platform === "android"
    ? ["contacts", "link", "suggested", "paste", "type"]
    : ["link", "vcf", "suggested", "paste", "type"];
  return (
    <div className="px-4 pt-4 pb-7 flex flex-col gap-4" aria-label={t("people.editTitle")}>
      <button type="button" className={LINK} onClick={onDone}>{t("people.back")}</button>
      <h2 className="m-0 font-display font-extrabold text-[26px] tracking-[-0.4px]">{group ? t("people.editTitle") : t("people.new")}</h2>
      <label className="flex flex-col gap-1.5 text-[14px] font-semibold">{t("people.name")}
        <input className={`${field} font-normal`} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("people.namePlaceholder")} />
      </label>

      <section className="flex flex-col gap-2" aria-label={t("people.members")}>
        <Eyebrow>{t("people.members")} ({list.length})</Eyebrow>
        {list.length === 0 && <p className="m-0 text-[14px] text-muted">{t("people.noMembers")}</p>}
        <ul className="m-0 p-0 list-none flex flex-wrap gap-2" data-testid="group-members">
          {list.map((d) => (
            <li key={d.key} className="inline-flex items-center gap-1.5 min-h-[40px] pl-1.5 pr-1 rounded-full border-[1.5px] border-ink bg-paper text-[14px]">
              <Avatars names={[d.name]} size={26} /><span className="max-w-[160px] truncate">{d.name}</span>
              {d.dialogbot && <span className="text-[11px] text-success font-semibold">{t("people.hasDialogbot")}</span>}
              <button type="button" aria-label={t("people.removeAria", { name: d.name })} onClick={() => { setList(list.filter((x) => x.key !== d.key)); if (d.id) setRemoved([...removed, d.id]); }} className="w-8 h-8 inline-flex items-center justify-center rounded-full hover:bg-panel"><Ico name="close" size={14} /></button>
            </li>
          ))}
        </ul>
      </section>

      <h3 className="m-0 font-display font-bold text-[20px]">{t("people.addTitle")}</h3>
      {order.map((k) => <div key={k} data-block={k}>{blocks[k]}</div>)}
      <p className="m-0 text-[13px] text-muted">{t("people.privacy")}</p>
      <div className="flex gap-2 flex-wrap">
        <Button className={BIG} onClick={save} disabled={!name.trim() || list.length === 0}>{t("people.save")}</Button>
        {group && <Button variant="outline" className="border-2 border-danger text-danger" onClick={async () => { await run((a) => a.deleteGroup(group.id)); onDone(); }}>{t("people.delete")}</Button>}
      </div>
    </div>
  );
}

/** «Lad dem melde sig selv»: ONE link the user drops into an existing group chat from their own phone. */
function JoinLinkBlock({ groupId, canCreate, ensureSaved, platform }: { groupId: string | null; canCreate: boolean; ensureSaved: () => Promise<string | null>; platform: Platform }) {
  const t = useT("privat");
  const { api, run } = usePrivat();
  const [link, setLink] = useState<GroupJoinLink | null>(null);
  const [copied, setCopied] = useState(false);
  const make = async () => {
    const id = await ensureSaved();
    if (!id) return;
    const r = await run((a) => a.groupJoinLink(id));
    if (r) setLink(r);
  };
  const btn = "inline-flex items-center justify-center gap-2 rounded-xl font-semibold";
  return (
    <section className="flex flex-col gap-2.5 rounded-[18px] border-2 border-ink p-4 bg-panel" data-testid="join-link">
      <h4 className="m-0 font-display font-bold text-[18px]">{t("people.selfTitle")}</h4>
      <p className="m-0 text-[14px] text-ink-soft">{t("people.selfText")}</p>
      {!link ? (
        <Button className={BIG} onClick={make} disabled={!canCreate}>{groupId ? t("people.selfMake") : t("people.selfSaveMake")}</Button>
      ) : (
        <>
          <p className="m-0 text-[14px] [overflow-wrap:anywhere] rounded-xl bg-paper border-[1.5px] border-ink p-3">«{link.suggested_text}»</p>
          <a href={smsHref(link.suggested_text, [], platform)} className={`${btn} ${BIG} bg-accent text-white hover:bg-accent-deep`}><Ico name="send" size={18} />{t("people.selfSend")}</a>
          <div className="grid grid-cols-2 gap-2">
            <a href={whatsappHref(link.suggested_text)} target="_blank" rel="noopener noreferrer" className={`${btn} min-h-[44px] border-2 border-ink bg-paper text-[15px] hover:bg-panel`}>{t("share.whatsapp")}</a>
            <Button variant="outline" className="border-2" onClick={async () => {
              if (typeof navigator.share === "function") { try { await navigator.share({ text: link.suggested_text }); } catch { /* cancelled */ } return; }
              try { await navigator.clipboard.writeText(link.short_url); setCopied(true); } catch { /* ignore */ }
            }}>{copied ? t("share.copied") : t("share.other")}</Button>
          </div>
          <p className="m-0 text-[13px] font-semibold flex items-center gap-2" data-testid="join-url"><Ico name="link" size={16} />{bareLink(link.short_url)}</p>
          <p className="m-0 text-[12px] text-muted" role="status">{t("people.selfWatching")}</p>
          <button type="button" className={LINK} onClick={async () => { if (groupId) { await api.revokeGroupJoinLink(groupId); setLink(null); } }}>{t("people.selfStop")}</button>
        </>
      )}
    </section>
  );
}

const GUIDE = ["people.vcfStep1", "people.vcfStep2", "people.vcfStep3"];

/** «Importér fra iPhone (.vcf)»: read in the browser, pick people, only those are sent. The file is never uploaded. */
function VcfImport({ onAdd }: { onAdd: (cs: VContact[]) => void }) {
  const t = useT("privat");
  const [contacts, setContacts] = useState<VContact[] | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const read = async (f: File | undefined) => {
    setErr(null);
    if (!f) return;
    if (f.size > 5_000_000) { setErr(t("people.vcfTooBig")); return; }
    const cs = parseVcf(await f.text());
    if (!cs.length) { setErr(t("people.vcfEmpty")); return; }
    setContacts(cs); setPicked(new Set());
  };
  return (
    <section className="flex flex-col gap-2.5 rounded-[18px] border-2 border-ink p-4" data-testid="vcf-import">
      <h4 className="m-0 font-display font-bold text-[18px]">{t("people.vcfTitle")}</h4>
      <ol className="m-0 p-0 list-none flex flex-col gap-2">
        {GUIDE.map((k, i) => (
          <li key={k} className="flex items-start gap-3"><Bag n={i + 1} size={32} /><span className="text-[14px] pt-1.5">{t(k)}</span></li>
        ))}
      </ol>
      <p className="m-0 text-[13px] text-muted">{t("people.vcfSingle")}</p>
      <label className="inline-flex items-center justify-center gap-2 self-start min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper font-semibold text-[15px] hover:bg-panel cursor-pointer focus-within:outline focus-within:outline-[3px] focus-within:outline-accent">
        <Ico name="package" size={18} />{t("people.vcfChoose")}
        <input type="file" accept=".vcf,text/vcard,text/x-vcard" className="sr-only" onChange={(e) => read(e.target.files?.[0])} data-testid="vcf-input" />
      </label>
      <p className="m-0 text-[12px] text-muted">{t("people.vcfLocal")}</p>
      {err && <p role="alert" className="m-0 text-[14px] text-danger font-semibold">{err}</p>}
      {contacts && (
        <fieldset className="m-0 p-0 border-0 flex flex-col gap-1">
          <legend className="text-[14px] font-semibold mb-1">{t("people.vcfPick", { n: contacts.length })}</legend>
          {contacts.map((c, i) => (
            <label key={i} className="flex items-center gap-3 min-h-[44px] rounded-lg px-1 hover:bg-panel cursor-pointer">
              <input type="checkbox" className="w-5 h-5 accent-[var(--color-accent)]" checked={picked.has(i)}
                onChange={() => { const n = new Set(picked); if (n.has(i)) n.delete(i); else n.add(i); setPicked(n); }} />
              <span className="flex-1 min-w-0 flex flex-col"><span className="text-[15px] font-semibold [overflow-wrap:anywhere]">{c.name}</span><span className="text-[13px] text-muted">{prettyPhone(normalizeDk(c.phone) ?? c.phone)}</span></span>
            </label>
          ))}
          <Button variant="outline" className="border-2 self-start mt-1" disabled={!picked.size}
            onClick={() => { onAdd(contacts.filter((_, i) => picked.has(i))); setContacts(null); setPicked(new Set()); }}>{t("people.vcfAdd", { n: picked.size })}</Button>
        </fieldset>
      )}
    </section>
  );
}
