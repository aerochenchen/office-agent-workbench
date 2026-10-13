import type { SessionMeta } from "./types";

/** Application-scoped sidebar memory. Survives folder switches and restarts. */
const STORAGE_KEY = "wenshutong.sidebar.v1";

export interface WorkspaceGroup {
  /** Path string stored on the newest chat; pass this to open the folder. */
  path: string;
  name: string;
  updatedAt: number;
  sessions: SessionMeta[];
}

export interface SidebarMemory {
  /** Normalized folder keys the user collapsed. */
  collapsed: string[];
  /** Normalized folder keys hidden from the sidebar. Chats stay in the session store. */
  archived: string[];
  /** Normalized folder key → last opened chat id. */
  lastSessionByWorkspace: Record<string, string>;
  /** Last folder the user was working in. */
  lastWorkspace: string | null;
}

const EMPTY_MEMORY: SidebarMemory = {
  collapsed: [],
  archived: [],
  lastSessionByWorkspace: {},
  lastWorkspace: null,
};

export function normalizeWorkspaceKey(path: string): string {
  const slash = path.trim().replace(/\\/g, "/").replace(/\/+$/, "");
  return slash || path.trim();
}

export function pathsEqual(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  return normalizeWorkspaceKey(a) === normalizeWorkspaceKey(b);
}

export function workspaceBasename(path: string): string {
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts.pop() || path;
}

function parentBasename(path: string): string {
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  if (parts.length < 2) return "";
  return parts[parts.length - 2] || "";
}

/** Same folder name in two places shows the parent, so the rows stay distinct. */
export function workspaceDisplayName(path: string, allPaths: readonly string[]): string {
  const name = workspaceBasename(path);
  const dupes = allPaths.filter((p) => workspaceBasename(p) === name);
  if (dupes.length <= 1) return name;
  const parent = parentBasename(path);
  return parent ? `${parent}/${name}` : name;
}

function byRecent(a: SessionMeta, b: SessionMeta): number {
  const updated = (b.updated_at || 0) - (a.updated_at || 0);
  if (updated !== 0) return updated;
  return (b.created_at || 0) - (a.created_at || 0);
}

/**
 * Group chats under their folders. Chats with no folder stay out of the list.
 * Folders are ordered by the newest chat, chats inside a folder the same way.
 */
export function groupSessionsByWorkspace(sessions: readonly SessionMeta[]): WorkspaceGroup[] {
  const buckets = new Map<string, SessionMeta[]>();
  for (const session of sessions) {
    const raw = (session.workspace_path || "").trim();
    if (!raw) continue;
    const key = normalizeWorkspaceKey(raw);
    const list = buckets.get(key);
    if (list) list.push(session);
    else buckets.set(key, [session]);
  }

  const groups: WorkspaceGroup[] = [];
  for (const list of buckets.values()) {
    const sessionsSorted = [...list].sort(byRecent);
    const path = sessionsSorted[0]?.workspace_path || "";
    if (!path) continue;
    groups.push({
      path,
      name: workspaceBasename(path),
      updatedAt: sessionsSorted[0]?.updated_at || 0,
      sessions: sessionsSorted,
    });
  }

  groups.sort((a, b) => {
    const updated = b.updatedAt - a.updatedAt;
    if (updated !== 0) return updated;
    return a.path.localeCompare(b.path);
  });

  const paths = groups.map((g) => g.path);
  return groups.map((g) => ({ ...g, name: workspaceDisplayName(g.path, paths) }));
}

export function pickSessionInWorkspace(
  sessions: readonly SessionMeta[],
  workspacePath: string,
  preferredId?: string | null,
): SessionMeta | null {
  const key = normalizeWorkspaceKey(workspacePath);
  const inFolder = sessions.filter(
    (s) => s.workspace_path && normalizeWorkspaceKey(s.workspace_path) === key,
  );
  if (inFolder.length === 0) return null;
  if (preferredId) {
    const hit = inFolder.find((s) => s.id === preferredId);
    if (hit) return hit;
  }
  return [...inFolder].sort(byRecent)[0] ?? null;
}

/** Sidebar rows only. Archived folders stay out until that folder is opened again. */
export function visibleWorkspaceGroups(
  sessions: readonly SessionMeta[],
  archived: readonly string[],
): WorkspaceGroup[] {
  const hidden = new Set(archived.map(normalizeWorkspaceKey));
  const visible = sessions.filter((session) => {
    const raw = (session.workspace_path || "").trim();
    if (!raw) return false;
    return !hidden.has(normalizeWorkspaceKey(raw));
  });
  return groupSessionsByWorkspace(visible);
}

export function pickRestoreWorkspace(
  groups: readonly WorkspaceGroup[],
  memory: SidebarMemory,
): string | null {
  if (memory.lastWorkspace) {
    const hit = groups.find((g) => pathsEqual(g.path, memory.lastWorkspace));
    if (hit) return hit.path;
  }
  return groups[0]?.path ?? null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

export function parseSidebarMemory(raw: unknown): SidebarMemory {
  if (!isRecord(raw)) return { ...EMPTY_MEMORY, lastSessionByWorkspace: {} };
  const collapsed = stringList(raw.collapsed);
  const archived = stringList(raw.archived);
  const lastSessionByWorkspace: Record<string, string> = {};
  if (isRecord(raw.lastSessionByWorkspace)) {
    for (const [key, value] of Object.entries(raw.lastSessionByWorkspace)) {
      if (typeof value === "string" && value) {
        lastSessionByWorkspace[normalizeWorkspaceKey(key)] = value;
      }
    }
  }
  const lastWorkspace = typeof raw.lastWorkspace === "string" && raw.lastWorkspace
    ? raw.lastWorkspace
    : null;
  return {
    collapsed: [...new Set(collapsed.map(normalizeWorkspaceKey))],
    archived: [...new Set(archived.map(normalizeWorkspaceKey))],
    lastSessionByWorkspace,
    lastWorkspace,
  };
}

export function readSidebarMemory(): SidebarMemory {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...EMPTY_MEMORY, lastSessionByWorkspace: {}, archived: [] };
    return parseSidebarMemory(JSON.parse(raw));
  } catch {
    return { ...EMPTY_MEMORY, lastSessionByWorkspace: {}, archived: [] };
  }
}

export function writeSidebarMemory(memory: SidebarMemory): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(memory));
  } catch {
    /* private mode / unavailable */
  }
}

export function withRememberedSession(
  memory: SidebarMemory,
  workspacePath: string,
  sessionId: string,
): SidebarMemory {
  const key = normalizeWorkspaceKey(workspacePath);
  return {
    ...memory,
    lastWorkspace: workspacePath,
    lastSessionByWorkspace: { ...memory.lastSessionByWorkspace, [key]: sessionId },
    collapsed: memory.collapsed.filter((item) => item !== key),
    archived: memory.archived.filter((item) => item !== key),
  };
}

export function withArchivedFolder(memory: SidebarMemory, workspacePath: string): SidebarMemory {
  const key = normalizeWorkspaceKey(workspacePath);
  if (memory.archived.includes(key)) return memory;
  return { ...memory, archived: [...memory.archived, key] };
}

export function withToggledCollapse(memory: SidebarMemory, workspacePath: string): SidebarMemory {
  const key = normalizeWorkspaceKey(workspacePath);
  const collapsed = memory.collapsed.includes(key)
    ? memory.collapsed.filter((item) => item !== key)
    : [...memory.collapsed, key];
  return { ...memory, collapsed };
}
