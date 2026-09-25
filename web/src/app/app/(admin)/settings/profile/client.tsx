"use client";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui";

export function LogoutButton() {
  const router = useRouter();
  return (
    <button onClick={async () => { await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } }); router.push("/login"); router.refresh(); }}
      className="px-space-md py-2.5 rounded-lg bg-surface-container-lowest text-error font-label-md text-label-md font-semibold hover:bg-error-container/40 flex items-center gap-1.5 shadow-sm">
      <Icon name="logout" size={18} />Log ud
    </button>
  );
}
