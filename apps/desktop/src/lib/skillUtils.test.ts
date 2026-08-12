import { describe, expect, it } from "vitest";
import {
  BUNDLED_SKILL_IDS,
  canExportSkill,
  canUninstallSkill,
  filterEnabledSkills,
  isBundledSkill,
  isBundledSkillId,
} from "./skillUtils";

describe("BUNDLED_SKILL_IDS", () => {
  it("includes known bundled skill ids", () => {
    expect(BUNDLED_SKILL_IDS.has("government-document-format")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("multidoc-digest")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("office-visual-design")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("doc-proofread")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("doc-diff-review")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("meeting-followup")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("material-gap")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("sheet-to-brief")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("one-to-three")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("brief-deck")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("chart-generation")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("skill-builder")).toBe(true);
  });
});

describe("isBundledSkillId", () => {
  it("returns true for bundled ids", () => {
    expect(isBundledSkillId("government-document-format")).toBe(true);
    expect(isBundledSkillId("doc-proofread")).toBe(true);
  });

  it("returns false for unknown ids", () => {
    expect(isBundledSkillId("custom-skill")).toBe(false);
    expect(isBundledSkillId("")).toBe(false);
  });
});

describe("isBundledSkill / canUninstall / canExport", () => {
  it("prefers Runtime source field", () => {
    expect(isBundledSkill({ id: "custom", source: "bundled" })).toBe(true);
    expect(isBundledSkill({ id: "government-document-format", source: "user" })).toBe(false);
    expect(canUninstallSkill({ id: "x", source: "bundled" })).toBe(false);
    expect(canExportSkill({ id: "x", source: "bundled" })).toBe(false);
    expect(canUninstallSkill({ id: "x", source: "user" })).toBe(true);
  });

  it("falls back to known id list when source absent", () => {
    expect(isBundledSkill({ id: "doc-diff-review" })).toBe(true);
    expect(canUninstallSkill({ id: "doc-diff-review" })).toBe(false);
    expect(canUninstallSkill({ id: "custom-skill" })).toBe(true);
  });
});

describe("filterEnabledSkills", () => {
  it("returns only skills with enabled true", () => {
    const skills = [
      { id: "a", enabled: true },
      { id: "b", enabled: false },
      { id: "c", enabled: true },
    ];
    expect(filterEnabledSkills(skills)).toEqual([
      { id: "a", enabled: true },
      { id: "c", enabled: true },
    ]);
  });

  it("returns empty array when none enabled", () => {
    expect(filterEnabledSkills([{ id: "a", enabled: false }])).toEqual([]);
  });

  it("returns empty array for empty input", () => {
    expect(filterEnabledSkills([])).toEqual([]);
  });
});
