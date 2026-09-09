import { describe, expect, it } from "vitest";
import { deferRenderBlockingStyles } from "./deferRenderBlockingStyles";

describe("deferRenderBlockingStyles", () => {
  it("makes production stylesheets non-blocking", () => {
    const html =
      '<head><link rel="stylesheet" crossorigin href="/assets/index.css"></head>' +
      '<body><div id="boot-splash"></div></body>';
    const out = deferRenderBlockingStyles(html);
    expect(out).toContain('href="/assets/index.css"');
    expect(out).toMatch(/href="\/assets\/index\.css"[^>]*media="print"/);
    expect(out).toContain("this.media='all'");
  });

  it("leaves already-deferred stylesheets alone", () => {
    const html =
      '<link rel="stylesheet" href="/a.css" media="print" onload="this.media=\'all\'">';
    expect(deferRenderBlockingStyles(html)).toBe(html);
  });
});
