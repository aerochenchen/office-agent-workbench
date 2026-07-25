/** True when running inside the Tauri shell (vs. plain `vite dev` in a browser tab). */
export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** Normalize separators and strip trailing slashes for prefix checks. */
export function normalizeFsPath(path: string): string {
  return path.replace(/\\/g, "/").replace(/\/+$/, "");
}

/** True when `filePath` is the workspace root or a path under it. */
export function isPathUnderWorkspace(filePath: string, workspacePath: string): boolean {
  const file = normalizeFsPath(filePath);
  const root = normalizeFsPath(workspacePath);
  if (!file || !root) return false;
  const fileKey = file.toLowerCase();
  const rootKey = root.toLowerCase();
  return fileKey === rootKey || fileKey.startsWith(`${rootKey}/`);
}

export function filterPathsUnderWorkspace(
  paths: string[],
  workspacePath: string,
): { accepted: string[]; rejected: string[] } {
  const accepted: string[] = [];
  const rejected: string[] = [];
  for (const raw of paths) {
    const path = raw.trim();
    if (!path) continue;
    if (isPathUnderWorkspace(path, workspacePath)) accepted.push(normalizeFsPath(path));
    else rejected.push(path);
  }
  return { accepted, rejected };
}

/** Parse absolute paths pasted one-per-line (browser fallback). */
export function parsePastedPaths(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

/**
 * Opens the native "choose folder" dialog via the Rust `pick_folder`
 * command. Returns `null` when unavailable (browser dev mode) or cancelled.
 */
export async function pickFolder(): Promise<string | null> {
  if (!isTauriRuntime()) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  const result = await invoke<string | null>("pick_folder");
  return result ?? null;
}

/** Pick a Skill zip or markdown file. Browser mode returns null. */
export async function pickSkillFile(): Promise<string | null> {
  if (!isTauriRuntime()) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  const result = await invoke<string | null>("pick_skill_file");
  return result ?? null;
}

/**
 * Multi-select files via `@tauri-apps/plugin-dialog`.
 * Returns `null` when cancelled or unavailable (browser / non-Tauri).
 */
export async function pickFiles(options?: {
  defaultPath?: string;
  title?: string;
}): Promise<string[] | null> {
  if (!isTauriRuntime()) return null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    multiple: true,
    directory: false,
    defaultPath: options?.defaultPath,
    title: options?.title ?? "选择附件",
  });
  if (selected === null) return null;
  return Array.isArray(selected) ? selected : [selected];
}
