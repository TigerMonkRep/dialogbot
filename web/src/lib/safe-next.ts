/** Accept only same-origin relative paths for ?next= redirects ("//host" and "/\host" leave the site). */
export function safeNext(next: string | null | undefined, fallback = "/app"): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : fallback;
}
