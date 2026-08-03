// @vitest-environment jsdom
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import {
  applyUiFontScale,
  applyUiTheme,
  isUiFontScale,
  isUiTheme,
  readUiFontScale,
  readUiTheme,
  writeUiFontScale,
  writeUiTheme,
} from "./uiPreferences";

const store = new Map<string, string>();

const localStorageMock = {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => {
    store.set(key, value);
  },
  clear: () => {
    store.clear();
  },
  removeItem: (key: string) => {
    store.delete(key);
  },
};

describe("uiPreferences", () => {
  beforeEach(() => {
    store.clear();
    vi.stubGlobal("localStorage", localStorageMock);
    document.documentElement.removeAttribute("data-ui-scale");
    document.documentElement.removeAttribute("data-ui-theme");
  });

  afterEach(() => {
    store.clear();
    document.documentElement.removeAttribute("data-ui-scale");
    document.documentElement.removeAttribute("data-ui-theme");
    vi.unstubAllGlobals();
  });

  it("defaults to md / default when unset", () => {
    expect(readUiFontScale()).toBe("md");
    expect(readUiTheme()).toBe("default");
  });

  it("persists and reads font scale", () => {
    writeUiFontScale("lg");
    expect(readUiFontScale()).toBe("lg");
    expect(isUiFontScale("lg")).toBe(true);
    expect(isUiFontScale("xl")).toBe(false);
  });

  it("persists and reads theme", () => {
    writeUiTheme("paper");
    expect(readUiTheme()).toBe("paper");
    expect(isUiTheme("deeper")).toBe(true);
    expect(isUiTheme("dark")).toBe(false);
  });

  it("applies data attributes on html", () => {
    applyUiFontScale("sm");
    applyUiTheme("deeper");
    expect(document.documentElement.dataset.uiScale).toBe("sm");
    expect(document.documentElement.dataset.uiTheme).toBe("deeper");
  });
});
