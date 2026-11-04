import { Suspense } from "react";
import { AudienceSwitch } from "@/components/audience-switch";
import { FunnelProvider } from "@/components/funnel";

/** The Erhverv quiz-funnel (/start/1 … /start/7 and the reveal /start/klar). Klods-blå like the rest of the business
 *  site. One provider for all steps: the draft is loaded once and kept while the person moves between them. The
 *  provider reads the URL (?h=, ?b=, utm_*), which needs a Suspense boundary. */
export default function StartLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense>
      <FunnelProvider kind="erhverv" base="/start" total={7} audience={<AudienceSwitch current="erhverv" />}>{children}</FunnelProvider>
    </Suspense>
  );
}
