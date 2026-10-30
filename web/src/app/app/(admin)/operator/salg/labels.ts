/** Types and Danish labels shared by server and client components (no server-only imports here). */
export type Status = {
  mode: "off" | "research" | "simulation" | "test" | "live"; places: "google" | "demo"; cvr_configured: boolean;
  sales_workspace: { id: string; name: string } | null; ai_provider: string; test_numbers: number; missing: string[];
  limits: Record<string, number>;
};

export type Company = {
  id: string; source: "google" | "demo" | "import"; display_name: string; legal_name: string | null; cvr: string | null;
  industry_key: string | null; industry_text: string | null; address_line: string | null; postal_code: string | null; city: string | null;
  website_url: string | null; domain: string | null; main_phone_e164: string | null; public_email: string | null;
  google: { place_id: string | null; fetched_at: string | null; types: string[]; primary_type: string | null; business_status: string | null; maps_uri: string | null; opening_hours: string[] | null; rating: number | null; user_rating_count: number | null };
  advertising_protected: boolean | null; relevance_score: number; relevance_reasons: string[];
  data_quality: { issues?: string[] }; research_status: "found" | "researched" | "profiled" | "incomplete";
  researched_at: string | null; research_error: string | null; possible_duplicate_of: string | null; duplicate_reason: string | null;
  existing_customer: boolean; contactable: { result: string; reasons: string[] }; first_seen_at: string | null;
};

export const SOURCE: Record<string, string> = { google: "Google", demo: "Demo-data", import: "Importeret" };
export const RESEARCH: Record<string, string> = { found: "Fundet", researched: "Undersøgt", profiled: "Profileret", incomplete: "Ufuldstændig" };
export const ISSUE: Record<string, string> = {
  missing_website: "Ingen hjemmeside", missing_phone: "Intet nummer", conflicting_phone: "Modstridende numre",
  stale: "Forældet", advertising_protection_unknown: "Reklamebeskyttelse ukendt", not_operational: "Ikke i drift",
};
