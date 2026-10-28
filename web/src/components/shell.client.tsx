"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Icon } from "./ui";

type Ws = { id: string; name: string; role: string; product_intent: string };
export type NavItem = { href: string; match: string; also?: string[]; label: string; icon: string };

/** "I dag" (/app) is only active on its own page and the two pages reached from it (Aftaler, Kampagner). */
const isActive = (path: string, item: NavItem) =>
  path === item.match || (item.match !== "/app" && path.startsWith(item.match + "/")) || (item.also ?? []).some((a) => path === a || path.startsWith(a + "/"));

/** Close a popover on outside click and Escape. */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) close(); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("mousedown", onDown); document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open, close]);
  return ref;
}

async function selectWs(id: string) {
  await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: id }) });
}

const MENU_ITEM = "flex items-center gap-2.5 min-h-[44px] px-3 rounded-xl text-[15px] font-semibold text-ink hover:bg-panel";
const POPOVER = "absolute mt-2 rounded-2xl bg-paper border-2 border-ink shadow-block-sm p-2 z-50";

export function WorkspaceChip({ workspaces, current, compact = false, plain = false }: { workspaces: Ws[]; current: Ws | null; compact?: boolean; plain?: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  if (!current) return null;
  const single = workspaces.length <= 1;
  if (single) return <span className={`truncate min-h-[44px] inline-flex items-center text-muted ${compact ? "text-[12px] max-w-[140px]" : "text-[14px] max-w-[220px]"}`}>{current.name}</span>;
  return (
    <div className="relative min-w-0" ref={ref}>
      <button onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open} aria-label={`Arbejdsrum: ${current.name}`}
        className={`flex items-center gap-1 min-h-[44px] rounded-xl text-muted hover:text-ink ${plain || compact ? "" : "px-2"} ${compact ? "text-[12px]" : "text-[14px]"}`}>
        <span className={`truncate ${compact ? "max-w-[140px]" : "max-w-[220px]"}`}>{current.name}</span>
        <Icon name="expand_more" size={16} />
      </button>
      {open && (
        <ul role="listbox" aria-label="Vælg arbejdsrum" className={`${POPOVER} left-0 w-72`}>
          {workspaces.map((w) => (
            <li key={w.id} role="option" aria-selected={w.id === current.id}>
              <button onClick={async () => { await selectWs(w.id); setOpen(false); router.refresh(); }} className={`w-full text-left ${MENU_ITEM} ${w.id === current.id ? "bg-panel" : ""}`}>
                <span className="w-8 h-8 rounded-lg bg-accent text-white font-display text-[13px] font-extrabold flex items-center justify-center shrink-0">{w.name.slice(0, 2).toUpperCase()}</span>
                <span className="flex flex-col min-w-0"><span className="truncate">{w.name}</span><span className="text-label-sm tracking-normal font-medium text-muted">{w.role} · {w.product_intent}</span></span>
              </button>
            </li>
          ))}
          <li className="border-t-[1.5px] border-ink mt-1 pt-1"><Link href="/opsaetning/1?ny=1" onClick={() => setOpen(false)} className={`${MENU_ITEM} text-accent`}><Icon name="add_circle" size={18} />Nyt arbejdsrum</Link></li>
        </ul>
      )}
    </div>
  );
}

/** The four pages as a pill-shaped segmented control (desktop and tablet). Selected = ink with white text. */
export function TabNav({ items }: { items: NavItem[] }) {
  const path = usePathname();
  return (
    <nav className="inline-flex p-1 rounded-full border-2 border-ink bg-paper" aria-label="Sider">
      {items.map((it) => {
        const active = isActive(path, it);
        return (
          <Link key={it.label} href={it.href} aria-current={active ? "page" : undefined}
            className={`inline-flex items-center min-h-[40px] px-3.5 md:px-4 rounded-full text-[14px] font-semibold whitespace-nowrap transition-colors ${active ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>
            {it.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** The same four pages as bottom tabs on a phone: icon + label, the selected one gets a yellow pill behind the icon. */
export function BottomTabs({ items }: { items: NavItem[] }) {
  const path = usePathname();
  return (
    <nav aria-label="Sider" className="sm:hidden fixed inset-x-0 bottom-0 z-40 bg-paper border-t-2 border-ink pb-safe">
      <ul className="grid grid-cols-4">
        {items.map((it) => {
          const active = isActive(path, it);
          return (
            <li key={it.label}>
              <Link href={it.href} aria-current={active ? "page" : undefined} className="flex flex-col items-center justify-center gap-0.5 min-h-[60px] text-[12px] font-semibold text-ink">
                <span className={`inline-flex items-center justify-center w-12 h-7 rounded-full ${active ? "bg-highlight" : ""}`}><Icon name={it.icon} size={20} filled={active} /></span>
                {it.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** The yellow avatar with the user's initial: one tap to Konto (profile, team, billing, log out). */
export function Avatar({ me }: { me: { display_name: string; email: string } | null }) {
  const path = usePathname();
  const initial = (me?.display_name || me?.email || "?").trim().charAt(0).toUpperCase();
  return (
    <Link href="/app/konto" aria-label={me ? `Konto: ${me.display_name}` : "Konto"} aria-current={path.startsWith("/app/konto") ? "page" : undefined}
      className="flex-shrink-0 w-11 h-11 rounded-full flex items-center justify-center">
      <span className="w-10 h-10 rounded-full bg-highlight text-ink font-display font-extrabold text-[15px] flex items-center justify-center border-2 border-ink">{initial}</span>
    </Link>
  );
}

/** Shown on every page while an operator looks at a customer's account ("se som kunde"): read-only, ends with one click. */
export function ViewAsBanner({ who }: { who: { name: string; email: string } }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <div role="status" className="bg-ink text-paper border-b-2 border-ink px-4 py-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[14px]">
      <span className="flex items-center gap-2"><Icon name="visibility" size={18} />Du ser som <strong>{who.name}</strong> ({who.email}) – kun læsning, intet kan ændres.</span>
      <button disabled={busy} className="underline font-semibold disabled:opacity-60" onClick={async () => {
        setBusy(true);
        await fetch("/api/admin/view-as/end", { method: "POST", headers: { "x-requested-with": "dialogbot" } });
        router.push("/app/operator/admin/kunder"); router.refresh();
      }}>Afslut og gå tilbage til admin</button>
    </div>
  );
}
