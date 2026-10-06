import type { NextConfig } from "next";
import { readFileSync } from "node:fs";

// Shown in the app footer: the release version from package.json plus the short commit Vercel built.
const { version } = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string };
const commit = (process.env.VERCEL_GIT_COMMIT_SHA ?? "").slice(0, 7);

const nextConfig: NextConfig = {
  env: { APP_VERSION: `v${version}`, APP_COMMIT: commit },
};

export default nextConfig;
