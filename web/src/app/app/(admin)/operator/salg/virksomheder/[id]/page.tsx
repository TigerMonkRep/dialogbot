import Link from "next/link";
import { ChannelOff, NotOperator, SalgFrame, load } from "../../shared";
import { CompanyDetail, type Detail } from "./client";

export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [r, st] = await Promise.all([load<Detail>(`/operator/salg/companies/${id}`), load<{ mode: string }>("/operator/salg")]);
  if (!r.ok) {
    if (r.status === 501) return <SalgFrame active="/app/operator/salg/virksomheder" title="Virksomhed"><ChannelOff message={r.message} /></SalgFrame>;
    if (r.status === 404) return <SalgFrame active="/app/operator/salg/virksomheder" title="Virksomhed"><p>Virksomheden findes ikke. <Link className="underline" href="/app/operator/salg/virksomheder">Alle virksomheder</Link></p></SalgFrame>;
    return <NotOperator />;
  }
  return (
    <SalgFrame active="/app/operator/salg/virksomheder" title={r.data.display_name}>
      <Link href="/app/operator/salg/virksomheder" className="text-primary underline text-[14px]">← Alle virksomheder</Link>
      <CompanyDetail c={r.data} canSimulate={st.ok && ["simulation", "test", "live"].includes(st.data.mode)} />
    </SalgFrame>
  );
}
