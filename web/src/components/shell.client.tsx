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

const MENU_ITEM = "flex items-center gap-2.5 min-h-[44px] px-3 rounded-xl text-[15px] font-semibold text-ink hover:bg-panel";
const POPOVER = "absolute mt-2 rounded-2xl bg-paper border-2 border-ink shadow-block-sm p-2 z-50";

/** The ONLY main nav: a pill-shaped segmented control. Selected = ink with white text. */
export function PillNav({ items, className = "" }: { items: NavItem[]; className?: string }) {
  const path = usePathname();
  return (
    <nav className={`inline-flex p-1 rounded-full border-2 border-ink bg-paper ${className}`} aria-label="Sider">
      {items.map((it) => {
        const active = isActive(path, it);
        return (
          <Link key={it.label} href={it.href} aria-current={active ? "page" : undefined}
            className={`inline-flex items-center min-h-[40px] px-4 rounded-full text-[14px] font-semibold whitespace-nowrap transition-colors ${active ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>
            {it.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function WorkspaceChip({ workspaces, current, compact = false, plain = false }: { workspaces: Ws[]; current: Ws | null; compact?: boolean; plain?: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  if (!current) return null;
  const single = workspaces.length <= 1;
  return (
    <div className="relative min-w-0" ref={ref}>
      <button onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open} aria-label={`Arbejdsrum: ${current.name}`}
        className={`flex items-center gap-1 min-h-[44px] rounded-xl text-muted hover:text-ink ${plain || compact ? "" : "px-2"} ${compact ? "text-[12px]" : "text-[14px]"}`}>
        <span className={`truncate ${compact ? "max-w-[140px]" : "max-w-[220px]"}`}>{current.name}</span>
        {!single && <Icon name="expand_more" size={16} />}
        {single && <Icon name="expand_more" size={16} className="opacity-60" />}
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
          <li className="border-t-[1.5px] border-ink mt-1 pt-1"><Link href="/onboarding/workspace" onClick={() => setOpen(false)} className={`${MENU_ITEM} text-accent`}><Icon name="add_circle" size={18} />Nyt arbejdsrum</Link></li>
        </ul>
      )}
    </div>
  );
}

/** Profile menu: yellow round avatar with the user's initial. Operator-only items live here. */
export function AccountButton({ me, extra = [] }: { me: { display_name: string; email: string; is_platform_operator?: boolean } | null; extra?: NavItem[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  const initial = (me?.display_name || me?.email || "?").trim().charAt(0).toUpperCase();
  return (
    <div className="relative flex-shrink-0" ref={ref}>
      <button onClick={() => setOpen(!open)} className="w-11 h-11 rounded-full flex items-center justify-center" aria-label={me ? `Profil: ${me.display_name}` : "Konto"} aria-haspopup="menu" aria-expanded={open}>
        <span className="w-10 h-10 rounded-full bg-highlight text-ink font-display font-extrabold text-[15px] flex items-center justify-center">{initial}</span>
      </button>
      {open && (
        <div role="menu" className={`${POPOVER} right-0 w-72`}>
          {me && <div className="px-3 py-2"><p className="text-[15px] font-semibold text-ink">{me.display_name}</p><p className="text-[13px] text-muted truncate">{me.email}</p></div>}
          <Link role="menuitem" href="/app/settings/profile" onClick={() => setOpen(false)} className={MENU_ITEM}><Icon name="person" size={18} className="text-accent" />Min profil</Link>
          <Link role="menuitem" href="/app/settings/team" onClick={() => setOpen(false)} className={MENU_ITEM}><Icon name="group" size={18} className="text-accent" />Team og roller</Link>
          <Link role="menuitem" href="/ambassador" onClick={() => setOpen(false)} className={MENU_ITEM}><Icon name="handshake" size={18} className="text-accent" />Ambassadør: anbefal og tjen</Link>
          {extra.map((it) => <Link key={it.href} role="menuitem" href={it.href} onClick={() => setOpen(false)} className={MENU_ITEM}><Icon name={it.icon} size={18} className="text-accent" />{it.label}</Link>)}
          {me?.is_platform_operator && (
            <div className="border-t-[1.5px] border-ink mt-1 pt-1">
              <span className="eyebrow block px-3 pt-2 pb-1">Operatør</span>
              <Link role="menuitem" href="/app/operator/ambassadors" onClick={() => setOpen(false)} className={MENU_ITEM}>Ambassadører</Link>
              <Link role="menuitem" href="/app/operator/social" onClick={() => setOpen(false)} className={MENU_ITEM}>Sociale medier</Link>
              <Link role="menuitem" href="/app/operator/sales" onClick={() => setOpen(false)} className={MENU_ITEM}>Salg</Link>
              <Link role="menuitem" href="/app/operator/telephony" onClick={() => setOpen(false)} className={MENU_ITEM}>Telefoni</Link>
              <Link role="menuitem" href="/app/operator/voices" onClick={() => setOpen(false)} className={MENU_ITEM}>Stemmer</Link>
            </div>
          )}
          <div className="border-t-[1.5px] border-ink mt-1 pt-1">
            <button role="menuitem" className={`w-full text-left ${MENU_ITEM} text-danger hover:bg-danger-soft`} onClick={async () => { await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } }); router.push("/login"); router.refresh(); }}>Log ud</button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Everything that is not one of the three main pages: a compact "Mere" menu (outline button on desktop, hamburger on mobile). */
export function MoreMenu({ items, variant }: { items: NavItem[]; variant: "hamburger" | "icon" | "bottom" | "button" }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  useEffect(() => setOpen(false), [path]);
  const anyActive = items.some((it) => isActive(path, it));
  const trigger = variant === "hamburger" || variant === "icon"
    ? <button onClick={() => setOpen(!open)} aria-label="Mere" aria-expanded={open} className="w-11 h-11 flex items-center justify-center rounded-xl text-ink hover:bg-panel"><Icon name={open ? "close" : "menu"} size={24} /></button>
    : <button onClick={() => setOpen(!open)} aria-expanded={open} className={`inline-flex items-center gap-1 min-h-[44px] px-3.5 rounded-xl border-2 border-ink text-[14px] font-semibold ${anyActive ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`}>Mere<Icon name={open ? "expand_less" : "expand_more"} size={18} /></button>;
  const sheet = variant === "hamburger"
    ? "fixed left-0 right-0 top-[64px] bg-paper border-b-2 border-ink p-3 grid gap-1 max-h-[calc(100dvh-64px)] overflow-y-auto"
    : `${POPOVER} right-0 w-72 grid gap-0.5 max-h-[70dvh] overflow-y-auto`;
  return (
    <div ref={ref} className="relative">
      {trigger}
      {open && (
        <nav className={`${sheet} z-50`} aria-label="Mere">
          {items.map((it) => {
            const active = isActive(path, it);
            return (
              <Link key={it.label} href={it.href} aria-current={active ? "page" : undefined} onClick={() => setOpen(false)}
                className={`${MENU_ITEM} ${active ? "bg-ink text-paper hover:bg-ink" : ""}`}>
                <Icon name={it.icon} size={20} className={active ? "text-highlight" : "text-accent"} />{it.label}
              </Link>
            );
          })}
        </nav>
      )}
    </div>
  );
}
