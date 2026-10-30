import { ChannelOff, NotOperator, SalgFrame, load } from "../shared";
import { FindCompanies, type Industry, type Job } from "./client";

export default async function FindPage() {
  const [ind, jobs] = await Promise.all([
    load<{ items: Industry[]; google_types: { type: string; term: string }[] }>("/operator/salg/industries"),
    load<{ items: Job[]; requests_today: number }>("/operator/salg/search-jobs"),
  ]);
  if (!ind.ok) {
    if (ind.status === 501) return <SalgFrame active="/app/operator/salg/find" title="Find virksomheder"><ChannelOff message={ind.message} /></SalgFrame>;
    return <NotOperator status={ind.status} message={ind.message} />;
  }
  return (
    <SalgFrame active="/app/operator/salg/find" title="Find virksomheder" intro="Vælg branche og område. Søgningen kører i baggrunden via Google Places (eller demo-data uden nøgle). Virksomhedernes egen hjemmeside undersøges først, når du beder om det.">
      <FindCompanies industries={ind.data.items} googleTypes={ind.data.google_types} jobs={jobs.ok ? jobs.data.items : []} requestsToday={jobs.ok ? jobs.data.requests_today : 0} />
    </SalgFrame>
  );
}
