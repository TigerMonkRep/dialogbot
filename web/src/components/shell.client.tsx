"use client";
import { useRouter } from "next/navigation";
import { Button } from "./ui";

export function LogoutButton() {
  const router = useRouter();
  return (
    <Button variant="ghost" onClick={async () => { await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } }); router.push("/login"); router.refresh(); }}>
      Log ud
    </Button>
  );
}

export function WorkspaceSwitcher({ workspaces, current }: { workspaces: { id: string; name: string; role: string }[]; current: string | null }) {
  const router = useRouter();
  if (workspaces.length === 0) return null;
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="sr-only">Arbejdsrum</span>
      <select
        className="rounded-lg border border-line bg-white px-2 py-1.5 text-sm font-semibold text-primary-dark"
        value={current ?? workspaces[0].id}
        onChange={async (e) => {
          await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: e.target.value }) });
          router.refresh();
        }}
      >
        {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name} · {w.role}</option>)}
      </select>
    </label>
  );
}
