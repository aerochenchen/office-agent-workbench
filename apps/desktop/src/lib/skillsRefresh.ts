/** Retry window after health becomes ok while bundled skill seed may still be running. */
export const SKILLS_REFRESH_INTERVAL_MS = 500;
export const SKILLS_REFRESH_MAX_MS = 4_000;

/** Keep polling until skills appear or the retry budget is exhausted. */
export function shouldRetrySkillsRefresh(elapsedMs: number, skillsCount: number): boolean {
  if (skillsCount > 0) return false;
  return elapsedMs < SKILLS_REFRESH_MAX_MS;
}
