export type BType = { id: string; name: string; duration_minutes: number; description: string; active: boolean };
export type Settings = {
  version: number; enabled: boolean; lead_time_hours: number; horizon_days: number; buffer_minutes: number;
  busy_ics_url: string | null; busy_synced_at: string | null; busy_error: string | null; busy_blocks: number;
  feed_url: string; has_opening_hours: boolean; open_weekdays: number[]; opening_hours: Record<string, string[]>; types: BType[];
};
export type Booking = {
  id: string; title: string; label: string; starts_at: string; ends_at: string; source: string; contact_name: string; contact_phone: string | null;
  contact_email: string | null; note: string; lead_id: string | null; conversation_id: string | null;
};
