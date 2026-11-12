/** Travelpayouts site verification on /privat (Fürster 12/11 16:07, option B).
 *
 *  The partner account must still find its site script, but the script («Drive», emrldtp.cc) is remote-controlled:
 *  its monetisation module (overtab / undertab / delayed_redirect) hooks every click and opens travel offers in new
 *  tabs, and it hides its own hooks (Function.prototype.toString spoofing). A guard in our own document is a race
 *  against code we do not control, so the script never runs in a Dialogbot page. It runs only in a separate document,
 *  /privat/tp-verify, served with `Content-Security-Policy: sandbox allow-scripts` and embedded by the /privat
 *  landing in an `<iframe sandbox="allow-scripts">` without allow-popups, allow-top-navigation*, allow-forms,
 *  allow-modals or allow-same-origin. The browser itself then refuses window.open, target=_blank, top.location,
 *  form posts and dialogs from it, and the document has an opaque origin (no access to our DOM, cookies or storage).
 *  The route answers only same-origin iframe fetches (Sec-Fetch-Dest: iframe) – opened directly it is a 404, since a
 *  sandboxed top-level document could still navigate itself – and the CSP header is a second lock on the sandbox.
 *  /privat also carries an inert `<script type="text/plain">` with the script address for a source-scanning verifier;
 *  browsers never fetch or run it.
 *
 *  Off unless NEXT_PUBLIC_TRAVELPAYOUTS_VERIFY=1. Read at runtime on the server (a computed key, so the build does not
 *  inline it), so the same build can be tested with the flag on and off; on Vercel a change still needs a redeploy. */
export const TP_SCRIPT_SRC = "https://emrldtp.cc/NTk2Mjc3.js?t=596277";
export const TP_FRAME_PATH = "/privat/tp-verify";
export const TP_FRAME_SANDBOX = "allow-scripts";

const FLAG = ["NEXT", "PUBLIC", "TRAVELPAYOUTS", "VERIFY"].join("_");

export function travelpayoutsVerifyEnabled(): boolean {
  return process.env[FLAG] === "1";
}
