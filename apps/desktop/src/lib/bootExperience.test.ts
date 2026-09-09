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

  it("hides main until page load and keeps paper background", () => {
    const conf = JSON.parse(read("src-tauri/tauri.conf.json")) as {
      app: {
        windows: Array<{ visible?: boolean; backgroundColor?: string }>;
      };
    };
    expect(conf.app.windows[0].visible).toBe(false);
    expect(conf.app.windows[0].backgroundColor).toBe("#f3f4f1");
  });

  it("wires a Windows native splash with spinner before WebView", () => {
    const lib = read("src-tauri/src/lib.rs");
    expect(lib).toContain("mod native_splash");
    expect(lib).toContain("native_splash::show");
    expect(lib).toContain("reveal_main_window");
    expect(lib).toContain("PageLoadEvent::Finished");

    const splash = read("src-tauri/src/native_splash.rs");
    expect(splash).toContain("正在启动本地运行组件");
    expect(splash).toContain("AngleArc");
    expect(splash).toContain("文书通");
  });

  it("keeps paper-colored html/body behind the HTML splash", () => {
    const html = read("index.html");
    expect(html).toMatch(/html,\s*body[\s\S]*background:\s*#f3f4f1/);
    expect(html).toContain("正在启动本地运行组件");
  });
});
