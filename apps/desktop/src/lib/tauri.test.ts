import { describe, expect, it } from "vitest";
import {
  assertHttpsUrl,
  filterPathsUnderWorkspace,
  hasDeliverableSuffix,
  isPathUnderWorkspace,
  isRelativeDeliverablePath,
  normalizeFsPath,
  parsePastedPaths,
  resolveUnderWorkspace,
} from "./tauri";

describe("normalizeFsPath", () => {
  it("normalizes backslashes and trailing slashes", () => {
    expect(normalizeFsPath("C:\\work\\docs\\")).toBe("C:/work/docs");
  });
});

describe("isPathUnderWorkspace", () => {
  it("accepts root and nested paths case-insensitively", () => {
    const root = "/Users/me/Project";
    expect(isPathUnderWorkspace("/Users/me/Project", root)).toBe(true);
    expect(isPathUnderWorkspace("/Users/me/Project/out/a.md", root)).toBe(true);
    expect(isPathUnderWorkspace("/Users/me/Other/a.md", root)).toBe(false);
  });
});

describe("filterPathsUnderWorkspace", () => {
  it("splits accepted and rejected paths", () => {
    const root = "/ws";
    const { accepted, rejected } = filterPathsUnderWorkspace(
      ["/ws/a.txt", "/else/b.txt"],
      root,
    );
    expect(accepted).toEqual(["/ws/a.txt"]);
    expect(rejected).toEqual(["/else/b.txt"]);
  });
});

describe("parsePastedPaths", () => {
  it("splits lines and trims blanks", () => {
    expect(parsePastedPaths("/a\n  /b\n\n")).toEqual(["/a", "/b"]);
  });
});

describe("hasDeliverableSuffix", () => {
  it("recognizes Office and text deliverables including pptx", () => {
    expect(hasDeliverableSuffix("deck.pptx")).toBe(true);
    expect(hasDeliverableSuffix("old.ppt")).toBe(true);
    expect(hasDeliverableSuffix("report.docx")).toBe(true);
    expect(hasDeliverableSuffix("工作成果/工作计划.html")).toBe(true);
    expect(hasDeliverableSuffix("notes.exe")).toBe(false);
  });
});

describe("isRelativeDeliverablePath", () => {
  it("accepts output deliverables and rejects absolute paths", () => {
    expect(isRelativeDeliverablePath("工作成果/report.docx")).toBe(true);
    expect(isRelativeDeliverablePath("工作成果/slides.pptx")).toBe(true);
    expect(isRelativeDeliverablePath("工作成果/工作计划.html")).toBe(true);
    expect(isRelativeDeliverablePath("/tmp/report.docx")).toBe(false);
  });
});

describe("resolveUnderWorkspace", () => {
  it("joins workspace root with relative path", () => {
    expect(resolveUnderWorkspace("/ws", "./工作成果/a.md")).toBe("/ws/工作成果/a.md");
  });
});

describe("assertHttpsUrl", () => {
  it("returns a plain https URL", () => {
    expect(assertHttpsUrl("https://www.lirenda.cn")).toBe("https://www.lirenda.cn");
  });

  it("rejects non-https URLs", () => {
    expect(() => assertHttpsUrl("http://www.lirenda.cn")).toThrow("仅允许打开 https 链接");
    expect(() => assertHttpsUrl("javascript:alert(1)")).toThrow("仅允许打开 https 链接");
  });
});
