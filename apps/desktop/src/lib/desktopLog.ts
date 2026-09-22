/** Build a desktop-shell JSONL payload (redaction for tests / invoke shape). */

const FORBIDDEN = new Set(["api_key", "key", "token", "password", "passwd", "messages", "content"]);

export type DesktopLogInput = {
  event: string;
  bootId: string;
  level?: string;
  extra?: Record<string, unknown>;
};

/** One JSON object line matching Rust `log_event` field shape (no trailing newline). */
export function desktopLogLine(input: DesktopLogInput): string {
  const row: Record<string, unknown> = {
    ts: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    level: input.level ?? "info",
    event: input.event,
    boot_id: input.bootId,
  };
  if (input.extra) {
    for (const [key, value] of Object.entries(input.extra)) {
      if (FORBIDDEN.has(key) || key in row) continue;
      if (value === undefined || value === null) continue;
      row[key] = value;
    }
  }
  return JSON.stringify(row);
}
