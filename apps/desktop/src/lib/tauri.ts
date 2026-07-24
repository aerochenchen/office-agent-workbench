/** True when running inside the Tauri shell (vs. plain `vite dev` in a browser tab). */
export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
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
