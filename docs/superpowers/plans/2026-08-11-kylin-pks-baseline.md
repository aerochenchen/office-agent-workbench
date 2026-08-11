# 文书通 PKS 基线（麒麟 aarch64）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在有网 Mac 上用 Docker（`linux/arm64`）打出可 U 盘断网安装的 `wenshutong-pks-*-aarch64` 交付目录，并在银河麒麟 V10 SP1 + WPS 上按 B 档验收办文主路径。

**Architecture:** 镜像 Windows/macOS 一键脚本：容器内 PyInstaller onedir → stage `resources/{runtime,bundled}` → `tauri build --bundles deb` → 组装 `deb + deps/ + install-offline.sh`。验收机只安装不编译。

**Tech Stack:** Docker `linux/arm64`、Python 3.11、PyInstaller、Node/npm、Rust stable、Tauri 2、WebKitGTK、deb

## Global Constraints

- 规格：`docs/superpowers/specs/2026-08-11-kylin-pks-baseline-design.md`（已确认）
- 目标 OS/Arch：银河麒麟桌面 V10 SP1 · aarch64；办公套件：WPS 信创（`/usr/bin/wps`）
- 构建：Mac + Docker；**禁止**要求断网麒麟机联网或安装 Cursor
- 交付：标准底座；**不含**写作 RAG / Torch
- 验收：B 档（安装、启动、模型配置/对话、工作区、公文排版、通篇校对 + WPS 可打开）
- 不擅自 `git commit`（除非用户明确要求）
- 不引入金仓 / 达梦 / TongWeb；首期不做龙芯/海光/统信/OFD/国密

---

## File map

| 路径 | 职责 |
|------|------|
| `scripts/build-kylin-pks.sh` | 宿主入口：调 Docker 出包并组装分发目录 |
| `packaging/pks/Dockerfile` | linux/arm64 构建镜像 |
| `packaging/pks/build-inside.sh` | 容器内：sidecar → stage → tauri deb |
| `packaging/pks/install-offline.sh` | 断网麒麟安装脚本 |
| `packaging/pks/deps.manifest` | 离线系统依赖 deb 清单（由实机回填） |
| `apps/desktop/src-tauri/tauri.kylin.conf.json` | Linux/deb 打包覆盖配置 |
| `apps/desktop/src-tauri/src/lib.rs` | 确认/修补 Linux sidecar 拉起（已有 unix 分支） |
| `apps/desktop/tests/test_build_kylin_pks_script.py` | 构建脚本契约测试 |
| `apps/desktop/tests/test_pks_install_offline.py` | 离线安装脚本契约测试 |
| `packaging/README-kylin-pks.md` | 构建者说明 |
| `packaging/VERIFY-kylin-pks.md` | 验收清单 |
| `packaging/验收清单-PKS-给非开发人员.md` | 非开发跟测 |
| `packaging/pks/fixtures/sample-format.docx` | 排版验收样例（可从现有 skill fixture 拷贝） |
| 产物（不入库）：`packaging/dist/pks/wenshutong-pks-<ver>-aarch64/` | U 盘交付物 |

---

### Task 1: 构建/安装脚本契约测试（先红）

**Files:**
- Create: `apps/desktop/tests/test_build_kylin_pks_script.py`
- Create: `apps/desktop/tests/test_pks_install_offline.py`
- Create（稍后实现，本任务先写测试）: `scripts/build-kylin-pks.sh`, `packaging/pks/install-offline.sh`

**Interfaces:**
- Produces: 失败中的契约测试，锁定脚本必须暴露的标志与关键字

- [ ] **Step 1: 写入构建脚本契约测试**

```python
"""Contract: build-kylin-pks.sh exists and documents Docker linux/arm64 offline bundle."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "build-kylin-pks.sh"


def test_build_kylin_pks_script_exists_and_is_executable_bit_friendly():
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!"), "missing shebang"
    assert "linux/arm64" in text or "linux/aarch64" in text
    assert "docker" in text.lower()
    assert "packaging/pks" in text or "packaging/pks/" in text
    assert "wenshutong-pks" in text
    assert "install-offline.sh" in text
```

- [ ] **Step 2: 写入离线安装脚本契约测试**

```python
"""Contract: PKS offline installer never requires network."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INSTALL = ROOT / "packaging" / "pks" / "install-offline.sh"


def test_install_offline_script_is_airgap_safe():
    assert INSTALL.is_file(), f"missing {INSTALL}"
    text = INSTALL.read_text(encoding="utf-8")
    assert text.startswith("#!")
    assert "dpkg" in text
    # Must not curl/wget the internet
    lower = text.lower()
    assert "curl " not in lower
    assert "wget " not in lower
    assert "apt-get update" not in lower
    assert "deps" in text
```

- [ ] **Step 3: 跑测试确认失败（文件尚不存在）**

Run:
```bash
cd /Users/chenzai/内部办公智能体
python3 -m pytest apps/desktop/tests/test_build_kylin_pks_script.py apps/desktop/tests/test_pks_install_offline.py -v
```
Expected: FAIL，`missing .../build-kylin-pks.sh` 与/或 `missing .../install-offline.sh`

- [ ] **Step 4: 提交（仅当用户要求 commit 时执行；默认跳过）**

---

### Task 2: 离线安装脚本 + deps 清单骨架

**Files:**
- Create: `packaging/pks/install-offline.sh`
- Create: `packaging/pks/deps.manifest`
- Create: `packaging/pks/deps/.gitkeep`

**Interfaces:**
- Consumes: Task 1 契约
- Produces: 可在麒麟上执行的安装入口（deps 可先空，靠主包自包含；实机回填）

- [ ] **Step 1: 创建 `deps.manifest`**

```text
# Offline system .deb packages for 银河麒麟 V10 SP1 aarch64.
# One package name per line. Filled after first failed install / ldd on device.
# Example (do not assume these exact names until verified):
# libwebkit2gtk-4.1-0
```

- [ ] **Step 2: 创建 `install-offline.sh`**

```bash
#!/usr/bin/env bash
# Offline installer for 文书通 PKS bundle on 银河麒麟 V10 (aarch64).
# Run from the extracted wenshutong-pks-*-aarch64 directory. NO NETWORK.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEPS_DIR="${ROOT}/deps"
cd "${ROOT}"

if [[ "$(uname -m)" != "aarch64" && "$(uname -m)" != "arm64" ]]; then
  echo "ERROR: expected aarch64 host, got $(uname -m)" >&2
  exit 1
fi

shopt -s nullglob
deps=( "${DEPS_DIR}"/*.deb )
if ((${#deps[@]} > 0)); then
  echo "==> Installing offline deps (${#deps[@]} packages)"
  sudo dpkg -i "${deps[@]}" || sudo dpkg --configure -a
fi

mains=( "${ROOT}"/文书通_*.deb "${ROOT}"/wenshutong_*.deb )
main=""
for c in "${mains[@]}"; do
  [[ -f "${c}" ]] || continue
  main="${c}"
  break
done
if [[ -z "${main}" ]]; then
  echo "ERROR: no 文书通_*.deb in ${ROOT}" >&2
  exit 1
fi

echo "==> Installing ${main}"
sudo dpkg -i "${main}" || sudo dpkg --configure -a

echo "==> Done. Start 文书通 from the application menu, then configure intranet model."
```

- [ ] **Step 3: `chmod +x packaging/pks/install-offline.sh` 并重跑契约测试中的 install 文件**

Run:
```bash
chmod +x packaging/pks/install-offline.sh
python3 -m pytest apps/desktop/tests/test_pks_install_offline.py -v
```
Expected: PASS

---

### Task 3: Tauri Linux/deb 覆盖配置

**Files:**
- Create: `apps/desktop/src-tauri/tauri.kylin.conf.json`
- Modify: `apps/desktop/src-tauri/tauri.conf.json` 仅当必须——优先用 `--config tauri.kylin.conf.json` 合并，避免破坏 Windows `nsis` 默认

**Interfaces:**
- Produces: deb bundle 配置（productName/资源与现网一致）

- [ ] **Step 1: 写入覆盖配置**

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "bundle": {
    "active": true,
    "targets": ["deb"],
    "linux": {
      "deb": {
        "depends": []
      }
    }
  }
}
```

说明：`depends` 首期保持空数组，真实依赖放入 U 盘 `deps/*.deb` + `deps.manifest`，避免 deb 元数据写死与麒麟包名不一致。

- [ ] **Step 2: 契约测试扩展——kylin conf 存在且 targets 含 deb**

在 `apps/desktop/tests/test_build_kylin_pks_script.py` 追加：

```python
KYLIN_CONF = ROOT / "apps" / "desktop" / "src-tauri" / "tauri.kylin.conf.json"


def test_tauri_kylin_conf_targets_deb():
    import json

    data = json.loads(KYLIN_CONF.read_text(encoding="utf-8"))
    assert "deb" in data["bundle"]["targets"]
```

Run:
```bash
python3 -m pytest apps/desktop/tests/test_build_kylin_pks_script.py::test_tauri_kylin_conf_targets_deb -v
```
Expected: PASS

---

### Task 4: 确认 Linux sidecar 拉起路径（代码审查 + 最小修补）

**Files:**
- Read/Modify: `apps/desktop/src-tauri/src/lib.rs`
- Create: `apps/desktop/tests/test_sidecar_name_linux_contract.py`（文本契约，避免本机无 Rust 测 linux）

**Interfaces:**
- Consumes: 现有 `sidecar_exe_name()` / `find_sidecar_exe()` / `venv_python()`
- Produces: 保证非 Windows 使用 `office-agent-runtime`（无 `.exe`）

- [ ] **Step 1: 写入文本契约**

```python
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "src-tauri" / "src" / "lib.rs"


def test_sidecar_exe_name_has_unix_branch():
    text = LIB.read_text(encoding="utf-8")
    assert 'office-agent-runtime.exe' in text
    assert '"office-agent-runtime"' in text
    assert "cfg!(windows)" in text or "cfg(windows)" in text
```

- [ ] **Step 2: 阅读 `find_sidecar_exe` / spawn 逻辑**

确认 Linux 上候选路径包含：
- `{exe_dir}/resources/runtime/office-agent-runtime`
- `resource_dir()/runtime/office-agent-runtime`

若 deb 安装后实际布局不同，在本任务追加候选路径（例如 `/usr/lib/文书通/resources/runtime/...`），以 `tauri build` 后容器内 `find` 结果为准（Task 6 回填）。

- [ ] **Step 3: 跑契约**

Run:
```bash
python3 -m pytest apps/desktop/tests/test_sidecar_name_linux_contract.py -v
```
Expected: PASS

---

### Task 5: Docker 构建镜像与容器内构建脚本

**Files:**
- Create: `packaging/pks/Dockerfile`
- Create: `packaging/pks/build-inside.sh`

**Interfaces:**
- Consumes: 仓库源码挂载到 `/src`
- Produces: 容器内可执行的构建步骤；输出 deb 到挂载的 `packaging/dist/pks/out`

- [ ] **Step 1: 写入 `Dockerfile`（Ubuntu 22.04 arm64 作为首期构建根；与麒麟差异靠 deps 兜底）**

```dockerfile
# syntax=docker/dockerfile:1
FROM --platform=linux/arm64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/root/.cargo/bin:/usr/local/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl build-essential pkg-config \
    libwebkit2gtk-4.1-dev librsvg2-dev patchelf \
    libssl-dev libgtk-3-dev libayatana-appindicator3-dev \
    python3 python3-pip python3-venv \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Node 20 via nodesource if distro node too old — prefer:
# keep ubuntu node if >=18; otherwise install node 20 in a follow-up patch after first build log.

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable \
    && rustup target add aarch64-unknown-linux-gnu

WORKDIR /src
```

- [ ] **Step 2: 写入 `build-inside.sh`（对齐 `scripts/build-macos.sh` 阶段）**

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/src}"
PACKAGING="${ROOT}/packaging"
DESKTOP="${ROOT}/apps/desktop"
SRC_TAURI="${DESKTOP}/src-tauri"
RESOURCES="${SRC_TAURI}/resources"
VENV="${PACKAGING}/.venv-pks"
DIST_RUNTIME="${PACKAGING}/dist/office-agent-runtime"
STAGED_RUNTIME="${RESOURCES}/runtime"
STAGED_BUNDLED="${RESOURCES}/bundled"
OUT="${PACKAGING}/dist/pks/out"
mkdir -p "${OUT}" "${PACKAGING}/dist"

echo "==> Python venv + runtime deps"
python3 -m venv "${VENV}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
pip install -U pip wheel
pip install -e "${ROOT}/runtime[packaging]"

echo "==> PyInstaller onedir"
rm -rf "${DIST_RUNTIME}"
pyinstaller "${PACKAGING}/runtime.spec" --noconfirm --clean
test -x "${DIST_RUNTIME}/office-agent-runtime"

echo "==> Stage resources"
rm -rf "${STAGED_RUNTIME}" "${STAGED_BUNDLED}"
mkdir -p "${RESOURCES}"
cp -a "${DIST_RUNTIME}" "${STAGED_RUNTIME}"
cp -a "${ROOT}/bundled/." "${STAGED_BUNDLED}/"
bash "${ROOT}/scripts/stage_notice.sh"

echo "==> npm + tauri deb"
cd "${DESKTOP}"
npm ci
npm run build
npx tauri build --bundles deb --config src-tauri/tauri.kylin.conf.json

DEB="$(find "${SRC_TAURI}/target/release/bundle/deb" -name '*.deb' | head -n1)"
test -n "${DEB}"
cp -f "${DEB}" "${OUT}/"
# smoke: binary exists inside package listing
dpkg-deb -c "${OUT}/"*.deb | grep -E 'office-agent-runtime|文书通' | head

echo "==> build-inside done: ${OUT}"
```

- [ ] **Step 3: `chmod +x packaging/pks/build-inside.sh`**

---

### Task 6: 宿主入口 `scripts/build-kylin-pks.sh`

**Files:**
- Create: `scripts/build-kylin-pks.sh`
- Modify: `apps/desktop/tests/test_build_kylin_pks_script.py`（若需补充关键字）

**Interfaces:**
- Consumes: Docker、Task 5 镜像与 `build-inside.sh`、Task 2 安装脚本
- Produces: `packaging/dist/pks/wenshutong-pks-<version>-aarch64/`

- [ ] **Step 1: 写入宿主脚本**

```bash
#!/usr/bin/env bash
# Build PKS (Kylin aarch64) offline bundle via Docker linux/arm64.
# Usage (repo root, networked Mac with Docker):
#   ./scripts/build-kylin-pks.sh
#   ./scripts/build-kylin-pks.sh --clean
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKS="${ROOT}/packaging/pks"
DIST_PKS="${ROOT}/packaging/dist/pks"
OUT_RAW="${DIST_PKS}/out"
IMAGE="wenshutong-pks-builder:ubuntu22-arm64"
CLEAN=0
for arg in "$@"; do
  case "${arg}" in
    --clean) CLEAN=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
  esac
done

command -v docker >/dev/null || { echo "docker required" >&2; exit 1; }

VERSION="$(python3 -c "import json;print(json.load(open('${ROOT}/apps/desktop/src-tauri/tauri.conf.json'))['version'])")"
BUNDLE_DIR="${DIST_PKS}/wenshutong-pks-${VERSION}-aarch64"

if [[ "${CLEAN}" -eq 1 ]]; then
  rm -rf "${DIST_PKS}" "${ROOT}/packaging/.venv-pks"
fi
mkdir -p "${OUT_RAW}"

echo "==> docker build image (${IMAGE})"
docker build --platform=linux/arm64 -t "${IMAGE}" -f "${PKS}/Dockerfile" "${PKS}"

echo "==> docker run build-inside"
docker run --rm --platform=linux/arm64 \
  -v "${ROOT}:/src" \
  -v "${OUT_RAW}:/src/packaging/dist/pks/out" \
  "${IMAGE}" bash /src/packaging/pks/build-inside.sh

echo "==> assemble USB bundle ${BUNDLE_DIR}"
rm -rf "${BUNDLE_DIR}"
mkdir -p "${BUNDLE_DIR}/deps"
cp -f "${OUT_RAW}"/*.deb "${BUNDLE_DIR}/"
cp -f "${PKS}/install-offline.sh" "${BUNDLE_DIR}/"
cp -f "${PKS}/deps.manifest" "${BUNDLE_DIR}/"
# copy any pre-downloaded debs if present
if compgen -G "${PKS}/deps/*.deb" > /dev/null; then
  cp -f "${PKS}/deps/"*.deb "${BUNDLE_DIR}/deps/"
fi
cat > "${BUNDLE_DIR}/README-安装说明.txt" <<EOF
文书通 PKS 离线安装（银河麒麟 V10 SP1 aarch64）

1. 将本目录完整拷贝到目标机（U 盘）
2. 在目录内执行: bash install-offline.sh
3. 从应用菜单启动「文书通」
4. 设置中配置单位内网模型地址
5. 按 packaging/VERIFY-kylin-pks.md 做 B 档验收
EOF
chmod +x "${BUNDLE_DIR}/install-offline.sh"

echo "USB bundle ready: ${BUNDLE_DIR}"
ls -la "${BUNDLE_DIR}"
```

- [ ] **Step 2: `chmod +x` 并跑契约测试**

Run:
```bash
chmod +x scripts/build-kylin-pks.sh packaging/pks/build-inside.sh
python3 -m pytest apps/desktop/tests/test_build_kylin_pks_script.py apps/desktop/tests/test_pks_install_offline.py apps/desktop/tests/test_sidecar_name_linux_contract.py -v
```
Expected: 全部 PASS

---

### Task 7: 文档与验收样例

**Files:**
- Create: `packaging/README-kylin-pks.md`
- Create: `packaging/VERIFY-kylin-pks.md`
- Create: `packaging/验收清单-PKS-给非开发人员.md`
- Create: `packaging/pks/fixtures/`（从 `bundled/skills/government-document-format` 或 digest fixtures 拷贝 1 个小型 docx 作为排版样例；校对样例同理从 `doc-proofread` fixtures 取）

**Interfaces:**
- Produces: 构建者与验收者可独立执行的说明

- [ ] **Step 1: 写 `README-kylin-pks.md`**

内容必须包含：
- 前置：Docker Desktop（启用 containerd / linux/arm64）
- 命令：`./scripts/build-kylin-pks.sh`
- 产物路径：`packaging/dist/pks/wenshutong-pks-<ver>-aarch64/`
- 明确：验收机断网；仅 U 盘拷贝该目录

- [ ] **Step 2: 写 `VERIFY-kylin-pks.md`**

将规格 §4 六条转成勾选清单，并增加：
- `curl -sf http://127.0.0.1:8765/health`（若系统有 curl；否则看 UI 在线态）
- WPS 打开排版/校对产出文件
- 失败时收集：`ldd` 主程序、`journalctl`/应用日志、`/tmp/office-agent-runtime.err.log`

- [ ] **Step 3: 写非开发人员清单**（从 `packaging/验收清单-给非开发人员.md` 裁剪，改成麒麟/WPS 用语）

- [ ] **Step 4: 准备 fixtures**

从现有 skill 目录复制小文件到 `packaging/pks/fixtures/`，并在 VERIFY 中写明路径。

---

### Task 8: 有网 Mac 首次 Docker 出包（工程验证）

**Files:**
- 可能热修：`Dockerfile`（Node 版本）、`build-inside.sh`（npm 锁文件）、`lib.rs`（deb 资源路径）、`deps.manifest`

**Interfaces:**
- Consumes: Task 1–7
- Produces: 真实 `wenshutong-pks-*-aarch64` 目录

- [ ] **Step 1: 构建**

Run:
```bash
cd /Users/chenzai/内部办公智能体
./scripts/build-kylin-pks.sh
```
Expected: 结束时打印 `USB bundle ready: .../wenshutong-pks-1.5.0-aarch64`（版本以 `tauri.conf.json` 为准）；目录内有 `.deb` + `install-offline.sh`

- [ ] **Step 2: 容器内冒烟（若 Step 1 已含 dpkg-deb 列表则复查日志）**

确认 deb 内含 `office-agent-runtime` 与前端资源。

- [ ] **Step 3: 记录阻塞项**

若 WebKit/Node/Rust 失败，按日志最小修补后重跑；不得扩大到龙芯/UOS。

---

### Task 9: 断网麒麟 B 档实机验收（人工）

**Files:**
- 可能更新: `packaging/pks/deps.manifest`、`packaging/pks/deps/*.deb`（从麒麟同版本机或官方 ISO 离线源取得，经 U 盘带回构建侧重新组装）

**Interfaces:**
- Consumes: Task 8 产物
- Produces: 勾选完成的 `VERIFY-kylin-pks.md`；若缺库则回填 deps 后回到 Task 8 重打分发目录

- [ ] **Step 1: U 盘拷贝整个 `wenshutong-pks-*-aarch64` 到麒麟**

- [ ] **Step 2: 执行 `bash install-offline.sh`**

Expected: dpkg 成功；应用菜单出现「文书通」

- [ ] **Step 3: 按 VERIFY 跑完 B 档 6 条**

特别确认：
- 公文排版产出用 **WPS** 打开
- 通篇校对产出用 **WPS** 打开

- [ ] **Step 4: 若动态库缺失**

在麒麟上：
```bash
ldd /path/to/文书通 | grep 'not found'
```
把缺失包名写入 `deps.manifest`，用离线 `.deb` 填入 `packaging/pks/deps/`，回 Mac 重跑 `./scripts/build-kylin-pks.sh`，再 U 盘复测。

---

### Task 10: 规格状态回写

**Files:**
- Modify: `docs/superpowers/specs/2026-08-11-kylin-pks-baseline-design.md` 状态行

- [ ] **Step 1: 将状态改为**

`已确认；实现计划见 docs/superpowers/plans/2026-08-11-kylin-pks-baseline.md`

- [ ] **Step 2: 全量契约测试回归**

Run:
```bash
python3 -m pytest apps/desktop/tests/test_build_kylin_pks_script.py apps/desktop/tests/test_pks_install_offline.py apps/desktop/tests/test_sidecar_name_linux_contract.py -v
```
Expected: PASS

---

## Spec coverage checklist

| 规格要求 | 任务 |
|----------|------|
| Docker linux/arm64 出包 | Task 5–6、8 |
| U 盘断网安装 | Task 2、6、9 |
| 包内壳+Runtime+bundled | Task 5 |
| 不含 RAG/Torch | Global + runtime.spec excludes（沿用） |
| B 档 6 条验收 | Task 7、9 |
| 不在麒麟开发/联网构建 | Global Constraints |
| deps 实机回填 | Task 2、9 |
| 文档 README/VERIFY | Task 7 |

## Placeholder scan

无 TBD/TODO 步骤；deps 包名刻意留空并由 Task 9 实机回填（规格已允许）。
