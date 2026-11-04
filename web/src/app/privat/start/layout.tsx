import { Suspense } from "react";
import { AudienceSwitch } from "@/components/audience-switch";
import { FunnelProvider } from "@/components/funnel";

/** The Privat quiz-funnel (/privat/start/1 … /privat/start/6). Orange theme via data-theme="privat" (globals.css), like
 *  the Privat landing and app. Not under privat/(app): no app shell, no session – a visitor without an account. */
export default function PrivatStartLayout({ children }: { children: React.ReactNode }) {
  return (
    <div data-theme="privat" className="contents">
      <Suspense>
        <FunnelProvider kind="privat" base="/privat/start" total={6} audience={<AudienceSwitch current="privat" />}>{children}</FunnelProvider>
      </Suspense>
    </div>
  );
}
