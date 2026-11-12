import { TP_FRAME_PATH, TP_FRAME_SANDBOX, TP_SCRIPT_SRC, travelpayoutsVerifyEnabled } from "@/lib/travelpayouts";

/** Travelpayouts site verification – only on the /privat landing, only with NEXT_PUBLIC_TRAVELPAYOUTS_VERIFY=1. The
 *  script runs in a sandboxed, invisible iframe and can never open a tab or popup or move this page (lib/travelpayouts.ts). */
export function TravelpayoutsVerify() {
  if (!travelpayoutsVerifyEnabled()) return null;
  return (
    <>
      {/* Inert marker for a verifier that scans the page source for the site script: type="text/plain" is never
          fetched or run by a browser. The script that runs is the one inside the sandboxed iframe below. */}
      <script type="text/plain" data-travelpayouts-verify-marker src={TP_SCRIPT_SRC} />
      <iframe
        src={TP_FRAME_PATH}
        sandbox={TP_FRAME_SANDBOX}
        title="Travelpayouts"
        aria-hidden="true"
        tabIndex={-1}
        data-travelpayouts-verify
        className="absolute w-0 h-0 border-0 pointer-events-none"
        style={{ left: -9999, top: 0 }}
      />
    </>
  );
}
