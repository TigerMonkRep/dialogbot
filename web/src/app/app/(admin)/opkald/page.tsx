import { OpkaldView } from "./view";

export default async function OpkaldPage({ searchParams }: { searchParams: Promise<{ f?: string; q?: string; days?: string }> }) {
  const { f, q, days } = await searchParams;
  return <OpkaldView f={f} q={q} days={Number(days) || 30} />;
}
