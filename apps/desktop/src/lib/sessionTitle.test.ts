import { describe, expect, it } from "vitest";
import {
  DEFAULT_SESSION_TITLE,
  normalizeSessionTitle,
  SESSION_TITLE_MAX_LEN,
} from "./sessionTitle";

describe("normalizeSessionTitle", () => {
  it("trims and keeps text", () => {
    expect(normalizeSessionTitle("  季度总结  ")).toBe("季度总结");
  });

  it("falls back for blank", () => {
    expect(normalizeSessionTitle("")).toBe(DEFAULT_SESSION_TITLE);
    expect(normalizeSessionTitle("   ")).toBe(DEFAULT_SESSION_TITLE);
  });

  it("truncates to max length", () => {
    const long = "字".repeat(100);
    const out = normalizeSessionTitle(long);
    expect(out.length).toBe(SESSION_TITLE_MAX_LEN);
    expect(out).toBe("字".repeat(SESSION_TITLE_MAX_LEN));
  });
});
