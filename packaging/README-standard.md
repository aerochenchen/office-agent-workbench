# 标准底座安装包

面向内网办公场景的默认交付物：**不含** PyTorch / sentence-transformers / transformers 等写作 RAG 重依赖。

## 包内内容

| 组件 | 说明 |
|------|------|
| `apps/desktop/` | Tauri 2 + React 工作台（工作区、对话、Skill 面板） |
| `runtime/` | 本地 Python Runtime（FastAPI，127.0.0.1），轻量 `requirements.txt` |
| `bundled/skills/` | 预置轻量 Skill（`tier: light`）：`government-document-format` 公文排版、`multidoc-digest` 多份汇总、`office-visual-design` 正式配色、`doc-proofread` 通篇校对、`doc-diff-review` 文稿对照、`meeting-followup` 会议督办、`material-gap` 材料摸底、`sheet-to-brief` 表格成文、`one-to-three` 一文三用、`brief-deck` 汇报成套、`chart-generation` 图表生成、`skill-builder` 创建技能 |
| `bundled/shared-scripts/` | 共享脚本：`format_gongwen`（排版）、`docx_diff`（两版段落对比） |

标准包**不包含** `optional-skills/gongwen-rag-writing/`、离线 embedding 模型或 Torch 运行时。

## Windows 安装包（推荐交付物）

交付文件为 **NSIS 安装器**：`文书通_0.1.0_x64-setup.exe`（版本号随 `tauri.conf.json` 变化；旧版曾用「办公智能体工作台」命名）。

### 架构

1. **桌面壳**：Tauri 打包的主程序  
2. **Runtime sidecar**：PyInstaller **onedir** 产物 `office-agent-runtime.exe`（随安装目录 `resources/runtime/`）  
3. **预置 Skill**：`resources/bundled/`（启动时 seed 到用户 `~/.office-agent`）  

写作 RAG 仍用 zip 选装，见 [写作 RAG 可选包](./README-writing-rag-optional.md)。

### 从源码打出 setup.exe

**机器要求（构建机）**

- Windows 10+
- Python 3.11+
- Node.js / npm
- Rust（`rustup`，MSVC toolchain）
- 首次构建需能下载 crates / npm（内网需镜像）

**一键构建**

在仓库根目录 PowerShell：

```powershell
.\scripts\build-windows.ps1
```

常用参数：

| 参数 | 含义 |
|------|------|
| `-Clean` | 清掉 packaging venv / PyInstaller 中间产物后重打 |
| `-SkipSidecar` | 跳过 PyInstaller（需已有 staged `src-tauri/resources/runtime`） |
| `-SkipTauri` | 只打 sidecar 并 stage resources，不跑 `tauri build` |

产物路径：

```
apps/desktop/src-tauri/target/release/bundle/nsis/*-setup.exe
```

### 用 GitHub Actions 打安装包（无需本机 Windows）

仓库提供手动触发流水线 [`.github/workflows/build-windows.yml`](../.github/workflows/build-windows.yml)：

1. 将代码推到 GitHub。
2. 打开仓库 **Actions** → **Build Windows Installer** → **Run workflow**（选分支后运行）。
3. 等待 `windows-latest` 跑完 `.\scripts\build-windows.ps1`。
4. 在该次 run 页面底部 **Artifacts** 下载 `wenshutong-windows-nsis`（内含 `*-setup.exe`；默认保留 14 天）。

也可在本机用 GitHub CLI：`gh workflow run "Build Windows Installer"`，完成后 `gh run download`。

验收步骤见 [VERIFY-windows.md](./VERIFY-windows.md)。

## macOS 内测 DMG

**内测用，不做 Apple 公证。** 在 **Apple Silicon / Intel Mac** 上可打出未签名/未公证的盘镜像（含 Runtime sidecar），供笔记本或另一台 Mac 验收。

```bash
./scripts/build-macos.sh
# 可选：--clean / --skip-sidecar / --skip-tauri
```

产物：

```
apps/desktop/src-tauri/target/release/bundle/dmg/*.dmg
packaging/dist/mac/*.dmg          # 脚本额外拷贝的便捷路径
```

说明：本路径仅面向内测，**不做公证**；测试机首次打开请在 Finder 中右键「打开」。正式对外分发需另行 Developer ID 签名与 notarize。

中间产物（不进 git）：

- `packaging/dist/office-agent-runtime/` — PyInstaller onedir  
- `apps/desktop/src-tauri/resources/runtime/` — 供 Tauri 打进安装包  
- `apps/desktop/src-tauri/resources/bundled/` — 预置 Skill 拷贝  

### 安装与运行（终端用户）

1. 双击 `*-setup.exe`（默认当前用户安装）。  
2. 若本机无 WebView2，安装器会走 **嵌入式 bootstrapper**（不依赖安装时访问公网下载页；仍建议机关镜像预装 WebView2）。  
3. 启动「文书通」：壳自动拉起 sidecar（`127.0.0.1:8765`）。  
4. 用户数据与会话在 `%USERPROFILE%\.office-agent\`；**卸载安装包不会删除**该目录。  
5. 额外 Skill 通过 Tauri 桌面端 UI「导入技能」（文件夹 / zip / md）安装，不影响标准包体积。

### 体积与基线

- **最低**：Windows 10+，约 **4GB** 内存 — 底座对话 + 轻量 Skill。  
- 安装包体积主要来自 PyInstaller Runtime + WebView2 bootstrapper；发版前在构建机记录实际 MB 数。  
- 启用重量级写作 RAG 请改用 [写作 RAG 可选包](./README-writing-rag-optional.md)（建议 **8GB** 内存）。

## 开发态（非安装包）

开发仍用仓库内 `runtime/.venv` + `./scripts/dev.sh`（或 Windows 下等价手动启动）。Debug 构建的 Tauri 壳会优先走 `.venv`，无需每次重打 sidecar。

正式 CLI：

```bash
cd runtime
.venv\Scripts\python.exe -m office_agent --host 127.0.0.1 --port 8765
```

## 依赖原则

- `runtime/requirements.txt` 仅声明 FastAPI、uvicorn、openai、pydantic、PyYAML、httpx 等轻依赖。  
- 发版前**必须**在仓库根目录依次执行：
  1. `./scripts/check_licenses.sh` — 扫描 `runtime/.venv`（Python）与 `apps/desktop`（npm），GPL/AGPL 失败退出；LGPL 允许。
  2. `./scripts/generate_notice.sh` — 生成/更新仓库根 `NOTICE`（人类可读的 Python + npm 摘要），并由打包脚本随标准包分发。
- `packaging/.venv` 用于 PyInstaller sidecar；若与 runtime 依赖不一致，可在该 venv 上单独跑 `pip-licenses` 复核。  
- 运行时仅允许白名单内网 API Host；Skill/模型禁止运行时从公网下载。

## 手动 / 解压式安装（运维备选）

若不便使用 NSIS：

1. 解压或安装标准底座到目标目录。  
2. 创建并填充 `runtime/.venv`（`pip install -e runtime`）。  
3. 启动桌面壳；Runtime 由 Tauri 拉起或按文档独立启动。  

详细联调步骤见 `apps/desktop/README.md` 与 `docs/superpowers/specs/2026-07-23-office-agent-runtime-design.md`。
