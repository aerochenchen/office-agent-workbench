/** Normalize a user-edited session title (mirrors runtime normalize_session_title). */
export const SESSION_TITLE_MAX_LEN = 80;
export const DEFAULT_SESSION_TITLE = "新对话";

export function normalizeSessionTitle(title: string): string {
  const cleaned = title.trim();
  if (!cleaned) return DEFAULT_SESSION_TITLE;
  if (cleaned.length > SESSION_TITLE_MAX_LEN) {
    return cleaned.slice(0, SESSION_TITLE_MAX_LEN);
  }
  return cleaned;
}
