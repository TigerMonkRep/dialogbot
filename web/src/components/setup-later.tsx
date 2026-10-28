"use client";
import Link from "next/link";

/** «Jeg gør resten senere»: lets the person look around I dag before the three steps are finished. Remembered for 30 days. */
export function SetupLater({ className = "" }: { className?: string }) {
  return (
    <Link href="/app" className={`underline underline-offset-2 ${className}`} onClick={() => { document.cookie = "db_setup_later=1; path=/; max-age=2592000; samesite=lax"; }}>Jeg gør resten senere</Link>
  );
}
