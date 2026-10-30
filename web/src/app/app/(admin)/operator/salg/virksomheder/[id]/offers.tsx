"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, Select, Tag, useSubmit } from "@/components/ui";
import type { ContactRow } from "./contacts";

type Message = { id: string; kind: string; channel: string; destination: string; status: string; error: string | null; requested_quote: string; created_at: string; sent_at: string | null };
export type Offer = {
  id: string; version: number; setup_kind: string; status: string; valid_until: string; terms_version: string;
  monthly_net_minor: number; monthly_vat_minor: number; setup_net_minor: number; sent_via: string | null; sent_to: string | null;
  sent_at: string | null; accepted_at: string | null; workspace_id: string | null; first_invoice_paid_at: string | null; messages: Message[];
};
export type Meeting = { id: string; status: string; starts_at: string | null; booking: { status: string; contact_name: string; contact_email: string | null; calendar: string | null } | null; calendar_confirmed: boolean; campaign_contact_id: string | null };

const STATUS: Record<string, string> = { draft: "Kladde", sent: "Sendt – ikke accepteret", accepted: "Accepteret", expired: "Udløbet", cancelled: "Annulleret" };
const MSG: Record<string, string> = { requested: "Venter", sent: "Sendt", failed: "Fejlet", cancelled: "Annulleret" };
const MEETING: Record<string, string> = { proposed: "Foreslået", confirmed: "Bekræftet", cancelled: "Aflyst", held: "Afholdt", no_show: "Udeblev" };
const kr = (minor: number) => `${(minor / 100).toLocaleString("da-DK", { maximumFractionDigits: 2 })} kr.`;
const dt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Copenhagen" }) : "–");

function SendForm({ offer, contacts, companyEmail, onDone }: { offer: Offer; contacts: ContactRow[]; companyEmail: string | null; onDone: () => void }) {
  const emails = [...new Set([...contacts.map((c) => c.email), companyEmail].filter((x): x is string => Boolean(x)))];
  const phones = [...new Set(contacts.map((c) => c.phone_e164).filter((x): x is string => Boolean(x)))];
  const [channel, setChannel] = useState<"email" | "sms">("email");
  const [dest, setDest] = useState(emails[0] ?? "");
  const send = useSubmit(async () => { await api(`/operator/salg/offers/${offer.id}/send`, { method: "POST", body: JSON.stringify({ channel, destination: dest }) }); onDone(); });
  const options = channel === "email" ? emails : phones;
  return (
    <form className="flex flex-wrap gap-2 items-end" onSubmit={(e) => { e.preventDefault(); send.run(); }}>
      <Field label="Kanal"><Select value={channel} onChange={(e) => { const c = e.target.value as "email" | "sms"; setChannel(c); setDest((c === "email" ? emails : phones)[0] ?? ""); }}><option value="email">E-mail</option><option value="sms">SMS</option></Select></Field>
      <Field label="Til" error={fieldError(send.error, "destination")} hint={options.length ? "Fra kontakten/virksomheden – eller skriv en adresse, du selv har bekræftet." : "Skriv en adresse, kunden selv har bekræftet."}>
        <Input list={`dest-${offer.id}`} value={dest} onChange={(e) => setDest(e.target.value)} />
        <datalist id={`dest-${offer.id}`}>{options.map((o) => <option key={o} value={o} />)}</datalist>
      </Field>
      <Button type="submit" variant="secondary" disabled={!dest.trim() || send.pending}>{send.pending ? "Sender…" : "Send link"}</Button>
      <ErrorBox error={send.error} />
    </form>
  );
}

export function OffersPanel({ companyId, offers, meetings, pending, contacts, companyEmail }: { companyId: string; offers: Offer[]; meetings: Meeting[]; pending: Message[]; contacts: ContactRow[]; companyEmail: string | null }) {
  const router = useRouter();
  const done = () => router.refresh();
  const run = useSubmit(async (path: string, body?: unknown) => { await api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }); router.refresh(); });
  return (
    <section className="rounded-2xl border-2 border-ink bg-paper p-space-md flex flex-col gap-3 min-w-0">
      <h2 className="font-display font-bold text-[18px]">Tilbud, ordre og møder</h2>
      <p className="text-[13px] text-muted">Beløbene kommer fra prislisten. Et sendt link er ikke en ordre – kunden accepterer selv på tilbudssiden og bliver først betalende kunde ved første betalte faktura.</p>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={run.pending} onClick={() => run.run(`/operator/salg/companies/${companyId}/offers`, { setup_kind: "diy" })}>Opret tilbud (gør-det-selv)</Button>
        <Button variant="secondary" disabled={run.pending} onClick={() => run.run(`/operator/salg/companies/${companyId}/offers`, { setup_kind: "specialist" })}>Opret tilbud (specialist)</Button>
      </div>
      <ErrorBox error={run.error} />
      {pending.length > 0 && (
        <Alert kind="warn">
          <p className="font-semibold">Links kunden bad om – adressen er ikke bekræftet</p>
          <ul className="flex flex-col gap-1">{pending.map((m) => (
            <li key={m.id} className="flex flex-wrap gap-2 items-center">{m.channel === "email" ? "E-mail" : "SMS"} til <strong>{m.destination}</strong> ({dt(m.created_at)})
              <Button variant="secondary" disabled={run.pending} onClick={() => run.run(`/operator/salg/messages/${m.id}/send`)}>Adressen er rigtig – send</Button></li>))}</ul>
        </Alert>
      )}
      {offers.length === 0 ? <p className="text-muted text-[14px]">Intet tilbud endnu.</p> : (
        <ul className="flex flex-col gap-2">{offers.map((o) => (
          <li key={o.id} className="rounded-xl border border-line p-3 text-[14px] flex flex-col gap-2">
            <div className="flex flex-wrap gap-2 items-center"><strong>Tilbud v{o.version}</strong><Tag tone={o.status === "accepted" ? "tertiary" : o.status === "sent" ? "neutral" : "secondary"}>{STATUS[o.status] ?? o.status}</Tag>
              {o.first_invoice_paid_at && <Tag tone="tertiary">Betalende kunde</Tag>}</div>
            <p>{kr(o.monthly_net_minor)}/md. ekskl. moms ({kr(o.monthly_net_minor + o.monthly_vat_minor)} inkl.) · {o.setup_kind === "specialist" ? `specialist-opsætning ${kr(o.setup_net_minor)}` : "gør-det-selv"} · gælder til {dt(o.valid_until)} · vilkår {o.terms_version}</p>
            {o.sent_at && <p className="text-muted">Sendt {dt(o.sent_at)} via {o.sent_via === "sms" ? "SMS" : "e-mail"} til {o.sent_to}</p>}
            {o.accepted_at && <p>Accepteret {dt(o.accepted_at)}{o.workspace_id && <> · <Link className="underline" href={`/app/operator/admin/kunder/${o.workspace_id}`}>Kundens arbejdsrum</Link></>}</p>}
            {o.messages.length > 0 && <ul className="text-[13px] text-muted">{o.messages.map((m) => <li key={m.id}>{MSG[m.status] ?? m.status}: {m.channel === "email" ? "e-mail" : "SMS"} til {m.destination} · {dt(m.sent_at ?? m.created_at)}{m.error ? ` – ${m.error}` : ""}</li>)}</ul>}
            {(o.status === "draft" || o.status === "sent") && <>
              <SendForm offer={o} contacts={contacts} companyEmail={companyEmail} onDone={done} />
              <div><Button variant="secondary" disabled={run.pending} onClick={() => run.run(`/operator/salg/offers/${o.id}/cancel`)}>Annullér tilbud</Button></div>
            </>}
          </li>))}</ul>
      )}
      <h3 className="font-semibold mt-2">Intro-møder</h3>
      {meetings.length === 0 ? <p className="text-muted text-[14px]">Ingen. Peter booker et møde på bookingtypen &quot;Intro-møde&quot; i salgsarbejdsrummet, når kunden siger ja til en tid.</p> : (
        <ul className="flex flex-col gap-2">{meetings.map((m) => (
          <li key={m.id} className="flex flex-wrap gap-2 items-center text-[14px]">
            <Tag tone={m.status === "confirmed" ? "tertiary" : "secondary"}>{MEETING[m.status] ?? m.status}</Tag>
            <span>{dt(m.starts_at)}{m.booking ? ` · ${m.booking.contact_name}${m.booking.contact_email ? ` (${m.booking.contact_email})` : ""}` : ""}{m.calendar_confirmed ? " · i kalenderen" : ""}</span>
            {m.campaign_contact_id && <Link className="underline text-[13px]" href={`/app/operator/salg/opkald/${m.campaign_contact_id}`}>Opkaldet</Link>}
            {m.status === "confirmed" && <>
              <Button variant="secondary" disabled={run.pending} onClick={() => run.run(`/operator/salg/meetings/${m.id}`, { status: "held" })}>Afholdt</Button>
              <Button variant="secondary" disabled={run.pending} onClick={() => run.run(`/operator/salg/meetings/${m.id}`, { status: "no_show" })}>Udeblev</Button>
              <Button variant="secondary" disabled={run.pending} onClick={() => run.run(`/operator/salg/meetings/${m.id}`, { status: "cancelled" })}>Aflys</Button>
            </>}
          </li>))}</ul>
      )}
    </section>
  );
}
