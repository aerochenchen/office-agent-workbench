export const BUNDLED_SKILL_IDS: ReadonlySet<string> = new Set([
  "government-document-format",
  "multidoc-digest",
  "office-visual-design",
  "doc-proofread",
  "doc-diff-review",
  "skill-builder",
]);

export function isBundledSkillId(id: string): boolean {
  return BUNDLED_SKILL_IDS.has(id);
}

/** Prefer Runtime `source` / `can_uninstall`; fall back to known bundled ids. */
export function isBundledSkill(skill: {
  id: string;
  source?: string;
  can_uninstall?: boolean;
}): boolean {
  if (skill.source === "bundled") return true;
  if (skill.source === "user") return false;
  if (typeof skill.can_uninstall === "boolean") return !skill.can_uninstall;
  return isBundledSkillId(skill.id);
}

export function canUninstallSkill(skill: {
  id: string;
  source?: string;
  can_uninstall?: boolean;
}): boolean {
  if (typeof skill.can_uninstall === "boolean") return skill.can_uninstall;
  return !isBundledSkill(skill);
}

export function canExportSkill(skill: {
  id: string;
  source?: string;
  can_export?: boolean;
}): boolean {
  if (typeof skill.can_export === "boolean") return skill.can_export;
  return !isBundledSkill(skill);
}

export function filterEnabledSkills<T extends { enabled: boolean }>(skills: T[]): T[] {
  return skills.filter((skill) => skill.enabled);
}
