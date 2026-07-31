import { describe, expect, it } from "vitest";
import {
  SKILLS_REFRESH_MAX_MS,
  shouldRetrySkillsRefresh,
} from "./skillsRefresh";

describe("shouldRetrySkillsRefresh", () => {
  it("stops once any skills are present", () => {
    expect(shouldRetrySkillsRefresh(0, 1)).toBe(false);
    expect(shouldRetrySkillsRefresh(SKILLS_REFRESH_MAX_MS - 1, 3)).toBe(false);
  });

  it("retries while empty within the budget", () => {
    expect(shouldRetrySkillsRefresh(0, 0)).toBe(true);
    expect(shouldRetrySkillsRefresh(SKILLS_REFRESH_MAX_MS - 1, 0)).toBe(true);
  });

  it("stops when empty and budget exhausted", () => {
    expect(shouldRetrySkillsRefresh(SKILLS_REFRESH_MAX_MS, 0)).toBe(false);
    expect(shouldRetrySkillsRefresh(SKILLS_REFRESH_MAX_MS + 500, 0)).toBe(false);
  });
});
