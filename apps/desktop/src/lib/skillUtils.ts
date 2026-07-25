export const BUNDLED_SKILL_IDS: ReadonlySet<string> = new Set([
  "government-document-format",
  "multidoc-digest",
  "skill-builder",
]);

export function isBundledSkillId(id: string): boolean {
  return BUNDLED_SKILL_IDS.has(id);
}

export function filterEnabledSkills<T extends { enabled: boolean }>(skills: T[]): T[] {
  return skills.filter((skill) => skill.enabled);
}
