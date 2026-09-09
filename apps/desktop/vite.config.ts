import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { deferRenderBlockingStyles } from "./src/lib/deferRenderBlockingStyles";

function deferStylesheetPlugin(): Plugin {
  return {
    name: "defer-render-blocking-styles",
    apply: "build",
    transformIndexHtml: {
      order: "post",
      handler(html) {
        return deferRenderBlockingStyles(html);
      },
    },
  };
}

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;

// https://vite.dev/config/
export default defineConfig(async () => ({
  plugins: [react(), deferStylesheetPlugin()],

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
  },
}));
