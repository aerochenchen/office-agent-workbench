/** Product brand — single source for window chrome and in-app UI. */
export const APP_NAME = "文书通";
/** Positioning line under the product name (not a second product title). */
export const APP_TAGLINE = "办公文书 · 智能通办";
/** macOS / Windows window title — keep short to avoid duplicating the in-app brand block. */
export const WINDOW_TITLE = APP_NAME;
/** Shown in About; keep in sync with package.json / tauri.conf.json version. */
export const APP_VERSION = "0.1.0";

/** Support / AI-content report mailbox (Store 11.16). */
export const SUPPORT_EMAIL = "wenshutongapp@163.com";

/** Key OSS attributions for the in-app About block (full list ships as NOTICE). */
export const OSS_CREDITS: ReadonlyArray<{ name: string; license: string }> = [
  { name: "Tauri", license: "Apache-2.0 / MIT" },
  { name: "React", license: "MIT" },
  { name: "FastAPI", license: "MIT" },
  { name: "OpenAI SDK", license: "Apache-2.0" },
];
