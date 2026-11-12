import { redirect } from "next/navigation";

/** Old address of «trin 1» (bookmarks, mails, QA specs): the guide now has named steps – Virksomhed is the first. */
export default async function Old1({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const q = new URLSearchParams(Object.entries(await searchParams).filter((e): e is [string, string] => typeof e[1] === "string"));
  redirect(`/opsaetning/virksomhed${q.size ? `?${q}` : ""}`);
}
