"use client";
import type { T } from "@/i18n/translate";
import type { Addon } from "@/lib/privat/api";

/** Name/tagline/description of an add-on: i18n `privat.addons.<key>.<field>` when we have it, else the API's own text
 *  (which the backend already writes in the user's language). A new add-on in the catalog needs no web change. */
export function addonText(t: T, a: Addon, field: "name" | "tagline" | "description"): string {
  const k = `addons.${a.key}.${field}`;
  const v = t(k);
  return v === `privat.${k}` ? a[field] : v;
}

/** Can the app be switched on with the user's rights? Backends without the field: everything that is not
 *  «monthly» is included; monthly apps need the plan. */
export function addonIncluded(a: Addon, entitled: boolean): boolean {
  if (typeof a.included === "boolean") return a.included;
  if (typeof a.requires_plan === "boolean") return !a.requires_plan || entitled;
  return a.pricing !== "monthly" || entitled;
}
/** Old names, kept for imports: the shop is apps.tsx now. */
export { ShopPage as StorePage, ShopPage as AddonsPage } from "./apps";
