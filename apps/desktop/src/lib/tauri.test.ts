import { describe, expect, it } from "vitest";
import {
  filterPathsUnderWorkspace,
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

describe("isRelativeDeliverablePath", () => {
  it("accepts output deliverables and rejects absolute paths", () => {
    expect(isRelativeDeliverablePath("output/report.docx")).toBe(true);
    expect(isRelativeDeliverablePath("/tmp/report.docx")).toBe(false);
  });
});

describe("resolveUnderWorkspace", () => {
  it("joins workspace root with relative path", () => {
    expect(resolveUnderWorkspace("/ws", "./output/a.md")).toBe("/ws/output/a.md");
  });
});
