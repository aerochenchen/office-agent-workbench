# 文书通 Windows MSIX Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增手动 GitHub Actions 工作流，打出可在本机 Windows 旁加载安装的 MSIX Artifact，并留下 spike 验收文档；验证核心办事路径，不过关则按规格 kill。

**Architecture:** 复用现有 `build-windows.ps1` 的 sidecar stage + Tauri build，额外把「主程序 + resources」舞台到 `packaging/msix-payload/`，用 `winapp pack`（自签名开发证书）产出 `*.msix`。现有 NSIS / MS Store EXE 工作流行为不变。

**Tech Stack:** GitHub Actions `windows-latest`、PowerShell、Tauri 2、PyInstaller onedir、winapp CLI、pytest 契约测试

## Global Constraints

- 规格：`docs/superpowers/specs/2026-08-05-msix-spike-design.md`
- 不得改变 `.github/workflows/build-windows.yml` 与 `build-windows-msstore.yml` 的对外行为
- 默认 `tauri.conf.json` 仍为 NSIS + `embedBootstrapper`
- Spike 用自签名证书旁加载；不采购生产 Authenticode；不提交 Partner Center
- 不擅自 git commit（除非用户明确要求）
- MSIX 舞台必须包含 sidecar：`resources/runtime/` + `resources/bundled/`（不能只拷单个 exe）
- 主程序入口名与 `productName` 一致时可能是 `文书通.exe`；清单 `Executable` 必须与舞台中实际文件名一致

---

## File map

| 路径 | 职责 |
|------|------|
| Create: `apps/desktop/src-tauri/Package.appxmanifest` | MSIX 包身份（spike 级 Publisher） |
| Create: `apps/desktop/src-tauri/Assets/` | winapp 要求的占位图标（可由现有 icon 生成或复制） |
| Create: `apps/desktop/tests/test_msix_manifest.py` | 清单与入口约定契约测试 |
| Create: `apps/desktop/tests/test_msix_workflow.py` | 工作流契约测试 |
| Modify: `scripts/build-windows.ps1` | 增加 `-Msix`：舞台 payload + winapp pack |
| Create: `apps/desktop/tests/test_build_windows_msix_flag.py` | 脚本开关契约测试 |
| Create: `.github/workflows/build-windows-msix.yml` | 手动构建 + Artifact |
| Create: `docs/APP store 相关/文书通-MSIX-spike.md` | 下载、装证书、安装、验收、kill 记录 |
| Modify: `docs/superpowers/specs/2026-08-05-msix-spike-design.md` | 状态行指向本计划 |
| Read-only: `.github/workflows/build-windows.yml`、`build-windows-msstore.yml` | 回归对照 |
| Read-only: `apps/desktop/src-tauri/src/lib.rs` | sidecar 路径约定 |

---

### Task 1: Package.appxmanifest + 契约测试

**Files:**
- Create: `apps/desktop/src-tauri/Package.appxmanifest`
- Create: `apps/desktop/src-tauri/Assets/.gitkeep`（若 winapp 需要具体 png，下一步用现有 `icons/` 复制为 Square150x150Logo.png 等标准名）
- Create: `apps/desktop/tests/test_msix_manifest.py`

**Interfaces:**
- Consumes: 无
- Produces: 清单字段约定供 Task 2 打包使用：
  - `Identity Name` = `ChenZai.Wenshutong`（ASCII）
  - `Publisher` = `CN=ChenZai Wenshutong Spike`（须与后续 `winapp cert generate` 一致）
  - `Version` = `0.1.0.0`
  - `DisplayName` = `文书通`
  - `Application Executable` = `文书通.exe`（若构建产物文件名不同，Task 2 必须改清单或重命名 exe，二选一写进脚本日志）

- [ ] **Step 1: 写失败的契约测试**

创建 `apps/desktop/tests/test_msix_manifest.py`:

```python
"""Contract: MSIX Package.appxmanifest for spike packaging."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src-tauri"
MANIFEST = ROOT / "Package.appxmanifest"


def test_manifest_exists():
    assert MANIFEST.is_file(), f"missing {MANIFEST}"


def test_identity_and_entry_are_spike_safe():
    text = MANIFEST.read_text(encoding="utf-8")
    assert 'Name="ChenZai.Wenshutong"' in text or "Name='ChenZai.Wenshutong'" in text
    assert "CN=ChenZai Wenshutong Spike" in text
    assert re.search(r'Version="0\.1\.0\.0"', text)
    assert "文书通.exe" in text
    assert "runFullTrust" in text or "partialTrust" in text or "windows.fullTrustApplication" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd apps/desktop && python3 -m pytest tests/test_msix_manifest.py -v
```

Expected: FAIL（文件不存在或字段缺失）

- [ ] **Step 3: 添加清单与 Assets**

在 `apps/desktop/src-tauri/` 创建 `Package.appxmanifest`（Desktop Bridge / fullTrust 风格，与 winapp 生成结构对齐）。最小可用骨架：

```xml
<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap rescap">
  <Identity
    Name="ChenZai.Wenshutong"
    Publisher="CN=ChenZai Wenshutong Spike"
    Version="0.1.0.0" />
  <Properties>
    <DisplayName>文书通</DisplayName>
    <PublisherDisplayName>ChenZai</PublisherDisplayName>
    <Logo>Assets/StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.22621.0" />
  </Dependencies>
  <Resources>
    <Resource Language="zh-cn" />
  </Resources>
  <Applications>
    <Application Id="Wenshutong" Executable="文书通.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="文书通"
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

从 `apps/desktop/src-tauri/icons/` 复制/生成 `Assets/StoreLogo.png`、`Square150x150Logo.png`、`Square44x44Logo.png`（可用现有 png 临时；spike 不要求商店级美工）。

若本机已装 winapp，也可用 `winapp init` 生成后**改成上述 Identity/Executable**，但提交到仓库的内容必须满足测试断言。

- [ ] **Step 4: 再跑测试确认通过**

Run:

```bash
cd apps/desktop && python3 -m pytest tests/test_msix_manifest.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add apps/desktop/src-tauri/Package.appxmanifest apps/desktop/src-tauri/Assets apps/desktop/tests/test_msix_manifest.py
git commit -m "$(cat <<'EOF'
Add MSIX spike Package.appxmanifest and contract tests.

EOF
)"
```

---

### Task 2: `build-windows.ps1 -Msix` 舞台 + winapp pack

**Files:**
- Modify: `scripts/build-windows.ps1`
- Create: `apps/desktop/tests/test_build_windows_msix_flag.py`

**Interfaces:**
- Consumes: Task 1 的 `Package.appxmanifest` + `Assets/`；现有 sidecar stage 输出
- Produces:
  - 开关：`-Msix`
  - 舞台目录：`$RepoRoot/packaging/msix-payload/`（含 `文书通.exe` 与 `resources/**`）
  - 输出：`$RepoRoot/packaging/msix-out/*.msix`（或脚本打印的确切路径）
  - 开发证书：`$RepoRoot/packaging/msix-out/devcert.pfx`（gitignore；CI 每次生成）

- [ ] **Step 1: 写失败的脚本契约测试**

创建 `apps/desktop/tests/test_build_windows_msix_flag.py`:

```python
"""Contract: build-windows.ps1 supports -Msix without breaking defaults."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build-windows.ps1"


def test_script_defines_msix_switch():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$Msix" in text or "Msix" in text
    assert "msix-payload" in text
    assert "winapp" in text.lower()
    assert "Package.appxmanifest" in text


def test_msix_and_microsoftstore_are_independent_flags():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "MicrosoftStore" in text
    assert "Msix" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python3 -m pytest apps/desktop/tests/test_build_windows_msix_flag.py -v
```

Expected: FAIL

- [ ] **Step 3: 扩展 `build-windows.ps1`**

在 `param` 增加 `[switch]$Msix`。

在 `Build-Tauri` 之后（或 `-Msix` 专用函数）增加逻辑，要点：

1. 若同时传 `-MicrosoftStore` 与 `-Msix`：抛错（互斥），避免混淆。
2. Tauri 仍可走现有 `tauri build`（产出 release exe + 已 stage 的 resources）。不必为了 spike 强行 `--no-bundle`；NSIS 顺带产出可忽略。
3. 清空并创建 `packaging/msix-payload`。
4. 定位主程序：优先 `Join-Path $SrcTauri "target\release\文书通.exe"`；若不存在则 `Get-ChildItem ...\target\release\*.exe` 排除 `office-agent-runtime.exe`，取产品主 exe，并 **Copy 时统一命名为清单中的 `文书通.exe`**（或改写舞台内临时清单——优先重命名拷贝以保持清单稳定）。
5. 复制整个已 stage 的 `apps/desktop/src-tauri/resources` 到 `packaging/msix-payload/resources`（必须含 `runtime/office-agent-runtime.exe`）。
6. 将 `Package.appxmanifest` 与 `Assets` 拷到 `packaging/msix-payload/`（或依赖 `winapp pack` 从 `src-tauri` 当前目录读取——若 winapp 要求 cwd 在 manifest 旁，则 `Push-Location $SrcTauri` 并对 payload 路径打包）。
7. 确保 `winapp` 在 PATH；否则给出安装提示：`winget install microsoft.winappcli`。
8. `winapp cert generate --if-exists skip`（在含清单的目录执行，Publisher 对齐）。
9. `winapp pack <payload> --cert <devcert.pfx>`；把生成的 `*.msix` 与 `devcert.pfx` 收集到 `packaging/msix-out/`。
10. 控制台打印 MSIX 完整路径。

将 `packaging/msix-out/` 与 `packaging/msix-payload/`、`*.pfx` 加入 `.gitignore`（若尚未忽略）。

伪代码结构（实现时写成真实 PowerShell）：

```powershell
param(
    [switch]$SkipSidecar,
    [switch]$SkipTauri,
    [switch]$Clean,
    [switch]$MicrosoftStore,
    [switch]$Msix
)

# ... existing helpers ...

function Build-Msix {
    if ($MicrosoftStore) { throw "-Msix cannot be combined with -MicrosoftStore" }
    Write-Step "Stage MSIX payload + winapp pack"
    $payload = Join-Path $PackagingDir "msix-payload"
    $outDir = Join-Path $PackagingDir "msix-out"
    # recreate payload/outDir, copy exe + resources, ensure winapp, cert generate, pack
}

# after Build-Tauri:
if ($Msix) { Build-Msix }
```

- [ ] **Step 4: 再跑契约测试**

Run:

```bash
python3 -m pytest apps/desktop/tests/test_build_windows_msix_flag.py apps/desktop/tests/test_msix_manifest.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add scripts/build-windows.ps1 apps/desktop/tests/test_build_windows_msix_flag.py .gitignore
git commit -m "$(cat <<'EOF'
Add -Msix packaging path via winapp for Windows spike.

EOF
)"
```

---

### Task 3: GitHub Actions 工作流 + 契约测试

**Files:**
- Create: `.github/workflows/build-windows-msix.yml`
- Create: `apps/desktop/tests/test_msix_workflow.py`

**Interfaces:**
- Consumes: `.\scripts\build-windows.ps1 -Msix`
- Produces: Artifact 名 `wenshutong-windows-msix`；内含 `*.msix` 与 `devcert.pfx`（供本机信任）

- [ ] **Step 1: 写失败的工作流契约测试**

创建 `apps/desktop/tests/test_msix_workflow.py`:

```python
"""Contract: MSIX Windows workflow is manual and isolated from NSIS store workflow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows" / "build-windows-msix.yml"
LEGACY = ROOT / ".github" / "workflows" / "build-windows.yml"
MSSTORE = ROOT / ".github" / "workflows" / "build-windows-msstore.yml"


def test_msix_workflow_exists_and_is_manual():
    text = WF.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "Build Windows MSIX" in text
    assert "wenshutong-windows-msix" in text
    assert "-Msix" in text or "Msix" in text
    assert "winapp" in text.lower() or "WinApp" in text or "microsoft.winappcli" in text.lower()


def test_other_windows_workflows_untouched_by_msix_flag():
    legacy = LEGACY.read_text(encoding="utf-8")
    store = MSSTORE.read_text(encoding="utf-8")
    assert "Build Windows Installer" in legacy
    assert "Msix" not in legacy
    assert "Build Windows MS Store" in store
    assert "Msix" not in store
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python3 -m pytest apps/desktop/tests/test_msix_workflow.py -v
```

Expected: FAIL

- [ ] **Step 3: 创建工作流**

创建 `.github/workflows/build-windows-msix.yml`，结构对齐 `build-windows-msstore.yml`，差异如下：

```yaml
# Manual Windows MSIX spike build.
# Trigger: Actions → Build Windows MSIX → Run workflow
# Download: Artifacts → wenshutong-windows-msix (*.msix + devcert.pfx)
# See docs/APP store 相关/文书通-MSIX-spike.md
name: Build Windows MSIX

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

      - name: Install winapp CLI
        shell: pwsh
        run: |
          winget install --id Microsoft.WinAppCLI --accept-package-agreements --accept-source-agreements --disable-interactivity
          winapp --version

      - name: Build Windows MSIX (spike)
        shell: pwsh
        run: .\scripts\build-windows.ps1 -Msix

      - name: Upload MSIX artifact
        uses: actions/upload-artifact@v4
        with:
          name: wenshutong-windows-msix
          path: |
            packaging/msix-out/*.msix
            packaging/msix-out/*.pfx
          if-no-files-found: error
          retention-days: 14
```

若 `winget install Microsoft.WinAppCLI` 在 runner 上不稳定，回退为规格允许的 MakeAppx 路径前，先在 spike 文档记录；实现优先用 [setup-WinAppCli](https://github.com/microsoft/setup-WinAppCli) action（若仍维护）替换 winget 步骤。

- [ ] **Step 4: 再跑测试**

Run:

```bash
python3 -m pytest apps/desktop/tests/test_msix_workflow.py apps/desktop/tests/test_build_windows_msix_flag.py apps/desktop/tests/test_msix_manifest.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add .github/workflows/build-windows-msix.yml apps/desktop/tests/test_msix_workflow.py
git commit -m "$(cat <<'EOF'
Add manual GitHub Actions workflow for Windows MSIX spike.

EOF
)"
```

---

### Task 4: Spike 操作文档 + 规格状态回写

**Files:**
- Create: `docs/APP store 相关/文书通-MSIX-spike.md`
- Modify: `docs/superpowers/specs/2026-08-05-msix-spike-design.md`（状态行指向本计划）

**Interfaces:**
- Consumes: Artifact 名、证书安装命令、§验收与 kill（规格 §5–§6）
- Produces: 可供 Windows 验收者照做的短文

- [ ] **Step 1: 写 spike 文档**

创建 `docs/APP store 相关/文书通-MSIX-spike.md`，至少包含：

```markdown
# 文书通 · Windows MSIX Spike

对应规格：`docs/superpowers/specs/2026-08-05-msix-spike-design.md`。  
**本阶段不提交 Partner Center。**

## 1. 打出 MSIX

1. GitHub → Actions → **Build Windows MSIX** → Run workflow
2. 下载 Artifact：`wenshutong-windows-msix`（`*.msix` + `devcert.pfx`）

## 2. 本机安装（Windows）

1. 安装 winapp（若需）：`winget install microsoft.winappcli`
2. **管理员** PowerShell：`winapp cert install .\devcert.pfx`（或等价信任开发证书）
3. `Add-AppxPackage .\文书通_*.msix`（以实际文件名为准）
4. 开始菜单启动「文书通」

## 3. 验收清单

- [ ] 应用可启动
- [ ] Runtime/对话可用（配置模型后发一句）
- [ ] 打开文件夹工作区
- [ ] 至少一个预置技能跑通（或受控失败而非崩溃）

## 4. 失败时

按规格 §6 Kill Criteria 记录现象与回退建议（NSIS 直链 / EXE+证书）。
```

- [ ] **Step 2: 更新规格状态行**

将规格表头「状态」改为：`已确认；实现计划见 docs/superpowers/plans/2026-08-05-msix-spike.md`

- [ ] **Step 3: 文档自检**

Run:

```bash
rg -n "Build Windows MSIX|wenshutong-windows-msix|Kill|devcert" "docs/APP store 相关/文书通-MSIX-spike.md" "docs/superpowers/specs/2026-08-05-msix-spike-design.md"
```

Expected: 均有命中

- [ ] **Step 4: Commit**（仅当用户要求时）

```bash
git add "docs/APP store 相关/文书通-MSIX-spike.md" docs/superpowers/specs/2026-08-05-msix-spike-design.md
git commit -m "$(cat <<'EOF'
Document MSIX spike install/verify steps and link the plan.

EOF
)"
```

---

### Task 5: 端到端核对（契约 + 提醒跑 Actions）

**Files:**
- 无新代码（只读验证）

**Interfaces:**
- Consumes: Task 1–4 产物

- [ ] **Step 1: 跑全部相关契约测试**

Run:

```bash
python3 -m pytest \
  apps/desktop/tests/test_msix_manifest.py \
  apps/desktop/tests/test_build_windows_msix_flag.py \
  apps/desktop/tests/test_msix_workflow.py \
  apps/desktop/tests/test_microsoftstore_conf.py \
  apps/desktop/tests/test_msstore_workflow.py \
  -v
```

Expected: 全部 PASS（含既有 MS Store EXE 契约，证明未破坏）

- [ ] **Step 2: 确认 NSIS 工作流无意外 diff**

Run:

```bash
git diff -- .github/workflows/build-windows.yml .github/workflows/build-windows-msstore.yml
```

Expected: 无输出（或仅与本计划无关的既有本地改动；实现者不得改这两文件）

- [ ] **Step 3: 提醒用户**

在实现完成后告知用户：

1. 推送含工作流的提交后，手动跑 **Build Windows MSIX**
2. 在 Windows 上下载 Artifact，按 `文书通-MSIX-spike.md` 安装验收
3. 通过 → 另开上架规格；失败 → 执行 kill，回 EXE+证书或直链

---

## Plan self-review (vs spec)

| 规格项 | 对应 Task |
|--------|-----------|
| winapp 打包 unpackaged + 独立 workflow | Task 2–3 |
| 不改 NSIS / MS Store EXE 行为 | Task 3 测试 + Task 5 |
| 自签名旁加载 | Task 2 cert generate + Task 4 文档 |
| 本机 Windows 验收路径 | Task 4 §3 |
| Kill / 回退 | Task 4 §4 |
| sidecar resources 必进包 | Task 2 舞台步骤 |
| MakeAppx 回退 | Task 3 注明；主路径仍为 winapp |
| 短文路径 | Task 4 |

无 TBD 占位；`-Msix` 与 `-MicrosoftStore` 互斥已写明。
