import { OpkaldView } from "../view";

export default async function OpkaldDetailPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ f?: string; q?: string; days?: string }> }) {
  const { id } = await params;
  const { f, q, days } = await searchParams;
  return <OpkaldView selected={id} f={f} q={q} days={Number(days) || 30} />;
}
