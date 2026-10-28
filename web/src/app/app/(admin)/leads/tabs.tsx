import Link from "next/link";
import { Icon } from "@/components/ui";

/** Henvendelser | Opgaver header shared by /app/leads and /app/tasks. */
export function LeadsHeader({ active }: { active: "leads" | "tasks" }) {
  const tabs: [string, string, string, "leads" | "tasks"][] = [["/app/leads", "Henvendelser", "contact_support", "leads"], ["/app/tasks", "Opgaver", "task_alt", "tasks"]];
  return (
    <div className="flex flex-col gap-space-md">
      <div className="flex flex-col gap-space-xs">
        <span className="eyebrow">Kunder, der vil kontaktes</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{active === "leads" ? "Henvendelser" : "Opgaver"}</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant">Kunder, der vil kontaktes, og det, der skal gøres for dem. Kvalificering, forløb og afregning holdes adskilt.</p>
      </div>
      <nav className="inline-flex self-start p-1 rounded-full border-2 border-ink bg-paper" aria-label="Henvendelser og opgaver">
        {tabs.map(([href, label, icon, key]) => (
          <Link key={key} href={href} aria-current={active === key ? "page" : undefined}
            className={`inline-flex items-center gap-1.5 min-h-[40px] px-3.5 rounded-full text-[14px] font-semibold ${active === key ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>
            <Icon name={icon} size={18} />{label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
