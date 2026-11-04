import { PrivatApp } from "@/components/privat/shell";
import { privatSession } from "../session.server";

/** Dialogbot Privat app: one client tree for Min dag, Samtale, Opgaver, Konto and Tilføjelser, so the conversation
 *  and the data survive moving between them. The pages below only set the title; the shell reads the path. Visitors
 *  without login see example data and are asked to log in when they save their first own task. */
export default async function PrivatLayout({ children }: { children: React.ReactNode }) {
  const session = await privatSession();
  // data-theme="privat": orange accent, warm paper/panel (globals.css). The shell renders into this wrapper.
  return <div data-theme="privat" className="contents"><PrivatApp session={session} />{children}</div>;
}
