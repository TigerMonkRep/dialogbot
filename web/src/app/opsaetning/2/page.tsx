import { redirect } from "next/navigation";

/** Old address of «trin 2 – Kalender & systemer»: now the Kalender step (shown only when «Booke aftaler» is chosen; the
 *  page itself sends on when it is not). The provider's ?connected=/?error= come along. */
export default async function Old2({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const q = new URLSearchParams(Object.entries(await searchParams).filter((e): e is [string, string] => typeof e[1] === "string"));
  redirect(`/opsaetning/kalender${q.size ? `?${q}` : ""}`);
}
