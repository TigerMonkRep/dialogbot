import type { Import, ReviewNote } from "@/components/knowledge-import";
export type Version = { id: string; item_id: string; version_no: number; status: string; title: string; content: Record<string, unknown>; edit_version: number; submitted_at: string | null; source_type?: string; source_ref?: string | null; review_note?: ReviewNote | null };
export type Item = { id: string; kind: string; key: string; approved_version: Version | null; open_draft: Version | null };
export type Profile = { version: number; legal_name: string; description: string; website_url: string | null; manual_setup: boolean; cvr: string | null; address_line: string | null; postal_code: string | null; city: string | null; country: string; timezone: string; phone: string | null };
export type SourceImport = Import & { url: string | null; skipped: number; finished_at: string | null };
