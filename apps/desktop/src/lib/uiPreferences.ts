/** Shell-only UI preferences (not Runtime / model gateway config). */

export type UiFontScale = "sm" | "md" | "lg";

const FONT_SCALE_KEY = "wenshutong.ui.fontScale";

export const UI_FONT_SCALE_OPTIONS: ReadonlyArray<{
  value: UiFontScale;
  label: string;
  hint: string;
}> = [
  { value: "sm", label: "小", hint: "界面更紧凑" },
  { value: "md", label: "标准", hint: "默认大小" },
  { value: "lg", label: "大", hint: "文字更易读" },
];

export function isUiFontScale(value: string): value is UiFontScale {
  return value === "sm" || value === "md" || value === "lg";
}

export function readUiFontScale(): UiFontScale {
  try {
    const raw = localStorage.getItem(FONT_SCALE_KEY);
    if (raw && isUiFontScale(raw)) return raw;
  } catch {
    /* private mode / unavailable */
  }
  return "md";
}

export function writeUiFontScale(scale: UiFontScale): void {
  try {
    localStorage.setItem(FONT_SCALE_KEY, scale);
  } catch {
    /* ignore */
  }
}

/** Apply scale via html[data-ui-scale]; theme.css maps tokens. */
export function applyUiFontScale(scale: UiFontScale): void {
  document.documentElement.dataset.uiScale = scale;
}

export function initUiPreferences(): UiFontScale {
  const scale = readUiFontScale();
  applyUiFontScale(scale);
  return scale;
}
