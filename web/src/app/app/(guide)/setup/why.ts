import type { Task } from "./page";

const WHY: Record<string, string> = {
  "knowledge.services": "Assistenten må kun love det, som virksomheden har godkendt. Uden mindst én godkendt ydelse findes der intet, den kan svare korrekt på.",
  "knowledge.review": "Kun ejere og administratorer kan gøre viden aktiv. Det sikrer, at ingen medarbejder ved en fejl publicerer priser eller løfter.",
  "checks.server": "Tjekkene beviser, at profil, sprog og godkendt viden hænger sammen. De bliver forældede, når du ændrer noget, så et gammelt bestået tjek ikke dækker en ny konfiguration.",
};

/** Why a task is a prerequisite — shared by the server-rendered page and client components. */
export function whyText(task: Task): string {
  return WHY[task.key] ?? `Trinnet er ${task.required ? "nødvendigt" : "valgfrit"} for de mål, du har valgt. ${task.blocked_by[0]?.message ?? task.explanation}`;
}
