import { isTauriRuntime } from "./tauri";

/** Show the main window after the inline splash can paint. No-op in browser dev. */
export async function revealMainWindow(): Promise<void> {
  if (!isTauriRuntime()) return;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().show();
  } catch {
    // Rust 8s fallback still shows the window if this IPC is unavailable.
  }
}
