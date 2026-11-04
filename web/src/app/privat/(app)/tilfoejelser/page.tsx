import { permanentRedirect } from "next/navigation";

/** The add-on shop moved to /privat/butik («Butikken»). */
export default function Page() { permanentRedirect("/privat/butik"); }
