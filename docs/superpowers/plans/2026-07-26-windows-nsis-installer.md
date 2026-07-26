# Windows 标准底座 NSIS 安装包 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本机打出标准底座 `文书通_0.1.0_x64-setup.exe`，安装器与桌面应用共用 `icon.ico`。

**Architecture:** 不改打包逻辑。补齐 Rust MSVC 后运行仓库 `scripts/build-windows.ps1`：PyInstaller sidecar → stage resources → `tauri build`（NSIS）。图标已由 `tauri.conf.json` 配置。

**Tech Stack:** Python 3.11+、PyInstaller、Node/npm、Tauri 2、Rust `x86_64-pc-windows-msvc`、NSIS（由 Tauri 拉取）

## Global Constraints

- 交付：标准底座 NSIS；不含写作 RAG 重依赖
- 图标：沿用 `apps/desktop/src-tauri/icons/icon.ico`（源图 `branding/app-icon.png`）
- 安装模式：保持 `currentUser`；不签名
- 不擅自 git commit（除非用户明确要求）
- 规格：`docs/superpowers/specs/2026-07-26-windows-nsis-installer-design.md`

---

## File map（本计划几乎只读既有文件）

| 路径 | 职责 |
|------|------|
| `scripts/build-windows.ps1` | 一键构建 |
| `apps/desktop/src-tauri/tauri.conf.json` | NSIS + 图标配置（不改） |
| `apps/desktop/src-tauri/icons/icon.ico` | 应用/安装器图标（不改） |
| `packaging/runtime.spec` | PyInstaller 规格 |
| `NOTICE` | 须存在并被 stage |
| 产物：`apps/desktop/src-tauri/target/release/bundle/nsis/*-setup.exe` | 交付物 |

---

### Task 1: 安装并校验 Rust MSVC toolchain

**Files:**
- 无仓库文件修改

**Interfaces:**
- Produces: PATH 上可用的 `rustc`、`cargo`（host `x86_64-pc-windows-msvc`）

- [ ] **Step 1: 检测是否已有 rustc**

Run (PowerShell):
```powershell
Get-Command rustc -ErrorAction SilentlyContinue
Get-Command cargo -ErrorAction SilentlyContinue
```
Expected: 若均缺失则继续 Step 2；若已存在则跳到 Step 3。

- [ ] **Step 2: 静默安装 rustup（默认 MSVC host）**

Run:
```powershell
Invoke-WebRequest -Uri "https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe" -OutFile "$env:TEMP\rustup-init.exe"
& "$env:TEMP\rustup-init.exe" -y --default-toolchain stable --default-host x86_64-pc-windows-msvc
$env:Path = "$env:USERPROFILE\.cargo\bin;" + $env:Path
```
Expected: 退出码 0；`~/.cargo/bin` 出现 `rustc.exe`、`cargo.exe`。

若链接阶段失败（缺少 `link.exe`），安装 Visual Studio Build Tools「使用 C++ 的桌面开发」或等价组件后重试 Task 2。

- [ ] **Step 3: 校验版本**

Run:
```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;" + $env:Path
rustc --version
cargo --version
```
Expected: 打印 `rustc` / `cargo` 版本号，无 CommandNotFound。

---

### Task 2: 校验前置依赖与 NOTICE

**Files:**
- Read: `NOTICE`（仓库根）
- Read: `apps/desktop/src-tauri/icons/icon.ico`
- Read: `apps/desktop/src-tauri/tauri.conf.json`（确认 `targets: ["nsis"]` 与 `installerIcon`）

**Interfaces:**
- Consumes: Task 1 的 toolchain
- Produces: 构建前置检查通过的确认

- [ ] **Step 1: 检查 Python / Node / 图标 / NOTICE / 配置**

Run:
```powershell
python --version
node --version
npm --version
Test-Path "NOTICE"
Test-Path "apps\desktop\src-tauri\icons\icon.ico"
Select-String -Path "apps\desktop\src-tauri\tauri.conf.json" -Pattern "nsis|installerIcon|icon.ico"
```
Expected: Python ≥3.11；Node/npm 可用；`NOTICE` 与 `icon.ico` 为 True；配置含 `nsis` 与 `installerIcon` → `icons/icon.ico`。

---

### Task 3: 执行标准底座一键构建

**Files:**
- 生成（不入库）：`packaging/.venv/`、`packaging/dist/office-agent-runtime/`、`apps/desktop/src-tauri/resources/runtime/`、`apps/desktop/src-tauri/resources/bundled/`、`apps/desktop/src-tauri/target/`

**Interfaces:**
- Consumes: Task 1–2 通过
- Produces: `apps/desktop/src-tauri/target/release/bundle/nsis/文书通_0.1.0_x64-setup.exe`（或同目录 `*-setup.exe`）

- [ ] **Step 1: 运行构建脚本**

Run（仓库根）:
```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;" + $env:Path
.\scripts\build-windows.ps1
```
Expected: 脚本正常结束；日志出现 `Installer: ...\*-setup.exe`。

- [ ] **Step 2: 确认产物文件**

Run:
```powershell
Get-ChildItem "apps\desktop\src-tauri\target\release\bundle\nsis\*-setup.exe" | Format-Table Name, Length, FullName
```
Expected: 至少一个 `*-setup.exe`，体积显著大于空壳（含 Runtime，通常数十到数百 MB）。

---

### Task 4: 图标与规格验收（本机构建机）

**Files:**
- Read: `packaging/VERIFY-windows.md`（可选完整干净机验收）
- Update: `docs/superpowers/specs/2026-07-26-windows-nsis-installer-design.md` 状态为已交付（可选）

**Interfaces:**
- Consumes: Task 3 产物路径

- [ ] **Step 1: 确认安装器图标资源**

Run:
```powershell
$exe = Get-ChildItem "apps\desktop\src-tauri\target\release\bundle\nsis\*-setup.exe" | Select-Object -First 1
$exe.FullName
(Get-Item $exe.FullName).Length
Test-Path "apps\desktop\src-tauri\icons\icon.ico"
```
Expected: setup.exe 存在；`icon.ico` 存在。在资源管理器中目视确认安装器文件图标与正式应用图标一致。

- [ ] **Step 2: 对照验收清单勾选构建机项**

按 `packaging/VERIFY-windows.md`「构建机」小节勾选：产物路径存在、图标配置未偏离。干净机双击安装可留作后续人工步骤。

---

## Spec coverage（自检）

| 规格要求 | 任务 |
|----------|------|
| 标准底座 setup.exe | Task 3 |
| 共用 icon.ico | Task 2 校验 + Task 4 抽查；配置不改 |
| 安装 Rust 后跑 build-windows.ps1 | Task 1 + Task 3 |
| 不含写作 RAG / 不签名 / 不改 installMode | Global Constraints + 不修改 tauri.conf |

无 TBD。不强制本会话完成干净机安装验收。
