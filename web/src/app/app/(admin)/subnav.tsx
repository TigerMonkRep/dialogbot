"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

/** A row of pill links for the pages inside Konto and Alle indstillinger. Selected = ink with white text. */
export function SubNav({ label, items }: { label: string; items: [href: string, label: string][] }) {
  const path = usePathname();
  return (
    <nav aria-label={label} className="overflow-x-auto no-scrollbar -mx-4 px-4 md:mx-0 md:px-0">
      <ul className="inline-flex gap-2 min-w-max">
        {items.map(([href, text]) => {
          const on = path === href;
          return (
            <li key={href}>
              <Link href={href} aria-current={on ? "page" : undefined}
                className={`inline-flex items-center min-h-[44px] px-4 rounded-full border-2 border-ink text-[14px] font-semibold whitespace-nowrap ${on ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`}>{text}</Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
