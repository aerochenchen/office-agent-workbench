import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = fileURLToPath(new URL(".", import.meta.url));
const desktopRoot = resolve(here, "../..");

function read(rel: string): string {
  return readFileSync(resolve(desktopRoot, rel), "utf8");
}

describe("boot experience wiring", () => {
  it("does not dismiss splash from main mount", () => {
    expect(read("src/main.tsx")).not.toMatch(/dismissBootSplash\s*\(/);
  });

  it("dismisses splash from health in App", () => {
    const app = read("src/App.tsx");
    expect(app).toContain("shouldDismissBootSplash");
    expect(app).toContain("dismissBootSplash");
  });

  it("hides the main window until splash can paint", () => {
    const conf = JSON.parse(read("src-tauri/tauri.conf.json")) as {
      app: {
        withGlobalTauri?: boolean;
        windows: Array<{ visible?: boolean; backgroundColor?: string }>;
      };
    };
    expect(conf.app.windows[0].visible).toBe(false);
    expect(conf.app.windows[0].backgroundColor).toBe("#f3f4f1");
    expect(conf.app.withGlobalTauri).toBe(true);
  });

  it("allows the frontend to show the window", () => {
    const caps = JSON.parse(read("src-tauri/capabilities/default.json")) as {
      permissions: unknown[];
    };
    expect(caps.permissions).toContain("core:window:allow-show");
  });

  it("reveals the window from the inline splash script", () => {
    const html = read("index.html");
    expect(html).toContain("__TAURI__");
    expect(html).toMatch(/getCurrentWindow\(\)\.show\(\)/);
    expect(html).toMatch(/html,\s*body[\s\S]*background:\s*#f3f4f1/);
  });
});
