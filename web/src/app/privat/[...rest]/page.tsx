import { notFound } from "next/navigation";

/** Any /privat/… address no Privat page matches → the Privat 404 (app/privat/not-found.tsx), status 404 (F-JP-11).
 *  Real pages (the (app) group, invitation, start, offline …) are more specific and always win. */
export default function UnknownPrivatPage() {
  notFound();
}
