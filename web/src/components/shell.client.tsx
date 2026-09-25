"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Icon } from "./ui";

type Ws = { id: string; name: string; role: string; product_intent: string };

async function selectWs(id: string) {
  await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: id }) });
}

export function WorkspaceChip({ workspaces, current }: { workspaces: Ws[]; current: Ws | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  if (!current) return null;
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-space-xs px-space-md py-1.5 rounded-lg bg-surface-container-low text-on-surface hover:bg-surface-container transition-colors" aria-haspopup="listbox" aria-expanded={open}>
        <Icon name="domain" size={18} className="text-secondary" />
        <span className="text-label-md font-medium max-w-[180px] truncate">{current.name}</span>
        <Icon name="expand_more" size={16} className="text-on-surface-variant" />
      </button>
      {open && (
        <ul role="listbox" className="absolute left-0 mt-1 w-72 rounded-xl bg-surface-container-lowest shadow-md p-1 z-50">
          {workspaces.map((w) => (
            <li key={w.id}>
              <button onClick={async () => { await selectWs(w.id); setOpen(false); router.refresh(); }} className={`w-full text-left flex items-center gap-space-sm px-space-md py-2 rounded-lg hover:bg-surface-container-low ${w.id === current.id ? "bg-surface-container-low" : ""}`}>
                <span className="w-7 h-7 rounded-lg bg-primary text-on-primary text-label-sm font-bold flex items-center justify-center">{w.name.slice(0, 2).toUpperCase()}</span>
                <span className="flex flex-col"><span className="text-label-md font-semibold">{w.name}</span><span className="text-label-sm text-on-surface-variant">{w.role} · {w.product_intent}</span></span>
              </button>
            </li>
          ))}
          <li className="border-t border-outline-variant/40 mt-1 pt-1"><Link href="/onboarding/workspace" className="flex items-center gap-space-sm px-space-md py-2 rounded-lg text-label-md text-primary hover:bg-surface-container-low"><Icon name="add_circle" size={18} />Nyt arbejdsrum</Link></li>
        </ul>
      )}
    </div>
  );
}

export function LogoutMenu({ me }: { me: { display_name: string; email: string } | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="w-8 h-8 rounded-full bg-primary flex items-center justify-center" aria-label="Konto"><Icon name="person" size={18} className="text-on-primary" /></button>
      {open && (
        <div className="absolute right-0 mt-1 w-60 rounded-xl bg-surface-container-lowest shadow-md p-space-sm z-50">
          {me && <div className="px-space-sm py-1"><p className="text-label-md font-semibold">{me.display_name}</p><p className="text-label-sm text-on-surface-variant truncate">{me.email}</p></div>}
          <Link href="/app/settings/team" className="block px-space-sm py-2 rounded-lg text-label-md hover:bg-surface-container-low">Team og roller</Link>
          <button className="w-full text-left px-space-sm py-2 rounded-lg text-label-md text-error hover:bg-surface-container-low" onClick={async () => { await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } }); router.push("/login"); router.refresh(); }}>Log ud</button>
        </div>
      )}
    </div>
  );
}

export function MobileNav({ nav }: { nav: [string, string, string][] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="xl:hidden">
      <button onClick={() => setOpen(!open)} className="w-9 h-9 rounded-lg flex items-center justify-center text-on-surface-variant hover:bg-surface-container-low" aria-label="Menu" aria-expanded={open}><Icon name={open ? "close" : "menu"} /></button>
      {open && (
        <nav className="absolute left-0 right-0 top-16 bg-surface-container-lowest shadow-md p-space-sm grid gap-1" aria-label="Mobilmenu">
          {nav.map(([href, label, icon]) => <Link key={label} href={href} onClick={() => setOpen(false)} className="flex items-center gap-space-sm px-space-md py-2.5 rounded-lg text-label-lg text-on-surface hover:bg-surface-container-low"><Icon name={icon} size={20} className="text-secondary" />{label}</Link>)}
        </nav>
      )}
    </div>
  );
}
