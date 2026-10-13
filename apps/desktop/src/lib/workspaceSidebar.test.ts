import { describe, expect, it } from "vitest";
import type { SessionMeta } from "./types";
import {
  groupSessionsByWorkspace,
  parseSidebarMemory,
  pathsEqual,
  pickRestoreWorkspace,
  pickSessionInWorkspace,
  visibleWorkspaceGroups,
  withArchivedFolder,
  withRememberedSession,
  withToggledCollapse,
  type SidebarMemory,
} from "./workspaceSidebar";

function session(partial: Partial<SessionMeta> & Pick<SessionMeta, "id" | "workspace_path">): SessionMeta {
  return {
    title: partial.id,
    created_at: 1,
    updated_at: 1,
    ...partial,
  };
}

describe("groupSessionsByWorkspace", () => {
  it("keeps every folder and nests chats by recent activity", () => {
    const groups = groupSessionsByWorkspace([
      session({ id: "a1", workspace_path: "/work/甲", updated_at: 10 }),
      session({ id: "b1", workspace_path: "/work/乙", updated_at: 30 }),
      session({ id: "a2", workspace_path: "/work/甲", updated_at: 20 }),
      session({ id: "loose", workspace_path: "", updated_at: 99 }),
    ]);

    expect(groups.map((g) => g.path)).toEqual(["/work/乙", "/work/甲"]);
    expect(groups[1]?.sessions.map((s) => s.id)).toEqual(["a2", "a1"]);
    expect(groups[0]?.name).toBe("乙");
  });

  it("disambiguates folders that share a name", () => {
    const groups = groupSessionsByWorkspace([
      session({ id: "1", workspace_path: "/docs/报告", updated_at: 2 }),
      session({ id: "2", workspace_path: "/archive/报告", updated_at: 1 }),
    ]);
    expect(groups.map((g) => g.name).sort()).toEqual(["archive/报告", "docs/报告"]);
  });
});

describe("pickSessionInWorkspace", () => {
  const sessions = [
    session({ id: "new", workspace_path: "/work/甲/", updated_at: 5 }),
    session({ id: "old", workspace_path: "/work/甲", updated_at: 1 }),
  ];

  it("prefers the remembered chat when it still exists", () => {
    expect(pickSessionInWorkspace(sessions, "/work/甲", "old")?.id).toBe("old");
  });

  it("falls back to the newest chat", () => {
    expect(pickSessionInWorkspace(sessions, "/work/甲", "missing")?.id).toBe("new");
  });
});

describe("sidebar memory", () => {
  it("restores the last folder when that folder still has chats", () => {
    const groups = groupSessionsByWorkspace([
      session({ id: "a", workspace_path: "/work/甲", updated_at: 1 }),
      session({ id: "b", workspace_path: "/work/乙", updated_at: 9 }),
    ]);
    const memory = withRememberedSession(
      { collapsed: [], archived: [], lastSessionByWorkspace: {}, lastWorkspace: null },
      "/work/甲",
      "a",
    );
    expect(pickRestoreWorkspace(groups, memory)).toBe("/work/甲");
    expect(memory.lastSessionByWorkspace["/work/甲"]).toBe("a");
    expect(memory.collapsed).toEqual([]);
  });

  it("toggles collapse without dropping the remembered chat", () => {
    const once = withToggledCollapse(
      { collapsed: [], archived: [], lastSessionByWorkspace: { "/work/甲": "a" }, lastWorkspace: "/work/甲" },
      "/work/甲/",
    );
    expect(once.collapsed).toEqual(["/work/甲"]);
    const twice = withToggledCollapse(once, "/work/甲");
    expect(twice.collapsed).toEqual([]);
    expect(twice.lastSessionByWorkspace["/work/甲"]).toBe("a");
  });

  it("ignores malformed storage", () => {
    expect(parseSidebarMemory(null).lastWorkspace).toBeNull();
    expect(parseSidebarMemory({ collapsed: [1, "/a/"], lastWorkspace: "" }).collapsed).toEqual(["/a"]);
  });

  it("treats trailing slashes as the same folder", () => {
    expect(pathsEqual("/work/甲/", "/work/甲")).toBe(true);
    expect(pathsEqual("/work/甲", "/work/乙")).toBe(false);
  });

  it("hides an archived folder without dropping its chats, and shows it again when reopened", () => {
    const sessions = [
      session({ id: "a", workspace_path: "/work/甲", updated_at: 2 }),
      session({ id: "b", workspace_path: "/work/乙", updated_at: 1 }),
    ];
    const base: SidebarMemory = {
      collapsed: [],
      archived: [],
      lastSessionByWorkspace: {},
      lastWorkspace: null,
    };
    const archived = withArchivedFolder(base, "/work/甲/");
    expect(visibleWorkspaceGroups(sessions, archived.archived).map((g) => g.path)).toEqual(["/work/乙"]);
    expect(sessions).toHaveLength(2);

    const reopened = withRememberedSession(archived, "/work/甲", "a");
    expect(visibleWorkspaceGroups(sessions, reopened.archived).map((g) => g.name)).toEqual(["甲", "乙"]);
    expect(pickRestoreWorkspace(visibleWorkspaceGroups(sessions, archived.archived), archived)).toBe("/work/乙");
  });
});
