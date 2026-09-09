/** Make Vite-injected stylesheets non-blocking so the inline splash can paint first. */
export function deferRenderBlockingStyles(html: string): string {
  return html.replace(/<link\s+rel="stylesheet"([^>]*?)>/gi, (match, attrs: string) => {
    if (/\bmedia\s*=/.test(attrs)) return match;
    return `<link rel="stylesheet"${attrs} media="print" onload="this.media='all'">`;
  });
}
