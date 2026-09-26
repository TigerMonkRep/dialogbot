"use client";
import { useEffect } from "react";
import { api } from "@/lib/client";

/** Marks the list as read once shown; the highlights stay until the next visit, the bell clears on navigation. */
export function MarkSeen({ wsId, unread }: { wsId: string; unread: number }) {
  useEffect(() => {
    if (!unread) return;
    api(`/workspaces/${wsId}/notifications/seen`, { method: "POST" }).catch(() => {});
  }, [wsId, unread]);
  return null;
}
