# Windows 标准底座 NSIS 安装包设计规格

| 项 | 内容 |
|---|---|
| 状态 | 已确认；实现计划见 `docs/superpowers/plans/2026-07-26-windows-nsis-installer.md` |
| 日期 | 2026-07-26 |
| 范围 | 在本机打出标准底座 `*-setup.exe`；安装包与桌面应用共用同一套图标 |
| 非目标 | 写作 RAG 选装包、代码签名、改安装模式、重写打包脚本 |

---

## 1. Problem Statement

如何在现有仓库打包链路下，于 Windows 构建机生成可分发的标准底座安装器（NSIS `.exe`），并保证安装器、主程序、开始菜单与桌面快捷方式使用与桌面应用一致的正式图标？

---

## 2. Decision

采用**仓库已有一键脚本**，不新增第二套打包工具：

1. 补齐本机构建依赖（Rust `x86_64-pc-windows-msvc` + 所需 C++ 构建工具）。
2. 在仓库根目录执行 `.\scripts\build-windows.ps1`。
3. 交付 `apps/desktop/src-tauri/target/release/bundle/nsis/文书通_0.1.0_x64-setup.exe`（版本号随 `tauri.conf.json`）。

图标不重新设计：沿用 `apps/desktop/branding/app-icon.png` 生成的 `src-tauri/icons/icon.ico`，并由 `tauri.conf.json` 的 `bundle.icon` / `bundle.windows.nsis.installerIcon` / `uninstallerIcon` 统一引用。

---

## 3. Architecture

```
branding/app-icon.png
        │
        ▼
src-tauri/icons/icon.ico  ──► 主程序 .exe / 快捷方式 / NSIS 安装·卸载图标
        │
runtime (PyInstaller onedir) ──► resources/runtime/
bundled/skills              ──► resources/bundled/
NOTICE                      ──► resources/NOTICE
        │
        ▼
tauri build (targets: nsis) ──► 文书通_*_x64-setup.exe
```

包内组件与 `packaging/README-standard.md` 一致：桌面壳、Runtime sidecar、预置轻量 Skill；**不含** `optional-skills/gongwen-rag-writing` 与 Torch 等重依赖。

安装行为保持现状：`installMode: currentUser`；WebView2 使用 `fixedRuntime`（随包捆绑 Fixed Version，内网可离线安装）；用户数据在 `%USERPROFILE%\.office-agent\`，卸载不删该目录。

---

## 4. Build Steps（实现计划将按此展开）

| 步骤 | 动作 | 成功标准 |
|------|------|----------|
| 1 | 安装/校验 Rust MSVC toolchain | `rustc` / `cargo` 可用 |
| 2 | 确认 Node、Python 3.11+、`NOTICE` 存在 | 与脚本前置检查一致 |
| 3 | 运行 `.\scripts\build-windows.ps1` | 无非零退出 |
| 4 | 定位 NSIS 产物 | `bundle/nsis/*-setup.exe` 存在 |
| 5 | 图标抽查 | 安装器文件图标与 `icon.ico` 一致（资源管理器可见） |

可选：构建后按 `packaging/VERIFY-windows.md` 做干净机安装验收（本规格不强制在同一会话完成）。

---

## 5. Out of Scope

- 写作 RAG 可选 zip / 重量依赖打入底座
- Authenticode 签名与智能筛选提示消除
- 改为 per-machine / MSI / 便携 zip
- 修改 `app-icon.png` 或重新跑 `tauri icon`（仅当源图变更时才需要）

---

## 6. Risks

| 风险 | 缓解 |
|------|------|
| 本机缺少 Rust / VS Build Tools | 安装 `rustup` 默认 MSVC toolchain；缺链路工具时安装「使用 C++ 的桌面开发」或 Build Tools |
| 首次 crates/npm 下载慢或需镜像 | 使用构建机已有网络/镜像；失败时按日志重试 |
| 构建耗时长 | 接受首次全量构建；后续可用 `-SkipSidecar` 仅在 sidecar 已 stage 时加速 |

---

## 7. Acceptance

- [ ] 产出 `文书通_*_x64-setup.exe`
- [ ] 安装器与主程序图标为正式 `icon.ico`（同源 `app-icon.png`）
- [ ] 包为标准底座（无写作 RAG 重依赖）
- [ ] 构建过程未改动安装模式、签名策略或品牌源图
