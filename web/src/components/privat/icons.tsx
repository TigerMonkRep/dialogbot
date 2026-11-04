/** Line icons for Dialogbot Privat: 2.2 px stroke (docs/brand.md), drawn inline so they need no icon font. */
const P: Record<string, React.ReactNode> = {
  list: <path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" />,
  bell: <><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z" /><path d="M10 21h4" /></>,
  phone: <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" />,
  users: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6.5 6.5 0 0 1 3.5 5.5" /></>,
  gift: <><rect x="3" y="8" width="18" height="5" rx="1" /><path d="M5 13v8h14v-8M12 8v13M12 8S10.5 3 8 3.8 8.5 8 12 8zM12 8s1.5-5 4-4.2S15.5 8 12 8z" /></>,
  calendar: <><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></>,
  package: <><path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5z" /><path d="M3.5 7.5 12 12l8.5-4.5M12 12v9" /></>,
  puzzle: <path d="M10 4a2 2 0 0 1 4 0v2h4v4h-2a2 2 0 0 0 0 4h2v4h-4v-2a2 2 0 0 0-4 0v2H6v-4h2a2 2 0 0 0 0-4H6V6h4z" />,
  mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>,
  send: <path d="M5 12h14M13 6l6 6-6 6" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  chevron: <path d="M9 6l6 6-6 6" />,
  coin: <><circle cx="12" cy="12" r="8" /><path d="M12 8v8M9 10.5h4.5a1.5 1.5 0 0 1 0 3H9" /></>,
  share: <><circle cx="18" cy="5" r="2.5" /><circle cx="6" cy="12" r="2.5" /><circle cx="18" cy="19" r="2.5" /><path d="M8.2 10.8l7.6-4.4M8.2 13.2l7.6 4.4" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
  link: <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />,
  trash: <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  // Butikken (app icons)
  cake: <><path d="M4 20h16M5 20v-6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v6" /><path d="M5 15.5c1.2 0 1.2 1 2.4 1s1.2-1 2.3-1 1.2 1 2.3 1 1.2-1 2.3-1 1.2 1 2.4 1" /><path d="M12 12V9M12 6.5a1.5 1.5 0 0 0 0-3 1.5 1.5 0 0 0 0 3z" /></>,
  utensils: <><path d="M5 3v7a3 3 0 0 0 6 0V3M8 3v18" /><path d="M18 3c-2 1-3 4-3 7v2h3v9M18 3v9" /></>,
  car: <><path d="M4 16v-4l2-5h12l2 5v4z" /><path d="M4 12h16M6 16v2M18 16v2" /><circle cx="7.5" cy="14" r=".6" /><circle cx="16.5" cy="14" r=".6" /></>,
  receipt: <><path d="M6 3h12v18l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5L6 21z" /><path d="M9 8h6M9 12h6M9 16h4" /></>,
  stethoscope: <><path d="M6 3v6a5 5 0 0 0 10 0V3" /><path d="M11 14v2a4 4 0 0 0 8 0v-2" /><circle cx="19" cy="12" r="2" /></>,
  suitcase: <><rect x="3.5" y="8" width="17" height="12" rx="2" /><path d="M9 8V5h6v3M9 8v12M15 8v12" /></>,
  sparkle: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />,
  shop: <><path d="M4 9l1.5-5h13L20 9" /><path d="M4 9a2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0" /><path d="M5 11v9h14v-9M10 20v-5h4v5" /></>,
  home: <><path d="M4 11l8-7 8 7" /><path d="M6 10v10h12V10" /><path d="M10 20v-6h4v6" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4.5 21a7.5 7.5 0 0 1 15 0" /></>,
};

/** Known add-on icon keys map onto these; anything new falls back to the generic puzzle piece. */
export function iconFor(key: string | null | undefined): string {
  const k = (key ?? "").toLowerCase();
  const alias: Record<string, string> = { call: "phone", telephone: "phone", group: "users", shared: "users", wishlist: "gift", box: "package", parcel: "package",
    birthday: "cake", birthdays: "cake", food: "utensils", meal: "utensils", mealplan: "utensils", fork: "utensils", vehicle: "car", auto: "car", bill: "receipt", bills: "receipt", invoice: "receipt",
    doctor: "stethoscope", heart: "stethoscope", health: "stethoscope", medical: "stethoscope", travel: "suitcase", luggage: "suitcase", packing: "suitcase", trip: "suitcase", reminder: "bell", lists: "list", store: "shop" };
  return P[k] ? k : alias[k] && P[alias[k]] ? alias[k] : "puzzle";
}

export function Ico({ name, size = 20, stroke = 2.2, className = "" }: { name: string; size?: number; stroke?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round"
      aria-hidden className={`shrink-0 ${className}`}>{P[name] ?? P.puzzle}</svg>
  );
}

/** White icon on a blue tile (brand: "Ikoner: 2,2 px streg, hvide på blå flise"). */
export function Tile({ name, size = 40, className = "bg-accent text-white rounded-[10px]" }: { name: string; size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center justify-center shrink-0 ${className}`} style={{ width: size, height: size }} aria-hidden>
      <Ico name={name} size={Math.round(size / 2)} />
    </span>
  );
}
