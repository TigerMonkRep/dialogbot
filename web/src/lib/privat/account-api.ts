"use client";
/** Konto → «Husstand» (Familie) and «Dine data» (export, delete). Real backend only: the in-browser simulation
 *  (fake.ts) has no household and no account to delete, so these are not part of PrivatApi. */
import { api } from "@/lib/client";

export type HouseholdMember = { id: string; name: string; is_me: boolean };
export type Household = {
  role: "owner" | "member" | null; active: boolean; can_invite: boolean; limit: number; count: number;
  owner_first_name: string | null; members: HouseholdMember[];
};
export type HouseholdInvite = { invite_url: string; short_url: string; short_code: string; token: string; suggested_text: string };
export type DataExport = { status: "queued" | "ready" | "expired" | "failed" | null; requested_at: string | null; expires_at: string | null };

const enc = encodeURIComponent;
const post = (body?: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body ?? {}) });

export const household = () => api<Household>("/privat/household");
export const householdInvite = () => api<HouseholdInvite>("/privat/household/invites", post());
export const householdRemove = (id: string) => api<void>(`/privat/household/members/${enc(id)}`, { method: "DELETE" });
export const householdLeave = () => api<void>("/privat/household/leave", post());

export const dataExport = () => api<DataExport>("/privat/data-export");
export const requestDataExport = () => api<DataExport>("/privat/data-export", post());
/** Same-origin download (the BFF adds the login); the token comes from the e-mail link (?eksport=). */
export const dataExportHref = (token: string) => `/api/backend/privat/data-export/download?token=${enc(token)}`;
export const deleteAccount = (confirm_email: string) =>
  api<{ deleted: boolean; login_kept: boolean }>("/privat/account/delete", post({ confirm_email }));
