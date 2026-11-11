import { redirect } from "next/navigation";

/** «Henvendelser» (the tile on I dag, the assistant's chip) links to /app/opkald/henvendelser. Without this page the
 *  segment fell through to /app/opkald/[id], whose backend call answered 422 for the non-UUID id → «Siden kunne ikke
 *  vises» (F-V2-04-I03). Enquiries and tasks live in the «Til dig» filter, the same target as the old /app/leads and
 *  /app/tasks (next.config.ts MOVED). */
export default function OpkaldListRedirect() {
  redirect("/app/opkald?f=to_you");
}
