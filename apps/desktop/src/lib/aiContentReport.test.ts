import { describe, expect, it } from "vitest";
import {
  AI_CONTENT_REPORT_SUBJECT,
  SUPPORT_EMAIL,
  buildAiContentReportMailto,
  truncateForMailto,
} from "./aiContentReport";

describe("truncateForMailto", () => {
  it("leaves short text unchanged", () => {
    expect(truncateForMailto("hello", 10)).toBe("hello");
  });

  it("truncates long text with ellipsis", () => {
    expect(truncateForMailto("abcdefghij", 5)).toBe("abcde…");
  });
});

describe("buildAiContentReportMailto", () => {
  it("targets support email and fixed subject", () => {
    const url = buildAiContentReportMailto({
      userNote: "不当输出",
      appVersion: "0.1.0",
    });
    expect(url.startsWith(`mailto:${SUPPORT_EMAIL}?`)).toBe(true);
    expect(url).toContain(`subject=${encodeURIComponent(AI_CONTENT_REPORT_SUBJECT)}`);
    expect(decodeURIComponent(url)).toContain("不当输出");
    expect(decodeURIComponent(url)).toContain("版本：0.1.0");
  });

  it("includes truncated assistant excerpt when provided", () => {
    const long = "x".repeat(5000);
    const url = buildAiContentReportMailto({
      userNote: "",
      appVersion: "0.1.0",
      assistantExcerpt: long,
      maxExcerptChars: 100,
    });
    const body = decodeURIComponent(url.split("body=")[1] ?? "");
    expect(body).toContain("助手回复摘要");
    expect(body).toContain("…");
    expect(body.length).toBeLessThan(800);
  });
});
