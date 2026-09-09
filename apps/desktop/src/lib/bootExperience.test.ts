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

  it("shows the window immediately with paper background", () => {
    const conf = JSON.parse(read("src-tauri/tauri.conf.json")) as {
      app: {
        withGlobalTauri?: boolean;
        windows: Array<{ visible?: boolean; backgroundColor?: string }>;
      };
    };
    expect(conf.app.windows[0].visible).not.toBe(false);
    expect(conf.app.windows[0].backgroundColor).toBe("#f3f4f1");
    expect(conf.app.withGlobalTauri).not.toBe(true);
  });

  it("does not defer production CSS with print media", () => {
    expect(read("vite.config.ts")).not.toContain("deferRenderBlockingStyles");
    expect(read("vite.config.ts")).not.toContain("media=\"print\"");
  });

  it("keeps paper-colored html/body behind the splash", () => {
    const html = read("index.html");
    expect(html).toMatch(/html,\s*body[\s\S]*background:\s*#f3f4f1/);
    expect(html).toContain("正在启动本地运行组件");
  });
});
