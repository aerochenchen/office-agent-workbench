# Task 7 Report: Tauri desktop workbench (M0 UI)

**Status:** DONE (前端完整；Tauri 原生构建未在本机验证，因缺 Rust) | **Commits:** none | **Date:** 2026-07-23

## Delivered

- `apps/desktop/` — `npm create tauri-app@latest --template react-ts` 脚手架 + 三栏工作台改造。
- `src/lib/runtimeClient.ts` — `health/openWorkspace/getTree/listSkills/installSkill/setEnabled/saveConfig/chat`，统一 fetch 封装（超时、错误信息透传 `detail`），固定指向 `http://127.0.0.1:8765`。
- `src/lib/tauri.ts` — `isTauriRuntime()` + `pickFolder()`；浏览器 dev 模式下自动降级为路径输入框。
- `src/components/`：`WorkspaceTree`（选择/打开工作区、根目录列表）、`ChatPanel`（消息淡入、tool_events 细分割线状态行）、`SkillPanel`（tier 徽标、heavy 的 `min_ram_gb` 安装后 `confirm()` 提示）、`SettingsModal`（api_base/api_key/model/allowed_hosts）。
- `src/styles/theme.css` — 冷灰纸感色板 + 中文字体栈 + 间距/圆角变量，禁止组件内硬编码色值；顶栏产品名「办公智能体工作台」。
- `src-tauri/`：新增 `pick_folder` 命令（`tauri-plugin-dialog`）；`setup()` 中 best-effort 从 `../../../runtime/.venv` 自动拉起 `uvicorn`，失败仅打日志不影响 UI；窗口关闭时尝试 kill 子进程。`tauri.conf.json` 更新窗口标题/尺寸与 `productName`。

## Verify

- `npm run build`（`tsc && vite build`）：**通过**，产物 `dist/`。
- `ReadLints`：无报错。
- 本机无 `cargo`/`rustc`，`tauri dev`/`tauri build` **未能实际执行**；改用 `npm run dev`（vite，`http://localhost:1420`）+ 手动启 Runtime（`uvicorn ... --port 8765`）做前后端联调：`curl /health` → `{"ok":true}`；`/workspace/open`→`/workspace/tree` 返回临时目录文件列表，字段与 `TreeEntry` 一致。
- 浏览器端到端交互（点击/截图）因本环境浏览器 MCP 工具当前不可用（`browser_navigate` 报 "No browser tab available"）未能完成，已改用 curl 校验 API 契约替代。

## Follow-ups

- `/workspace/tree` 无路径参数，暂不支持子目录展开，README 已注明；后续若 Runtime 加带 `path` 的接口可补齐。
- 无 `GET /config`，设置弹窗为覆盖式保存，不能回显 Runtime 当前配置。
- 需在有 Rust 工具链的机器上补跑一次 `npm run tauri dev` / `tauri build` 做真机验证。
