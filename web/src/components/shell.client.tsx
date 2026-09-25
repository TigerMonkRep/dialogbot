"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Icon } from "./ui";

type Ws = { id: string; name: string; role: string; product_intent: string };
export type NavItem = { href: string; match: string; label: string; icon: string };

const isActive = (path: string, item: NavItem) => path === item.match || path.startsWith(item.match + "/");

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

export function DesktopNav({ items }: { items: NavItem[] }) {
  const path = usePathname();
  return (
    <nav className="hidden xl:flex items-center gap-1 flex-1 justify-center" aria-label="Hovedmenu">
      {items.map((it) => {
        const active = isActive(path, it);
        return (
          <Link key={it.label} href={it.href} aria-current={active ? "page" : undefined}
            className={`px-space-md py-2 rounded-lg font-label-md text-label-md transition-colors ${active ? "bg-primary text-on-primary font-semibold shadow-sm" : "text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface"}`}>
            {it.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function WorkspaceChip({ workspaces, current, compact = false }: { workspaces: Ws[]; current: Ws | null; compact?: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  if (!current) return null;
  return (
    <div className="relative" ref={ref}>
      {compact ? (
        <button onClick={() => setOpen(!open)} className="flex items-center gap-1 mt-0.5" aria-haspopup="listbox" aria-expanded={open} aria-label={`Arbejdsrum: ${current.name}`}>
          <span className="font-label-sm text-[11px] text-on-surface-variant font-medium truncate max-w-[130px]">{current.name}</span>
          <Icon name="expand_more" size={14} className="text-outline" />
        </button>
      ) : (
        <button onClick={() => setOpen(!open)} className="flex items-center gap-space-xs px-space-md py-1.5 rounded-lg bg-surface-container-low text-on-surface hover:bg-surface-container transition-colors" aria-haspopup="listbox" aria-expanded={open}>
          <Icon name="domain" size={18} className="text-secondary" />
          <span className="font-label-md text-label-md font-medium text-on-surface max-w-[220px] truncate">{current.name}</span>
          <Icon name="expand_more" size={16} className="text-on-surface-variant" />
        </button>
      )}
      {open && (
        <ul role="listbox" aria-label="Vælg arbejdsrum" className="absolute left-0 mt-1 w-72 rounded-xl bg-surface-container-lowest shadow-md p-1 z-50">
          {workspaces.map((w) => (
            <li key={w.id} role="option" aria-selected={w.id === current.id}>
              <button onClick={async () => { await selectWs(w.id); setOpen(false); router.refresh(); }} className={`w-full text-left flex items-center gap-space-sm px-space-md py-2 rounded-lg hover:bg-surface-container-low ${w.id === current.id ? "bg-surface-container-low" : ""}`}>
                <span className="w-7 h-7 rounded-lg bg-primary text-on-primary font-label-sm text-label-sm font-bold flex items-center justify-center">{w.name.slice(0, 2).toUpperCase()}</span>
                <span className="flex flex-col"><span className="font-label-md text-label-md font-semibold">{w.name}</span><span className="font-label-sm text-label-sm text-on-surface-variant">{w.role} · {w.product_intent}</span></span>
              </button>
            </li>
          ))}
          <li className="border-t border-outline-variant/40 mt-1 pt-1"><Link href="/onboarding/workspace" onClick={() => setOpen(false)} className="flex items-center gap-space-sm px-space-md py-2 rounded-lg font-label-md text-label-md text-primary hover:bg-surface-container-low"><Icon name="add_circle" size={18} />Nyt arbejdsrum</Link></li>
        </ul>
      )}
    </div>
  );
}

export function AccountButton({ me }: { me: { display_name: string; email: string } | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  return (
    <div className="relative flex-shrink-0" ref={ref}>
      <button onClick={() => setOpen(!open)} className="w-8 h-8 rounded-full bg-primary flex items-center justify-center" aria-label="Konto" aria-haspopup="menu" aria-expanded={open}><Icon name="person" size={18} className="text-on-primary" /></button>
      {open && (
        <div role="menu" className="absolute right-0 mt-1 w-60 rounded-xl bg-surface-container-lowest shadow-md p-space-sm z-50">
          {me && <div className="px-space-sm py-1"><p className="font-label-md text-label-md font-semibold">{me.display_name}</p><p className="font-label-sm text-label-sm text-on-surface-variant truncate">{me.email}</p></div>}
          <Link role="menuitem" href="/app/settings/team" onClick={() => setOpen(false)} className="block px-space-sm py-2 rounded-lg font-label-md text-label-md hover:bg-surface-container-low">Team og roller</Link>
          <button role="menuitem" className="w-full text-left px-space-sm py-2 rounded-lg font-label-md text-label-md text-error hover:bg-surface-container-low" onClick={async () => { await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } }); router.push("/login"); router.refresh(); }}>Log ud</button>
        </div>
      )}
    </div>
  );
}

/** Full navigation as a sheet: hamburger (mobile header), icon (desktop < xl) or bottom-nav "Mere". */
export function MoreMenu({ items, variant }: { items: NavItem[]; variant: "hamburger" | "icon" | "bottom" }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  useEffect(() => setOpen(false), [path]);
  const trigger = {
    hamburger: <button onClick={() => setOpen(!open)} aria-label="Menu" aria-expanded={open} className="w-11 h-11 flex items-center justify-center rounded-lg text-primary hover:bg-surface-container transition-colors active:scale-95"><Icon name={open ? "close" : "menu"} size={24} /></button>,
    icon: <button onClick={() => setOpen(!open)} aria-label="Menu" aria-expanded={open} className="w-9 h-9 rounded-lg flex items-center justify-center text-on-surface-variant hover:bg-surface-container-low"><Icon name={open ? "close" : "menu"} size={20} /></button>,
    bottom: <button onClick={() => setOpen(!open)} aria-expanded={open} className={`flex flex-col items-center justify-center gap-0.5 h-12 w-full transition-colors ${open ? "text-primary-container font-semibold" : "text-on-surface-variant hover:text-on-surface"}`}><Icon name="more_horiz" size={24} /><span className="font-label-sm text-label-sm">Mere</span></button>,
  }[variant];
  const sheet = variant === "bottom"
    ? "fixed left-0 right-0 bottom-16 rounded-t-2xl bg-surface-container-lowest shadow-2xl p-space-md grid gap-1"
    : variant === "hamburger" ? "fixed left-0 right-0 top-16 bg-surface-container-lowest shadow-md p-space-sm grid gap-1" : "absolute right-0 top-12 w-72 rounded-xl bg-surface-container-lowest shadow-md p-space-sm grid gap-1";
  return (
    <div ref={ref} className={variant === "bottom" ? "w-full" : "relative"}>
      {trigger}
      {open && (
        <nav className={`${sheet} z-50`} aria-label="Menu">
          {items.map((it) => {
            const active = isActive(path, it);
            return (
              <Link key={it.label} href={it.href} aria-current={active ? "page" : undefined} onClick={() => setOpen(false)}
                className={`flex items-center gap-space-sm px-space-md py-2.5 rounded-lg font-label-lg text-label-lg ${active ? "bg-primary text-on-primary" : "text-on-surface hover:bg-surface-container-low"}`}>
                <Icon name={it.icon} size={20} className={active ? "" : "text-secondary"} />{it.label}
              </Link>
            );
          })}
        </nav>
      )}
    </div>
  );
}

export function BottomNav({ items, more }: { items: NavItem[]; more: NavItem[] }) {
  const path = usePathname();
  return (
    <nav className="md:hidden fixed bottom-0 w-full z-50 pb-safe bg-surface/90 backdrop-blur-xl shadow-[0_-2px_12px_rgba(0,0,0,0.03)]" aria-label="Genveje">
      <div className="h-16 px-space-sm grid grid-cols-4 items-center">
        {items.map((it) => {
          const active = isActive(path, it);
          return (
            <Link key={it.label} href={it.href} aria-current={active ? "page" : undefined}
              className={`flex flex-col items-center justify-center gap-0.5 h-12 w-full transition-colors ${active ? "text-primary-container font-semibold" : "text-on-surface-variant hover:text-on-surface"}`}>
              <Icon name={it.icon} size={24} filled={active} /><span className="font-label-sm text-label-sm">{it.label}</span>
            </Link>
          );
        })}
        <MoreMenu items={more} variant="bottom" />
      </div>
    </nav>
  );
}
