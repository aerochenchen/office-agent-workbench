# 文书通 Microsoft Store · MSIX 上架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 MSIX spike 之上，产出与 Partner Center Package identity 对齐的商店提交用 MSIX（GHA Artifact），并留下可照做的上架操作文（含中文列表与认证备注）；手工首提由人在 Partner Center 完成。

**Architecture:** 新增 `Package.store.appxmanifest` 模板（展示名固定为 `「文书通」`）+ `build-windows.ps1 -MsixStore` 在打包前用工作流入参替换 `__STORE_*__` 占位符；复用 spike 的 payload 舞台与 MakeAppx 清理；用与商店 Publisher 一致的开发证书打包以便本机 smoke，提交后由商店重签。新建独立 workflow，不改 NSIS / EXE 商店流。

**Tech Stack:** GitHub Actions `windows-latest`、PowerShell、winapp CLI、现有 Tauri/PyInstaller 构建、pytest 契约测试

## Global Constraints

- 规格：`docs/superpowers/specs/2026-08-06-msix-store-listing-design.md`
- 预留名 / DisplayName：`「文书通」`（U+300C / U+300D）
- 支持邮箱：`wenshutong@163.com`
- 隐私政策：`https://aerochenchen.github.io/wenshutong-privacy/`
- Version 四段式且**第 4 段为 0**（默认 `0.1.0.0`）
- 不得改变 `build-windows.yml` / `build-windows-msstore.yml` / spike `build-windows-msix.yml` 的对外默认行为（可新增并行 workflow）
- `-MsixStore` 与 `-Msix`、`-MicrosoftStore` 互斥
- 不擅自 `git commit`（除非用户明确要求）
- Partner Center **Name / Publisher / Publisher display name** 由人创建 MSIX 产品后提供；实现不得写死虚假商店 Publisher

---

## File map

| 路径 | 职责 |
|------|------|
| Create: `apps/desktop/src-tauri/Package.store.appxmanifest` | 商店清单模板（占位符 + 固定展示名） |
| Create: `apps/desktop/tests/test_msix_store_manifest.py` | 商店清单契约 |
| Modify: `scripts/build-windows.ps1` | `-MsixStore` + 身份注入 + 打包 |
| Create: `apps/desktop/tests/test_build_windows_msix_store_flag.py` | 脚本开关契约 |
| Create: `.github/workflows/build-windows-msix-store.yml` | 手动商店构建 + Artifact |
| Create: `apps/desktop/tests/test_msix_store_workflow.py` | 工作流契约 |
| Create: `docs/APP store 相关/文书通-MSIX-Store上架.md` | 建产品→抄身份→构建→上传→列表→提交 |
| Modify: `docs/superpowers/specs/2026-08-06-msix-store-listing-design.md` | 状态行指向本计划 |
| Read-only: `scripts/build-windows.ps1` 现有 `Build-Msix`、spike 清单与 workflow | 复用舞台逻辑 |

---

### Task 0（人工门禁，不改仓库）: Partner Center 新建 MSIX 产品

**Files:** 无

**Interfaces:**
- Produces（供后续 Tasks / workflow_dispatch 使用）:
  - `package_name` ← Identity Name
  - `publisher` ← Identity Publisher（完整 `CN=…`）
  - `publisher_display_name` ← Publisher display name

- [ ] **Step 1: 创建产品**

在 Partner Center → Apps and Games → **New product → MSIX or PWA app**，预留名填 **`「文书通」`**（含直角引号）。不要往旧 EXE/MSI 草稿上传包。

- [ ] **Step 2: 抄写身份**

打开 Product identity / Package identity，把三项原文保存到本地笔记（后续跑 Actions 时粘贴）：

```
package_name=
publisher=
publisher_display_name=
```

- [ ] **Step 3: 确认门禁**

若三项任一为空，**停止**后续商店构建任务；可先完成 Task 1–4 的仓库改动，但不要用空身份触发商店 workflow。

---

### Task 1: 商店清单模板 + 契约测试

**Files:**
- Create: `apps/desktop/src-tauri/Package.store.appxmanifest`
- Create: `apps/desktop/tests/test_msix_store_manifest.py`
- Read-only: `apps/desktop/src-tauri/Package.appxmanifest`（spike，勿改坏旁加载）

**Interfaces:**
- Consumes: spike 布局约定 `Executable="App\Wenshutong.exe"`、`runFullTrust`
- Produces: 占位符 `__STORE_PACKAGE_NAME__`、`__STORE_PUBLISHER__`、`__STORE_PUBLISHER_DISPLAY_NAME__`、`__STORE_VERSION__`；固定 `DisplayName` / 磁贴名为 `「文书通」`

- [ ] **Step 1: 写失败的契约测试**

创建 `apps/desktop/tests/test_msix_store_manifest.py`:

```python
"""Contract: Store-targeted Package.store.appxmanifest template."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src-tauri"
MANIFEST = ROOT / "Package.store.appxmanifest"


def test_store_manifest_exists():
    assert MANIFEST.is_file(), f"missing {MANIFEST}"


def test_store_manifest_placeholders_and_display_name():
    text = MANIFEST.read_text(encoding="utf-8")
    assert "__STORE_PACKAGE_NAME__" in text
    assert "__STORE_PUBLISHER__" in text
    assert "__STORE_PUBLISHER_DISPLAY_NAME__" in text
    assert "__STORE_VERSION__" in text
    assert "「文书通」" in text
    assert "ChenZai Wenshutong Spike" not in text
    assert 'Executable="App\\Wenshutong.exe"' in text
    assert "runFullTrust" in text
    assert re.search(r'Version="__STORE_VERSION__"', text)
```

- [ ] **Step 2: 运行确认失败**

Run:

```bash
python3 -m pytest apps/desktop/tests/test_msix_store_manifest.py -v
```

Expected: FAIL（缺文件）

- [ ] **Step 3: 创建模板**

创建 `apps/desktop/src-tauri/Package.store.appxmanifest`（以 spike 清单为骨架，仅改身份/展示名相关字段）：

```xml
<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap rescap">
  <Identity
    Name="__STORE_PACKAGE_NAME__"
    Publisher="__STORE_PUBLISHER__"
    Version="__STORE_VERSION__" />
  <Properties>
    <DisplayName>「文书通」</DisplayName>
    <PublisherDisplayName>__STORE_PUBLISHER_DISPLAY_NAME__</PublisherDisplayName>
    <Logo>Assets/StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.22621.0" />
  </Dependencies>
  <Resources>
    <Resource Language="zh-cn" />
  </Resources>
  <Applications>
    <Application Id="Wenshutong" Executable="App\Wenshutong.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="「文书通」"
        Description="本地办公智能体"
        BackgroundColor="transparent"
        Square150x150Logo="Assets/Square150x150Logo.png"
        Square44x44Logo="Assets/Square44x44Logo.png" />
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
```

- [ ] **Step 4: 再跑测试**

Run:

```bash
python3 -m pytest apps/desktop/tests/test_msix_store_manifest.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add apps/desktop/src-tauri/Package.store.appxmanifest apps/desktop/tests/test_msix_store_manifest.py
git commit -m "$(cat <<'EOF'
Add Store MSIX manifest template with identity placeholders.

EOF
)"
```

---

### Task 2: `build-windows.ps1 -MsixStore`

**Files:**
- Modify: `scripts/build-windows.ps1`
- Create: `apps/desktop/tests/test_build_windows_msix_store_flag.py`

**Interfaces:**
- Consumes: `Package.store.appxmanifest`；参数 `-MsixStore`；可选环境变量或参数：
  - `-StorePackageName` (string)
  - `-StorePublisher` (string)
  - `-StorePublisherDisplayName` (string)
  - `-StoreVersion` (string，默认 `0.1.0.0`)
- Produces: `packaging/msix-out/*.msix`（建议名 `Wenshutong_<version>_x64.msix`）；可选 `store-devcert.pfx`（Publisher 与商店一致，便于旁加载 smoke）
- 复用: 现有 `Build-Msix` 的舞台与清理逻辑（可抽成共享函数，或让 `Build-MsixStore` 调用同一舞台后再换清单）

- [ ] **Step 1: 写失败的开关契约测试**

创建 `apps/desktop/tests/test_build_windows_msix_store_flag.py`:

```python
"""Contract: build-windows.ps1 exposes -MsixStore independent of spike -Msix."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build-windows.ps1"


def test_script_defines_msix_store_switch():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$MsixStore" in text or "$MsixStore" in text
    assert "StorePackageName" in text
    assert "StorePublisher" in text
    assert "Package.store.appxmanifest" in text
    assert "Build-MsixStore" in text or "MsixStore" in text


def test_msix_store_mutex_with_other_pack_modes():
    text = SCRIPT.read_text(encoding="utf-8")
    # Must refuse combining store pack with spike Msix or MicrosoftStore EXE mode.
    assert "MsixStore" in text and "MicrosoftStore" in text and "Msix" in text
    assert "cannot be combined" in text.lower() or "互斥" in text or "throw" in text
```

- [ ] **Step 2: 运行确认失败/不足**

Run:

```bash
python3 -m pytest apps/desktop/tests/test_build_windows_msix_store_flag.py -v
```

Expected: FAIL（尚无 `-MsixStore`）

- [ ] **Step 3: 扩展 `param` 与互斥**

在 `scripts/build-windows.ps1` 顶部 `param` 增加：

```powershell
    [switch]$MsixStore,
    [string]$StorePackageName = "",
    [string]$StorePublisher = "",
    [string]$StorePublisherDisplayName = "",
    [string]$StoreVersion = "0.1.0.0"
```

在现有 `$MicrosoftStore -and $Msix` 检查旁增加：

```powershell
if ($MsixStore -and $Msix) { throw "-MsixStore cannot be combined with -Msix" }
if ($MsixStore -and $MicrosoftStore) { throw "-MsixStore cannot be combined with -MicrosoftStore" }
```

- [ ] **Step 4: 实现 `Build-MsixStore`**

要求（实现时写完整函数，勿留伪代码）：

1. 校验四个商店字段非空；`StoreVersion` 匹配 `^\d+\.\d+\.\d+\.0$`。
2. 调用与 `Build-Msix` **相同的** payload 舞台与清理（exe→`App\Wenshutong.exe`、resources、fixtures、`[Content_Types]`、`.agents` 等）。
3. 读取 `Join-Path $SrcTauri "Package.store.appxmanifest"`，替换：

```powershell
$manifestText = $manifestText.
  Replace("__STORE_PACKAGE_NAME__", $StorePackageName).
  Replace("__STORE_PUBLISHER__", $StorePublisher).
  Replace("__STORE_PUBLISHER_DISPLAY_NAME__", $StorePublisherDisplayName).
  Replace("__STORE_VERSION__", $StoreVersion)
```

写入 `$MsixPayloadDir\Package.appxmanifest`。若替换后仍含 `__STORE_`，`throw`。
4. 复制 Assets。
5. `Write-Host` 打印最终 Identity Name / Publisher / Version（便于 CI 日志核对）。
6. `winapp cert generate`：`--publisher $StorePublisher`（或 winapp 等价参数），输出 `packaging/msix-out/store-devcert.pfx`，供本机旁加载；**不要**用 spike 的 `CN=ChenZai Wenshutong Spike`。
7. `winapp pack . --cert <store-devcert> --output (Join-Path $MsixOutDir ("Wenshutong_{0}_x64.msix" -f $StoreVersion))`（保持与现有相同的 `$ErrorActionPreference=Continue` 陷阱）。
8. 主流程末尾：`if ($MsixStore) { Build-MsixStore }`（且若仅 `-MsixStore` 则不要再走 `Build-Msix`）。

若 `winapp cert generate` 不支持直接传 Publisher 字符串：先把已替换的 `Package.appxmanifest` 放在 payload 根，在该目录执行 `winapp cert generate`，让其从清单推断 Publisher（与 spike 相同模式），仍输出到 `msix-out/store-devcert.pfx`。

- [ ] **Step 5: 再跑契约测试**

Run:

```bash
python3 -m pytest apps/desktop/tests/test_build_windows_msix_store_flag.py apps/desktop/tests/test_msix_store_manifest.py apps/desktop/tests/test_build_windows_msix_flag.py -v
```

Expected: PASS（spike 开关测试仍绿）

- [ ] **Step 6: Commit**（仅当用户要求时）

```bash
git add scripts/build-windows.ps1 apps/desktop/tests/test_build_windows_msix_store_flag.py
git commit -m "$(cat <<'EOF'
Add -MsixStore packaging path with Partner Center identity injection.

EOF
)"
```

---

### Task 3: GitHub Actions 商店工作流 + 契约测试

**Files:**
- Create: `.github/workflows/build-windows-msix-store.yml`
- Create: `apps/desktop/tests/test_msix_store_workflow.py`
- Modify: `apps/desktop/tests/test_msix_workflow.py`（可选：断言 legacy 工作流仍不含 `MsixStore`；或放在新文件里断言 `build-windows-msix.yml` 不被改成商店默认）

**Interfaces:**
- Consumes: `.\scripts\build-windows.ps1 -MsixStore ...`
- Produces: Artifact `wenshutong-windows-msix-store`（`*.msix`；可选附带 `store-devcert.pfx` 仅供作者旁加载，**不要**把证书当用户分发物宣传）

- [ ] **Step 1: 写失败的工作流契约测试**

创建 `apps/desktop/tests/test_msix_store_workflow.py`:

```python
"""Contract: Store MSIX workflow is manual and separate from spike/NSIS."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows" / "build-windows-msix-store.yml"
SPIKE = ROOT / ".github" / "workflows" / "build-windows-msix.yml"
LEGACY = ROOT / ".github" / "workflows" / "build-windows.yml"
MSSTORE_EXE = ROOT / ".github" / "workflows" / "build-windows-msstore.yml"


def test_store_msix_workflow_manual_inputs_and_artifact():
    text = WF.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "Build Windows MSIX Store" in text
    assert "wenshutong-windows-msix-store" in text
    assert "MsixStore" in text
    assert "store_package_name" in text or "StorePackageName" in text
    assert "store_publisher" in text or "StorePublisher" in text
    assert "winapp" in text.lower() or "WinApp" in text


def test_spike_and_exe_workflows_remain_separate():
    spike = SPIKE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")
    exe = MSSTORE_EXE.read_text(encoding="utf-8")
    assert "wenshutong-windows-msix-store" not in spike
    assert "MsixStore" not in legacy
    assert "MsixStore" not in exe
```

- [ ] **Step 2: 运行确认失败**

Run:

```bash
python3 -m pytest apps/desktop/tests/test_msix_store_workflow.py -v
```

Expected: FAIL

- [ ] **Step 3: 创建工作流**

创建 `.github/workflows/build-windows-msix-store.yml`:

```yaml
# Manual Windows MSIX build for Microsoft Store submission.
# Trigger: Actions → Build Windows MSIX Store → Run workflow
# Inputs: Partner Center Package identity (Name / Publisher / Publisher display name)
# Download: Artifacts → wenshutong-windows-msix-store
# See docs/APP store 相关/文书通-MSIX-Store上架.md
name: Build Windows MSIX Store

on:
  workflow_dispatch:
    inputs:
      store_package_name:
        description: "Partner Center Identity Name"
        required: true
        type: string
      store_publisher:
        description: "Partner Center Identity Publisher (CN=...)"
        required: true
        type: string
      store_publisher_display_name:
        description: "Partner Center Publisher display name"
        required: true
        type: string
      store_version:
        description: "Package version (fourth segment must be 0)"
        required: true
        type: string
        default: "0.1.0.0"

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

      - name: Install winapp CLI
        uses: microsoft/setup-WinAppCli@v0.1

      - name: Verify winapp CLI
        shell: pwsh
        run: winapp --version

      - name: Build Windows MSIX (Store identity)
        shell: pwsh
        run: |
          .\scripts\build-windows.ps1 -MsixStore `
            -StorePackageName "${{ inputs.store_package_name }}" `
            -StorePublisher "${{ inputs.store_publisher }}" `
            -StorePublisherDisplayName "${{ inputs.store_publisher_display_name }}" `
            -StoreVersion "${{ inputs.store_version }}"

      - name: Upload Store MSIX artifact
        uses: actions/upload-artifact@v4
        with:
          name: wenshutong-windows-msix-store
          path: |
            packaging/msix-out/*.msix
            packaging/msix-out/*.pfx
          if-no-files-found: error
          retention-days: 14
```

- [ ] **Step 4: 再跑测试**

Run:

```bash
python3 -m pytest \
  apps/desktop/tests/test_msix_store_workflow.py \
  apps/desktop/tests/test_msix_store_manifest.py \
  apps/desktop/tests/test_build_windows_msix_store_flag.py \
  apps/desktop/tests/test_msix_workflow.py \
  -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add .github/workflows/build-windows-msix-store.yml apps/desktop/tests/test_msix_store_workflow.py
git commit -m "$(cat <<'EOF'
Add manual GHA workflow for Store-identity Windows MSIX builds.

EOF
)"
```

---

### Task 4: 上架操作文档（列表初稿 + 认证备注）

**Files:**
- Create: `docs/APP store 相关/文书通-MSIX-Store上架.md`
- Modify: `docs/superpowers/specs/2026-08-06-msix-store-listing-design.md`（状态行）

**Interfaces:**
- Consumes: 规格 §4.3、Mac 文案 `docs/APP store 相关/文书通-App-Store文案.md`（改写，去掉描述中的 URL）
- Produces: 人工可照做的步骤 + 可粘贴文本

- [ ] **Step 1: 写操作文**

创建 `docs/APP store 相关/文书通-MSIX-Store上架.md`，至少包含以下章节与内容：

````markdown
# 文书通 · Microsoft Store（MSIX）上架

对应规格：`docs/superpowers/specs/2026-08-06-msix-store-listing-design.md`。  
**产品类型：MSIX。** 不要往旧 EXE/MSI 草稿上传本包。

## 1. Partner Center：新建产品

1. New product → **MSIX or PWA app**
2. 预留名：`「文书通」`
3. 抄写 Package identity：`Name` / `Publisher` / `Publisher display name`
4. 定价：免费；市场尽量全球；列表语言先做简体中文

## 2. 打出商店包

1. Actions → **Build Windows MSIX Store** → Run workflow  
2. 填入上一步三项身份 + 版本（默认 `0.1.0.0`，第 4 段必须为 0）  
3. 下载 Artifact：`wenshutong-windows-msix-store`

## 3. 提交前本机核对（Windows）

1. 信任 `store-devcert.pfx`（若 Artifact 含证书）：`winapp cert install .\store-devcert.pfx`  
2. `Add-AppxPackage .\Wenshutong_*.msix`  
3. Smoke：启动 → 配模型对话 → 开文件夹 → 技能 → PDF  
4. 截图（Desktop PNG ≥1366×768，建议 ≥4 张；设置页勿含真实 Key）

## 4. Partner Center 填表

| 项 | 值 |
|----|-----|
| 隐私政策 | https://aerochenchen.github.io/wenshutong-privacy/ |
| 支持邮箱 | wenshutong@163.com |
| 类别 | Productivity |
| 收集个人信息 | 是 |
| 生成式 AI | 是 |
| 驱动/NT/辅助功能/笔墨 | 否 |
| 年龄分级 | IARC 问卷（生产力 + 用户内容/联网如实填） |

上传 Packages 页中的 `.msix` → 填 Store listing → Notes for certification → Submit。

## 5. 简体中文列表初稿

### 短描述（建议 ≤270 字）

```
会干活的助手，不是会说话的窗口。打开材料文件夹，用自然语言完成排版、汇总与写作；材料留在本机，模型由你配置。
```

### 完整描述（纯文本；勿再贴 URL）

```
文书通是装在本机的办公文书工作台：打开材料所在文件夹，用自然语言下任务，在受控范围内读写文件、调用技能，直接产出可交付的 Word、PDF 等结果。

会干活的助手，不是会说话的窗口。

【它和普通 AI 聊天有何不同】
• 主战场是本地文件夹，不是对话框附件
• 能力可安装、可扩展——薄底座 + 选装技能
• 模型接口由你配置（建议单位内网或本机模型）
• 结果常落成可打开、可流转、可复核的文档
• 操作可控：权限可确认、步骤看得见、调用可审计

【现在能做什么】
1. 公文排版 —— 按规范处理格式，输出新文件便于核对
2. 批量整理 —— 多文档汇总，报告带引用出处
3. 办公视觉设计 —— 为汇报生成正式配色并可套用到幻灯片
4. PDF 文本抽取 —— 将工作区内 PDF 纳入办理材料
5. 创建与沉淀技能 —— 把反复流程固化、导出、分享

【推荐使用路径】
安装 → 在设置中配置模型地址与密钥 → 先对话了解能力 → 打开材料文件夹办事 → 在技能管理中启用需要的能力。

【本地可控】
• 读写范围限制在你选定的文件夹内
• 高危操作可按权限模式要求人工确认
• 模型仅连接你配置并允许的地址
• 工具调用留在本机审计（敏感字段脱敏）
• 开发者不运营用于汇聚你公文内容的云端账号体系

一句话：让大模型进入真实文书工作流——本地可控，轻量可跑，方法可沉淀，能力可插拔。
```

（隐私政策与支持联系请填 Partner Center 专用字段，不要写进描述正文。）

## 6. Notes for certification（英文模板，可直接粘贴）

```
Date: 2026-08-06

Product: 「文书通」 (Wenshutong) — local productivity agent for office documents on Windows (MSIX).

Account / login:
- No user registration or in-app account.
- The user configures their own OpenAI-compatible model endpoint (api_base) and API key in Settings.

Network:
- Outbound HTTPS to the user-configured model endpoint only (plus normal OS/store update channels).
- Local loopback HTTP to a bundled sidecar runtime on 127.0.0.1 (office document tools).

Files:
- Reads/writes only within the folder the user explicitly opens as the workspace.
- Supports Office documents and PDF text extraction for workspace materials.

Display name:
- Reserved Store name includes CJK corner quotes: 「文书通」 (U+300C / U+300D), because the unquoted name was unavailable.

Testing:
- No test account required.
- Contact: wenshutong@163.com
- Suggested path: launch → set model → send one chat → open a folder → run one skill → open a PDF in workspace and extract/summarize.
```

## 7. 失败时

按规格 Kill / 回退：继续 NSIS 直链；勿默认改回买证 EXE，除非书面改决策。
````

- [ ] **Step 2: 更新规格状态行**

将 `docs/superpowers/specs/2026-08-06-msix-store-listing-design.md` 表头状态改为：

`已确认；实现计划见 docs/superpowers/plans/2026-08-06-msix-store-listing.md`

- [ ] **Step 3: 文档自检**

Run:

```bash
rg -n "Build Windows MSIX Store|wenshutong-windows-msix-store|wenshutong@163.com|「文书通」|Notes for certification" \
  "docs/APP store 相关/文书通-MSIX-Store上架.md" \
  docs/superpowers/specs/2026-08-06-msix-store-listing-design.md
```

Expected: 均有命中

- [ ] **Step 4: Commit**（仅当用户要求时）

```bash
git add "docs/APP store 相关/文书通-MSIX-Store上架.md" docs/superpowers/specs/2026-08-06-msix-store-listing-design.md
git commit -m "$(cat <<'EOF'
Document MSIX Store listing steps, copy, and certification notes.

EOF
)"
```

---

### Task 5: 端到端契约核对 + 提醒人工步骤

**Files:** 无新代码（只读验证）

- [ ] **Step 1: 跑全部相关契约测试**

Run:

```bash
python3 -m pytest \
  apps/desktop/tests/test_msix_manifest.py \
  apps/desktop/tests/test_msix_store_manifest.py \
  apps/desktop/tests/test_build_windows_msix_flag.py \
  apps/desktop/tests/test_build_windows_msix_store_flag.py \
  apps/desktop/tests/test_msix_workflow.py \
  apps/desktop/tests/test_msix_store_workflow.py \
  -v
```

Expected: 全部 PASS

- [ ] **Step 2: 确认未误改 EXE/NSIS 工作流**

Run:

```bash
git diff -- .github/workflows/build-windows.yml .github/workflows/build-windows-msstore.yml
```

Expected: 无输出（或仅与本计划无关的既有本地改动；实现者不得改这两文件）

- [ ] **Step 3: 提醒用户（实现完成后）**

1. 完成 **Task 0**（若尚未）：Partner Center 建 MSIX 产品并抄身份  
2. 推送含 workflow 的提交后，跑 **Build Windows MSIX Store**（粘贴身份）  
3. Windows 旁加载 smoke + 截图  
4. Partner Center 上传包、填列表与 Notes、Submit  
5. 通过 → In the Store；失败 → 按规格记录，不默认改 EXE

---

## Plan self-review (vs spec)

| 规格项 | 对应 Task |
|--------|-----------|
| 新建 MSIX 产品 / 预留名 `「文书通」` | Task 0 + Task 4 §1 |
| 身份注入构建 | Task 1–3 |
| Version 第 4 段为 0 | Task 2 校验 + workflow default |
| 免费 / 全球 / 中文列表 / 邮箱 / 隐私 URL | Task 4 |
| 生成式 AI 等声明 | Task 4 §4 |
| 认证备注 | Task 4 §6 |
| Artifact 商店包 / 手工上传 | Task 3–4 |
| 不改 NSIS/EXE 流 | Task 3 测试 + Task 5 |
| Kill / 回退说明 | Task 4 §7 |
| 提交前 smoke（含 PDF） | Task 4 §3 |
| msstore CLI 不做 | 未列入实现任务 |

无 TBD 占位；Partner Center 真实 Name/Publisher 由 Task 0 人工提供，模板用 `__STORE_*__` 明确表达。
