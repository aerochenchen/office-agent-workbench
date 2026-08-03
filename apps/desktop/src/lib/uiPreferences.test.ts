// @vitest-environment jsdom
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import {
  applyUiFontScale,
  isUiFontScale,
  readUiFontScale,
  writeUiFontScale,
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
  });

  afterEach(() => {
    store.clear();
    document.documentElement.removeAttribute("data-ui-scale");
    vi.unstubAllGlobals();
  });

  it("defaults to md when unset", () => {
    expect(readUiFontScale()).toBe("md");
  });

  it("persists and reads font scale", () => {
    writeUiFontScale("lg");
    expect(readUiFontScale()).toBe("lg");
    expect(isUiFontScale("lg")).toBe(true);
    expect(isUiFontScale("xl")).toBe(false);
  });

  it("applies data-ui-scale on html", () => {
    applyUiFontScale("sm");
    expect(document.documentElement.dataset.uiScale).toBe("sm");
  });
});
