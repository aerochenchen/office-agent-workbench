# 文书通

Tauri 2 + React + TypeScript 桌面壳。定位：**政务文书 · 智能通办**。  
三栏工作台：对话列表 | 对话 | Skill。  
UI 通过 `src/lib/runtimeClient.ts` 与本地 Python Runtime（`http://127.0.0.1:8765`）通信；
不直接联网、不直接读写文件系统——所有沙箱与工具调用都在 Runtime 侧完成。

## 目录结构

```
src/
  lib/
    runtimeClient.ts   # 与 Runtime HTTP API 对接的唯一入口
    tauri.ts           # Tauri 环境检测 + pick_folder 封装
    types.ts           # 共享类型
  components/
    WorkspaceTree.tsx  # 左栏：选择/展示工作区根目录内容
    ChatPanel.tsx       # 中栏：对话 + 工具调用状态行
    SkillPanel.tsx      # 右栏：Skill 列表、启停、安装
    SettingsModal.tsx   # 模型网关设置（api_base / api_key / model / allowed_hosts）
  styles/theme.css       # 全局色板 / 字号 / 间距 CSS 变量（唯一硬编码色值来源）
src-tauri/
  src/lib.rs             # `pick_folder` 命令 + 尝试自动拉起本地 Runtime（失败不影响 UI）
```

## 运行方式

### 推荐：一键启动

在仓库根目录执行：

```bash
./scripts/dev.sh           # Runtime + Vite + Tauri 桌面壳
./scripts/dev.sh --web     # Runtime + 浏览器前端（更快，适合打磨对话/工具）
./scripts/dev.sh --runtime # 仅 Runtime（改 Python 后热重载）
./scripts/dev-stop.sh      # 停掉 Runtime / Vite
```

日志在 `.dev/runtime.log`、`.dev/vite.log`。Runtime 开了 `--reload`，改 `runtime/src` 会自动重载。

窗口标题：**文书通**。首次 Tauri 编译较慢，之后会快很多。

浏览器模式（`--web`）没有原生选文件夹对话框，左侧可粘贴工作区绝对路径。

### 手动分终端（排障时用）

`tauri.conf.json` 中 `beforeDevCommand` 为空，避免与脚本抢 Vite 端口：

```bash
# A：Runtime
cd runtime && source .venv/bin/activate
uvicorn office_agent.app:app --app-dir src --host 127.0.0.1 --port 8765 --reload --reload-dir src

# B：Vite
cd apps/desktop && npx vite --host 127.0.0.1 --port 1420

# C：Tauri
source "$HOME/.cargo/env"
cd apps/desktop && npm run tauri -- dev
```

### 构建校验

```bash
npm run build   # tsc + vite build，产物在 dist/
```

### Windows 安装包

一键打出 NSIS `*-setup.exe`（含 Runtime sidecar）：

```powershell
# 仓库根目录
.\scripts\build-windows.ps1
```

说明见 [`packaging/README-standard.md`](../../packaging/README-standard.md)。

## 已知限制

- Skill 安装：桌面端点「选择安装包」→ 选文件夹或 zip/md；安装前预览名称/类型/权限。浏览器模式可用「高级：粘贴路径」。
- `/workspace/tree` 当前只返回工作区根目录的一层内容（无递归/展开），文件树暂不支持展开子目录；
  待 Runtime 增加带路径参数的接口后再补齐。
- 无流式配置回读以外，设置弹窗以覆盖式保存为主。
