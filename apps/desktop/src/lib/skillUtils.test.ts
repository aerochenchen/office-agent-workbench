import { describe, expect, it } from "vitest";
import {
  BUNDLED_SKILL_IDS,
  filterEnabledSkills,
  isBundledSkillId,
} from "./skillUtils";

describe("BUNDLED_SKILL_IDS", () => {
  it("includes known bundled skill ids", () => {
    expect(BUNDLED_SKILL_IDS.has("government-document-format")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("multidoc-digest")).toBe(true);
    expect(BUNDLED_SKILL_IDS.has("skill-builder")).toBe(true);
  });
});

describe("isBundledSkillId", () => {
  it("returns true for bundled ids", () => {
    expect(isBundledSkillId("government-document-format")).toBe(true);
    expect(isBundledSkillId("multidoc-digest")).toBe(true);
    expect(isBundledSkillId("skill-builder")).toBe(true);
  });

  it("returns false for unknown ids", () => {
    expect(isBundledSkillId("custom-skill")).toBe(false);
    expect(isBundledSkillId("")).toBe(false);
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
