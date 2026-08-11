# 文书通 PKS 基线（银河麒麟 × 飞腾 aarch64）设计规格

| 项 | 内容 |
|---|---|
| 状态 | 已确认；实现计划见 `docs/superpowers/plans/2026-08-11-kylin-pks-baseline.md` |
| 日期 | 2026-08-11 |
| 范围 | 在有网 Mac 上用 Docker（linux/aarch64）打出可 U 盘离线安装的 PKS 桌面包；在断网银河麒麟 V10 SP1 + WPS 信创上完成 B 档验收 |
| 非目标 | 龙芯/海光/统信、OFD/国密签章、金仓/TongWeb、兼容证书送测、写作 RAG 重依赖、在麒麟机上日常开发 |

---

## 1. Problem Statement

党政办公终端主流基线为 **PKS（飞腾 + 银河麒麟 + 安全）**。文书通当前仅交付 Windows NSIS / macOS 包，无法在断网麒麟 aarch64 终端安装验收。

约束：

1. 验收目标为 **B 档**：安装启动 →（内网）模型对话 → 打开工作区 → **WPS 信创下公文排版/校对主路径可跑通**。
2. 已具备验收机：`银河麒麟桌面 V10 SP1` + `aarch64` + `/usr/bin/wps`；**全程断网**，无 Cursor。
3. 无「可联网的 aarch64 真机构建机」；开发继续在 Mac + Cursor。
4. 用户侧必须支持 **U 盘拷贝后断网安装**。

---

## 2. Decision

采用 **方案 1：有网 Mac + Docker `linux/arm64` 出包 → U 盘只搬运安装产物 → 断网麒麟安装验收**。

| 角色 | 机器 | 职责 |
|------|------|------|
| 开发机 | Mac + Cursor（有网） | 改代码、跑单元测试、触发 Docker 构建 |
| 构建环境 | Docker `linux/arm64` | 编译 Tauri 壳、PyInstaller Runtime、打 deb + 离线 deps |
| 验收机 | 断网麒麟 V10 SP1 aarch64 | 仅安装与 B 档实机验收，不编译、不装 IDE |

明确不做：

- 首期不在断网麒麟本机编译（方案 2 仅作兼容性兜底，不进主路径）。
- 首期不做 x86→aarch64 裸机交叉编译主路径（WebKit / PyInstaller 风险过高）。

---

## 3. Architecture

```
[Mac + Cursor，有网]
        │
        ▼
Docker linux/arm64 构建镜像
  · Node / Rust / Python 3.11
  · webkit2gtk 等构建依赖
  · 对齐麒麟 V10 SP1 可用的运行时库策略（见 §5）
        │
        ├─ PyInstaller onedir → resources/runtime/
        ├─ bundled/skills     → resources/bundled/
        ├─ NOTICE             → resources/NOTICE
        └─ tauri build (deb)  → 文书通_*_aarch64.deb
        │
        ▼
发布目录（可整包打 tar 拷 U 盘）
  wenshutong-pks-<ver>-aarch64/
    ├─ 文书通_*_aarch64.deb          # 主包
    ├─ deps/*.deb                    # 系统依赖离线包（若主包未完全自包含）
    ├─ install-offline.sh            # 断网安装脚本
    └─ README-安装说明.txt
        │
        ▼ U 盘
[断网麒麟 V10 SP1 + WPS]
  install-offline.sh → 启动 → 配内网模型 → 办文验收
```

包内组件与现有标准底座同构（见 `packaging/README-standard.md`）：

- 桌面壳（Tauri 2）
- Runtime sidecar（本地 `127.0.0.1:8765`）
- 预置轻量 Skill（至少包含公文排版、通篇校对）
- **不含** 写作 RAG / Torch 等重依赖

数据与网络行为保持产品既有原则：

- 材料在用户选定工作区；沙箱不越界
- 模型仅连设置中白名单地址（内网）；断网且无内网模型时，本地文件类能力仍应可启动，对话给出明确不可达提示

---

## 4. Acceptance Criteria（B 档）

在目标验收机（麒麟 V10 SP1 · aarch64 · 已装 WPS · 断网）上：

| # | 用例 | 通过标准 |
|---|------|----------|
| 1 | 断网安装 | `install-offline.sh`（或文档步骤）成功；桌面/菜单可启动 |
| 2 | 冷启动 | 主窗口出现；Runtime `/health` 可达（或等价就绪态） |
| 3 | 模型配置 | 设置可保存 api_base / api_key / model / allowed_hosts；无内网模型时有明确错误，不崩溃 |
| 4 | 工作区 | 原生选文件夹或等价路径选择成功；后续工具落在该目录 |
| 5 | 公文排版 | 对样例 `.docx` 跑通排版技能，产出可被 **WPS** 打开的结果文件 |
| 6 | 通篇校对 | 对样例文稿跑通校对技能，结果可在 WPS 中查看 |

说明：

- 完整多轮「聪明对话」若现场无内网模型，可用用例 3 的降级标准；有模型窗口时再补跑一轮真实对话。
- 首期不要求 OFD、电子签章、奇安信兼容证书。

---

## 5. Build & Packaging Design

### 5.1 新增构建入口

- `scripts/build-kylin-pks.sh`：宿主入口（检测 Docker、平台、产出目录）
- `packaging/pks/`：Docker 上下文、离线安装脚本、依赖清单
- 可选：`packaging/runtime-linux.spec` 或扩展现有 `packaging/runtime.spec` 以支持 linux

### 5.2 Tauri / Linux

- `tauri.conf.json`（或 linux 覆盖配置）增加 `deb` 目标；资源 staging 与 Windows 脚本对称
- 审查 `apps/desktop/src-tauri/src/lib.rs`：去掉阻碍 Linux 的 Windows-only 假设；保证 sidecar 路径、进程拉起、退出清理在 linux 可用
- WebView：Linux 使用系统 WebKitGTK；安装包必须能处理「目标机缺库」

### 5.3 Runtime sidecar

- 在 Docker linux/arm64 内用 PyInstaller onedir 产出 `office-agent-runtime`
- 打入 `src-tauri/resources/runtime/`
- 启动参数、token、8765 绑定行为与现网 Windows 包一致

### 5.4 断网依赖策略（关键）

优先顺序：

1. 尽量让主程序 + sidecar 自包含，减少系统依赖面
2. 仍缺的共享库（尤其 WebKitGTK 相关）列入 `deps/*.deb`，由 `install-offline.sh` 先于主包安装
3. `deps` 清单以 **麒麟 V10 SP1 aarch64** 实机 `ldd` / 试装结果回填，不在规格阶段臆造包名全集

### 5.5 版本与产物命名

- 版本号跟随 `apps/desktop/src-tauri/tauri.conf.json` 的 `version`
- 产物示例：`文书通_<version>_aarch64.deb`
- 分发目录：`wenshutong-pks-<version>-aarch64/`

---

## 6. Verification Artifacts

新增文档（实现阶段落地）：

| 文档 | 用途 |
|------|------|
| `packaging/README-kylin-pks.md` | 构建者：如何在 Mac 上 Docker 出包 |
| `packaging/VERIFY-kylin-pks.md` | 验收者：断网安装 + B 档清单 |
| `packaging/验收清单-PKS-给非开发人员.md` | 非开发人员跟测（可从现有 Windows 验收清单裁剪） |

随 U 盘提供只读样例材料（小体积 `.docx`），避免验收机无材料。

---

## 7. Out of Scope

- 龙芯 LoongArch、海光 x86、统信 UOS 首期适配
- OFD 版式、国密签章、电子公文交换闭环
- 人大金仓 / 达梦 / 东方通等服务器栈（本产品为桌面 Agent，不引入）
- 麒麟软商店上架流程与厂商兼容互认证正式送测
- 写作 RAG 可选包、Torch、本地 embedding
- 在验收机上安装 Cursor / 配置日常开发环境

---

## 8. Risks

| 风险 | 影响 | 缓解 |
|------|------|------|
| Docker 内库版本与麒麟 V10 SP1 不一致 | 安装后无法启动 WebView / 动态库错误 | 以验收机 `ldd` 回填 deps；必要时换用更贴近麒麟的基础镜像或降低 WebKit 假设 |
| Apple Silicon Docker arm64 构建慢/失败 | 出包阻塞 | 固定镜像标签与缓存挂载；记录可复现命令 |
| PyInstaller 在 linux aarch64 漏收依赖 | Runtime 起不来 | 构建后在容器内跑 `/health`；验收机再跑一遍 |
| 无内网模型导致对话无法演示 | 验收争议 | 规格已区分「配置/报错」与「真实对话」；样例办文路径不依赖模型聪明度时可尽量脚本化 |
| WPS 与 python-docx 样式差异 | 排版结果「能开但不好看」 | B 档先要求「可打开 + 主流程成功」；版式精细度单列后续 |

---

## 9. Success Definition

同时满足：

1. 有网 Mac 上一键（或文档化少数命令）打出 `wenshutong-pks-*-aarch64` 目录  
2. U 盘拷到断网麒麟后按说明安装成功  
3. B 档验收表（§4）全部勾选通过  
4. 不引入服务器信创组件，不扩大首期 CPU/OS 矩阵  

---

## 10. Next Step

规格审阅通过后，编写实现计划：

`docs/superpowers/plans/2026-08-11-kylin-pks-baseline.md`
