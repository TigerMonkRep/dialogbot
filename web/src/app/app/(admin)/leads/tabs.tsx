import Link from "next/link";
import { Icon } from "@/components/ui";

/** Henvendelser | Opgaver header shared by /app/leads and /app/tasks. */
export function LeadsHeader({ active }: { active: "leads" | "tasks" }) {
  const tabs: [string, string, string, "leads" | "tasks"][] = [["/app/leads", "Henvendelser", "contact_support", "leads"], ["/app/tasks", "Opgaver", "task_alt", "tasks"]];
  return (
    <div className="flex flex-col gap-space-md">
      <div className="flex flex-col gap-space-xs">
        <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight">{active === "leads" ? "Henvendelser" : "Opgaver"}</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant">Kunder, der vil kontaktes, og det, der skal gøres for dem. Kvalificering, forløb og afregning holdes adskilt.</p>
      </div>
      <nav className="flex items-center gap-space-xs self-start p-1 bg-surface-container-low rounded-xl" aria-label="Henvendelser og opgaver">
        {tabs.map(([href, label, icon, key]) => (
          <Link key={key} href={href} aria-current={active === key ? "page" : undefined}
            className={`flex items-center gap-space-sm px-space-md py-space-sm rounded-lg font-label-md text-label-md ${active === key ? "bg-primary-container text-on-primary shadow-sm" : "text-on-surface-variant hover:text-on-surface"}`}>
            <Icon name={icon} size={18} />{label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
