# Microsoft Store EXE + GitHub Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增商店专用 GitHub Actions 工作流，打出符合 Microsoft Store（EXE/MSI）要求的 NSIS 安装包 Artifact；并留下 Mac 上手动上架说明。

**Architecture:** 保留现有直链 `build-windows.yml`。新增 `tauri.microsoftstore.conf.json`（`offlineInstaller` + 显式 `publisher`），扩展 `build-windows.ps1 -MicrosoftStore` 合并该配置，新建独立 workflow 上传 Artifact。不自动上传 Partner Center；一期不强制签名。

**Tech Stack:** GitHub Actions `windows-latest`、PowerShell、Tauri 2 CLI、NSIS、pytest（配置契约测试）

## Global Constraints

- 规格：`docs/superpowers/specs/2026-08-05-microsoft-store-exe-gha-design.md`
- 现有 `.github/workflows/build-windows.yml` 行为不得改变
- 默认 `apps/desktop/src-tauri/tauri.conf.json` 保持 `embedBootstrapper` 与 `targets: ["nsis"]`
- 商店产物：标准底座 NSIS；不含写作 RAG 重依赖
- 一期不强制 Authenticode；上架文档必须写明签名为硬门槛
- 不擅自 git commit（除非用户明确要求）
- 静默参数文档必须写 `/S`（大写 S）
- `bundle.publisher` 固定为 `Chenzai`（≠ 产品名「文书通」；与 identifier `com.chenzai.*` 一致）

---

## File map

| 路径 | 职责 |
|------|------|
| Create: `apps/desktop/src-tauri/tauri.microsoftstore.conf.json` | 商店叠加配置（offline WebView2 + publisher） |
| Create: `apps/desktop/tests/test_microsoftstore_conf.py` | 契约测试：商店 conf 字段 |
| Modify: `scripts/build-windows.ps1` | 增加 `-MicrosoftStore`；开启时 `--config` 合并商店 conf |
| Create: `.github/workflows/build-windows-msstore.yml` | 手动触发商店构建 + Artifact |
| Create: `docs/APP store 相关/文书通-Microsoft-Store上架.md` | Mac 侧上架操作说明 |
| Read-only: `.github/workflows/build-windows.yml` | 对齐步骤结构，不改内容 |
| Read-only: `apps/desktop/src-tauri/tauri.conf.json` | 确认默认不被覆盖 |

---

### Task 1: 商店 Tauri 配置 + 契约测试

**Files:**
- Create: `apps/desktop/src-tauri/tauri.microsoftstore.conf.json`
- Create: `apps/desktop/tests/test_microsoftstore_conf.py`

**Interfaces:**
- Consumes: 无
- Produces: JSON 文件路径相对 `apps/desktop/src-tauri/`；测试断言 `webviewInstallMode.type == "offlineInstaller"` 且 `publisher == "Chenzai"`

- [ ] **Step 1: 写失败的契约测试**

创建 `apps/desktop/tests/test_microsoftstore_conf.py`:

```python
"""Contract: Microsoft Store overlay config for Tauri Windows builds."""

from __future__ import annotations

import json
from pathlib import Path

CONF = (
    Path(__file__).resolve().parents[1]
    / "src-tauri"
    / "tauri.microsoftstore.conf.json"
)


def test_microsoftstore_conf_exists():
    assert CONF.is_file(), f"missing {CONF}"


def test_offline_installer_and_publisher():
    data = json.loads(CONF.read_text(encoding="utf-8"))
    webview = data["bundle"]["windows"]["webviewInstallMode"]
    assert webview["type"] == "offlineInstaller"
    assert data["bundle"]["publisher"] == "Chenzai"
    assert data["bundle"]["publisher"] != "文书通"
```

- [ ] **Step 2: 运行测试确认失败**

Run（仓库根目录）:

```bash
python -m pytest apps/desktop/tests/test_microsoftstore_conf.py -v
```

Expected: FAIL（文件不存在或 import/断言失败）

- [ ] **Step 3: 写入最小商店配置**

Create `apps/desktop/src-tauri/tauri.microsoftstore.conf.json`:

```json
{
  "bundle": {
    "publisher": "Chenzai",
    "windows": {
      "webviewInstallMode": {
        "type": "offlineInstaller"
      }
    }
  }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
python -m pytest apps/desktop/tests/test_microsoftstore_conf.py -v
```

Expected: PASS（2 passed）

- [ ] **Step 5: 确认默认 conf 仍为直链策略**

Run:

```bash
python -c "import json; p='apps/desktop/src-tauri/tauri.conf.json'; d=json.load(open(p,encoding='utf-8')); assert d['bundle']['windows']['webviewInstallMode']['type']=='embedBootstrapper'; print('ok', d['bundle']['windows']['webviewInstallMode'])"
```

Expected: 打印 `ok {'type': 'embedBootstrapper'}`

- [ ] **Step 6: Commit（仅当用户要求时）**

```bash
git add apps/desktop/src-tauri/tauri.microsoftstore.conf.json apps/desktop/tests/test_microsoftstore_conf.py
git commit -m "$(cat <<'EOF'
Add Tauri Microsoft Store overlay config and contract test.

EOF
)"
```

---

### Task 2: 扩展 `build-windows.ps1` 支持 `-MicrosoftStore`

**Files:**
- Modify: `scripts/build-windows.ps1`
- Create: `apps/desktop/tests/test_build_windows_msstore_flag.py`（静态检查脚本含开关与 `--config`）

**Interfaces:**
- Consumes: `apps/desktop/src-tauri/tauri.microsoftstore.conf.json`（Task 1）
- Produces: `param([switch]$MicrosoftStore)`；当 `$MicrosoftStore` 时 `npx tauri build --config src-tauri/tauri.microsoftstore.conf.json`

- [ ] **Step 1: 写失败的静态契约测试**

Create `apps/desktop/tests/test_build_windows_msstore_flag.py`:

```python
"""Contract: build-windows.ps1 exposes -MicrosoftStore and passes Tauri --config."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build-windows.ps1"


def test_script_defines_microsoft_store_switch():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$MicrosoftStore" in text


def test_script_passes_store_config_to_tauri():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "tauri.microsoftstore.conf.json" in text
    assert "--config" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m pytest apps/desktop/tests/test_build_windows_msstore_flag.py -v
```

Expected: FAIL（断言找不到开关或 `--config`）

- [ ] **Step 3: 修改 `scripts/build-windows.ps1` 参数块**

将文件顶部 `param` 改为：

```powershell
param(
    [switch]$SkipSidecar,
    [switch]$SkipTauri,
    [switch]$Clean,
    [switch]$MicrosoftStore
)
```

- [ ] **Step 4: 修改 `Build-Tauri` 在商店模式下传入 `--config`**

将 `Build-Tauri` 函数内 `npx` 调用替换为（保留原有 `$prevEap` / 退出码处理结构）：

```powershell
function Build-Tauri {
    Write-Step "npm install + tauri build (NSIS)"
    Push-Location $DesktopDir
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        if (-not (Test-Path (Join-Path $DesktopDir "node_modules\@tauri-apps\cli"))) {
            & npm install
            if ($LASTEXITCODE -ne 0) {
                $ErrorActionPreference = $prevEap
                throw "npm install failed"
            }
        }
        $tauriArgs = @("tauri", "build")
        if ($MicrosoftStore) {
            $storeConf = Join-Path $SrcTauri "tauri.microsoftstore.conf.json"
            if (-not (Test-Path $storeConf)) {
                $ErrorActionPreference = $prevEap
                throw "Microsoft Store config missing: $storeConf"
            }
            Write-Host "Microsoft Store mode: merging $storeConf"
            $tauriArgs += @("--config", "src-tauri/tauri.microsoftstore.conf.json")
        }
        & npx --yes @tauriArgs
        $tauriExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        if ($tauriExit -ne 0) { throw "tauri build failed with exit $tauriExit" }
    }
    finally {
        Pop-Location
    }

    $nsisDir = Join-Path $SrcTauri "target\release\bundle\nsis"
    Write-Step "Done"
    if (Test-Path $nsisDir) {
        Get-ChildItem $nsisDir -Filter "*.exe" | ForEach-Object {
            Write-Host ("Installer: " + $_.FullName) -ForegroundColor Green
        }
    }
    else {
        Write-Host "NSIS output folder not found at $nsisDir (check tauri build logs)." -ForegroundColor Yellow
    }
}
```

注意：原脚本是 `& npx --yes tauri build`。实现时必须把 `tauri build` 与可选 `--config` 作为参数数组传给 `npx --yes`，即：

```powershell
& npx --yes @tauriArgs
```

其中 `$tauriArgs` 在非商店模式为 `@("tauri", "build")`，商店模式为 `@("tauri", "build", "--config", "src-tauri/tauri.microsoftstore.conf.json")`。

在 `SYNOPSIS` / `.DESCRIPTION` 注释中增加一行：`-MicrosoftStore` 合并 `tauri.microsoftstore.conf.json`。

- [ ] **Step 5: 运行契约测试确认通过**

Run:

```bash
python -m pytest apps/desktop/tests/test_build_windows_msstore_flag.py apps/desktop/tests/test_microsoftstore_conf.py -v
```

Expected: PASS

- [ ] **Step 6: Commit（仅当用户要求时）**

```bash
git add scripts/build-windows.ps1 apps/desktop/tests/test_build_windows_msstore_flag.py
git commit -m "$(cat <<'EOF'
Add -MicrosoftStore flag to Windows build script.

EOF
)"
```

---

### Task 3: 新建商店 GitHub Actions 工作流

**Files:**
- Create: `.github/workflows/build-windows-msstore.yml`
- Create: `apps/desktop/tests/test_msstore_workflow.py`

**Interfaces:**
- Consumes: `scripts/build-windows.ps1 -MicrosoftStore`（Task 2）
- Produces: workflow 名 `Build Windows MS Store`；Artifact `wenshutong-windows-msstore`

- [ ] **Step 1: 写失败的工作流契约测试**

Create `apps/desktop/tests/test_msstore_workflow.py`:

```python
"""Contract: MS Store Windows workflow exists and calls -MicrosoftStore."""

from __future__ import annotations

from pathlib import Path

WF = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "build-windows-msstore.yml"
)
LEGACY = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "build-windows.yml"
)


def test_msstore_workflow_exists_and_is_manual():
    text = WF.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "Build Windows MS Store" in text
    assert "wenshutong-windows-msstore" in text
    assert "-MicrosoftStore" in text or "MicrosoftStore" in text


def test_legacy_windows_workflow_unchanged_marker():
    """Smoke: legacy workflow still present and does not opt into Store mode."""
    text = LEGACY.read_text(encoding="utf-8")
    assert "Build Windows Installer" in text
    assert "MicrosoftStore" not in text
    assert "wenshutong-windows-nsis" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m pytest apps/desktop/tests/test_msstore_workflow.py -v
```

Expected: FAIL（workflow 文件不存在）

- [ ] **Step 3: 创建工作流文件**

Create `.github/workflows/build-windows-msstore.yml`（内容如下，结构对齐现有 `build-windows.yml`，仅构建命令与 Artifact 不同）：

```yaml
# Manual Windows NSIS build for Microsoft Store (EXE/MSI listing).
# Trigger: Actions → Build Windows MS Store → Run workflow
# Download: run summary → Artifacts → wenshutong-windows-msstore
# Upload to Partner Center is manual (see docs/APP store 相关/文书通-Microsoft-Store上架.md).
name: Build Windows MS Store

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build:
    runs-on: windows-latest
    timeout-minutes: 90

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: apps/desktop/package-lock.json

      - name: Setup Rust
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: x86_64-pc-windows-msvc

      - name: Cache Rust build
        uses: Swatinem/rust-cache@v2
        with:
          workspaces: apps/desktop/src-tauri -> target

      - name: Ensure Git Bash on PATH
        shell: pwsh
        run: |
          $gitBin = "C:\Program Files\Git\bin"
          if (-not (Test-Path "$gitBin\bash.exe")) {
            throw "Git Bash not found (required by tauri beforeBuildCommand)"
          }
          Add-Content -Path $env:GITHUB_PATH -Value $gitBin

      - name: Build Windows NSIS installer (Microsoft Store config)
        shell: pwsh
        run: .\scripts\build-windows.ps1 -MicrosoftStore

      - name: Upload installer artifact
        uses: actions/upload-artifact@v4
        with:
          name: wenshutong-windows-msstore
          path: apps/desktop/src-tauri/target/release/bundle/nsis/*-setup.exe
          if-no-files-found: error
          retention-days: 14
```

- [ ] **Step 4: 运行契约测试确认通过**

Run:

```bash
python -m pytest apps/desktop/tests/test_msstore_workflow.py apps/desktop/tests/test_microsoftstore_conf.py apps/desktop/tests/test_build_windows_msstore_flag.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit（仅当用户要求时）**

```bash
git add .github/workflows/build-windows-msstore.yml apps/desktop/tests/test_msstore_workflow.py
git commit -m "$(cat <<'EOF'
Add GitHub Actions workflow for Microsoft Store Windows build.

EOF
)"
```

---

### Task 4: 上架操作文档

**Files:**
- Create: `docs/APP store 相关/文书通-Microsoft-Store上架.md`

**Interfaces:**
- Consumes: Artifact 名 `wenshutong-windows-msstore`；静默 `/S`；工作流显示名 `Build Windows MS Store`
- Produces: 人工可跟随完成 Partner Center 提交的中文说明

- [ ] **Step 1: 写入上架文档**

Create `docs/APP store 相关/文书通-Microsoft-Store上架.md`，正文须包含下列章节与要点（可直接使用下文）：

```markdown
# 文书通 · Microsoft Store 上架（EXE/MSI）

本文对应规格：`docs/superpowers/specs/2026-08-05-microsoft-store-exe-gha-design.md`。  
构建由 GitHub Actions 完成；**提交 Partner Center 需在浏览器中手动操作**（Mac 即可）。

## 1. 前置条件

1. 注册 [Partner Center](https://partner.microsoft.com/) Windows 应用开发者账号。
2. 在 Apps and Games 中 **New Product → EXE or MSI app**，预留应用名（如「文书通」）。
3. 准备隐私政策 URL（可复用 `docs/APP store 相关/文书通-隐私政策.md` 的公开发布页）。
4. **代码签名证书**（上架硬门槛）：安装包及其中 PE 须由链式到 [Microsoft Trusted Root Program](https://learn.microsoft.com/en-us/security/trusted-root/participants-list) 的证书签名。自签名不可用。微软对 EXE/MSI 路径**不会**免费重签。

## 2. 用 GitHub Actions 打商店包

1. 打开仓库 GitHub → **Actions** → **Build Windows MS Store** → **Run workflow**。
2. 等待 `windows-latest` 任务完成。
3. 在 run 摘要页下载 Artifact：`wenshutong-windows-msstore`（内含 `文书通_*_x64-setup.exe`）。
4. 该包已合并商店配置：`offlineInstaller`（离线 WebView2）、publisher=`Chenzai`。

直链分发请继续使用 **Build Windows Installer**（`wenshutong-windows-nsis`），二者互不影响。

## 3. 托管 HTTPS 版本化 URL

Partner Center 的 EXE/MSI 产品需要填写**安装包下载 URL**：

- 必须是 **HTTPS** 直链。
- URL 应按版本固定；**提交后该 URL 上的二进制不得再被覆盖**。
- 新版本必须换新的版本化 URL，并更新商店提交。

推荐：用 GitHub Release 的 Assets 链接（每个版本独立文件名，例如 `文书通_0.1.0_x64-setup.exe`）。

一期 CI 默认可能产出**未签名**包：上架前请先完成本机或 CI 签名，再上传到该 URL。

## 4. Partner Center 填写要点

| 项 | 值 |
|----|-----|
| 产品类型 | EXE or MSI app |
| 安装包 | 上一步 HTTPS URL |
| 静默安装参数 | `/S`（NSIS，注意大写 S） |
| WebView2 | 已由商店构建使用 offlineInstaller，安装时无需再下载引导程序 |

按向导补齐商店列表：截图、说明、分级、隐私政策、认证备注等，然后 **Submit for certification**。

## 5. 与 Mac App Store 的关系

- Mac：`docs/APP store 相关/文书通-Mac-App-Store构建.md`
- Windows Store：本文
- 两边账号、证书、包格式均独立，不要混用 Apple 证书签 Windows 包。

## 6. 后续（非本期）

- Actions Secrets + Azure Trusted Signing / PFX 接入 CI 签名
- `msstore` CLI 自动上传
- 真 MSIX（需另开规格）
```

- [ ] **Step 2: 用 grep 自检关键字符串**

Run:

```bash
rg -n "Build Windows MS Store|/S|wenshutong-windows-msstore|offlineInstaller|Trusted Root|EXE or MSI" "docs/APP store 相关/文书通-Microsoft-Store上架.md"
```

Expected: 上述关键词均有命中。

- [ ] **Step 3: Commit（仅当用户要求时）**

```bash
git add "docs/APP store 相关/文书通-Microsoft-Store上架.md"
git commit -m "$(cat <<'EOF'
Document Microsoft Store EXE listing steps for 文书通.

EOF
)"
```

---

### Task 5: 端到端核对（本机契约 + 提醒跑 Actions）

**Files:**
- 无新文件（只读验证）

**Interfaces:**
- Consumes: Task 1–4 全部产物

- [ ] **Step 1: 跑全部相关契约测试**

Run:

```bash
python -m pytest \
  apps/desktop/tests/test_microsoftstore_conf.py \
  apps/desktop/tests/test_build_windows_msstore_flag.py \
  apps/desktop/tests/test_msstore_workflow.py \
  -v
```

Expected: 全部 PASS

- [ ] **Step 2: 确认旧工作流文件未被修改**

Run:

```bash
git diff -- .github/workflows/build-windows.yml
```

Expected: 无输出（无 diff）

- [ ] **Step 3:（可选，需 GitHub 权限）手动触发 Actions**

在 GitHub UI：Actions → Build Windows MS Store → Run workflow。  
Expected: 成功并出现 Artifact `wenshutong-windows-msstore`。  
若本会话无权限推送/触发，在实现记录中注明「待用户在 GitHub 上手动跑通」。

- [ ] **Step 4: 更新规格状态行（可选）**

将 `docs/superpowers/specs/2026-08-05-microsoft-store-exe-gha-design.md` 表头「待写实现计划」改为「实现计划见 `docs/superpowers/plans/2026-08-05-microsoft-store-exe-gha.md`」。

---

## Spec coverage checklist（写作自检）

| 规格要求 | 对应任务 |
|----------|----------|
| 独立商店 workflow、手动触发 | Task 3 |
| `tauri.microsoftstore.conf.json` offlineInstaller + publisher | Task 1 |
| 扩展 `build-windows.ps1 -MicrosoftStore` | Task 2 |
| 现有 `build-windows.yml` 不动 | Task 3 契约 + Task 5 |
| Artifact `wenshutong-windows-msstore` | Task 3 |
| 上架文档含 `/S`、HTTPS、签名门槛 | Task 4 |
| 不自动上传 / 不做 MSIX | 全局约束 + 文档第 6 节 |
| 签名分步（一期可不签） | Task 4 第 1、3 节 |

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-05-microsoft-store-exe-gha.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子代理，Task 间复核  
2. **Inline Execution** — 本会话按 executing-plans 连续执行并设检查点  

要选哪一种？
