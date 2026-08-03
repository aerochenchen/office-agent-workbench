/** Shell-only UI preferences (not Runtime / model gateway config). */

export type UiFontScale = "sm" | "md" | "lg";
export type UiTheme = "default" | "deeper" | "paper";

const FONT_SCALE_KEY = "wenshutong.ui.fontScale";
const THEME_KEY = "wenshutong.ui.theme";

export const UI_FONT_SCALE_OPTIONS: ReadonlyArray<{
  value: UiFontScale;
  label: string;
  hint: string;
}> = [
  { value: "sm", label: "小", hint: "界面更紧凑" },
  { value: "md", label: "标准", hint: "默认大小" },
  { value: "lg", label: "大", hint: "文字更易读" },
];

export const UI_THEME_OPTIONS: ReadonlyArray<{
  value: UiTheme;
  label: string;
  hint: string;
}> = [
  { value: "default", label: "素笺", hint: "素净宣纸感，冷灰日间默认" },
  { value: "deeper", label: "黛青", hint: "略沉的青墨底色，仍适合日间办公" },
  { value: "paper", label: "竹纸", hint: "暖米色竹纸感，长时间阅读更柔和" },
];

export function isUiFontScale(value: string): value is UiFontScale {
  return value === "sm" || value === "md" || value === "lg";
}

export function isUiTheme(value: string): value is UiTheme {
  return value === "default" || value === "deeper" || value === "paper";
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

export function readUiTheme(): UiTheme {
  try {
    const raw = localStorage.getItem(THEME_KEY);
    if (raw && isUiTheme(raw)) return raw;
  } catch {
    /* private mode / unavailable */
  }
  return "default";
}

export function writeUiTheme(theme: UiTheme): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* ignore */
  }
}

/** Apply theme via html[data-ui-theme]; theme.css maps color tokens. */
export function applyUiTheme(theme: UiTheme): void {
  document.documentElement.dataset.uiTheme = theme;
}

export function initUiPreferences(): { fontScale: UiFontScale; theme: UiTheme } {
  const fontScale = readUiFontScale();
  const theme = readUiTheme();
  applyUiFontScale(fontScale);
  applyUiTheme(theme);
  return { fontScale, theme };
}
