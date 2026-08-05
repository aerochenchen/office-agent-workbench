# 文书通 Windows MSIX Spike 设计规格

| 项 | 内容 |
|---|---|
| 状态 | 已确认；实现计划见 `docs/superpowers/plans/2026-08-05-msix-spike.md` |
| 日期 | 2026-08-05 |
| 范围 | 同一仓库内用 GitHub Actions 产出可在 Windows 本机安装的 MSIX，验证核心办事路径；**不**做 Partner Center 正式提交 |
| 非目标 | 商店上架认证、生产 Authenticode 采购、替换/删除现有 NSIS 直链与 EXE 商店工作流、winget、自动更新改造 |

相关既有规格：`docs/superpowers/specs/2026-08-05-microsoft-store-exe-gha-design.md`（EXE/MSI 路径；本 spike 与之并行，互不阻塞）。

---

## 1. Problem Statement

如何在不重写业务功能的前提下，验证「文书通」能否以 **真 MSIX** 形态在 Windows 上安装并跑通核心路径，从而为后续 Microsoft Store（MSIX 免费重签）提供去留依据？

背景约束：

- Tauri 2 **不原生**产出 MSIX；商店若走 EXE/MSI 则发布者须自备 Trusted Root 代码签名证书。
- 真 MSIX 上架可由商店重签，但 Tauri + PyInstaller sidecar（`127.0.0.1:8765`、`~/.office-agent`、resources 布局）在打包身份下风险未知。
- 开发以 Mac 为主；Windows 构建已有 GHA；验收者有本机 Windows 可安装测试。
- 用户已确认一期只做 **spike**（选项 1），不是直接冲上架。

---

## 2. Decision

采用 **方案 A：`winapp`（或等价官方工具链）打包 Tauri 未打包产物 + 独立手动工作流**。

1. **复用**现有 Windows 构建前半段（Runtime PyInstaller onedir → stage → Tauri 构建），得到含 `resources/runtime`、`resources/bundled` 的可运行目录或等价布局。
2. **新增** MSIX 打包步骤（优先微软 [winapp CLI](https://github.com/microsoft/winappCli) 对 Tauri 的指引；若工具链卡死，允许回退到 MakeAppx + 手写最小 `AppxManifest`，仍属同一决策）。
3. **新建**独立 GitHub Actions 工作流（仅 `workflow_dispatch`），上传 `*.msix` Artifact。
4. **不修改** `build-windows.yml` / `build-windows-msstore.yml` 的对外行为；NSIS 直链与 EXE 商店包继续可用。
5. Spike 阶段可用 **自签名/开发证书** 仅供本机旁加载安装；不以生产签名为目标。
6. 验收在贡献者 **本机 Windows** 完成；Mac 只负责改仓库与触发 CI。

不采用：NSIS→MSIX 转换器作为主路径；不在本 spike 内提交 Partner Center。

---

## 3. Architecture

```
[workflow_dispatch]
        │
        ▼
 GitHub Actions (windows-latest)
   · 对齐现有 Windows 依赖（Python / Node / Rust / 缓存）
   · 构建 unpackaged 应用树（桌面壳 + resources/runtime + bundled skills）
   · winapp pack（或 MakeAppx）→ 文书通_*.msix
        │
        ▼
 Artifact: wenshutong-windows-msix
        │
        ▼
 本机 Windows
   · 启用开发者模式 / 信任测试证书（按工具链要求）
   · 安装 MSIX
   · 按 §7 验收清单测试
        │
        ├── 通过 → 另开「MSIX 上架」规格（Partner Center）
        └── 失败 → 按 §6 退出，回 EXE + 证书或继续直链分发
```

---

## 4. Components

### 4.1 构建与工作流

| 项 | 约定 |
|---|---|
| 工作流路径 | `.github/workflows/build-windows-msix.yml`（名称建议：`Build Windows MSIX`） |
| 触发 | 仅 `workflow_dispatch` |
| Runner | `windows-latest` |
| Artifact | `wenshutong-windows-msix`（内含至少一个 `*.msix`） |
| 与现有脚本关系 | 优先扩展 `scripts/build-windows.ps1` 增加 `-Msix`（默认关闭）；或新增 `scripts/build-windows-msix.ps1` 调用公共步骤。**禁止**改变默认 NSIS 行为 |

### 4.2 应用树（打包输入）

与现网 NSIS 包内容对齐的最小集合：

- Tauri 主程序（文书通）
- `resources/runtime/`（`office-agent-runtime.exe` + `_internal/`）
- `resources/bundled/` 预置轻量技能
- 启动仍由壳拉起 sidecar：`--host 127.0.0.1 --port 8765`

### 4.3 清单与身份（spike 级）

- 使用测试用 Package Identity（Publisher 可用自签名主题）；**不**要求与最终商店 Publisher 一次定死。
- 版本号与 `tauri.conf.json` 的 `0.1.0` 对齐为四段式时按工具要求补零（例如 `0.1.0.0`）。
- 能力声明：仅声明 spike 验证所需的最小能力；避免一上来全开放。

### 4.4 可能的适配改动（仅测挂时）

允许在 spike 中做**最小**代码改动，优先顺序：

1. sidecar / resources 路径解析（安装目录 vs 打包路径）
2. 用户数据目录：若 `~/.office-agent` 在打包身份下不可写，改为包可写位置或 `OFFICE_AGENT_DATA` 默认策略
3. loopback `8765` / 本机 HTTP 在打包身份下的连通性

不在本 spike 重做技能业务逻辑或 UI。

### 4.5 文档

短文：`docs/APP store 相关/文书通-MSIX-spike.md` —— 如何下 Artifact、本机如何安装测试证书包、验收步骤、失败时如何记录。

---

## 5. Acceptance Criteria（通过）

同时满足：

1. GHA `Build Windows MSIX` 手动运行成功，产出 Artifact `wenshutong-windows-msix`。
2. 本机 Windows 能安装该 MSIX（开发旁加载即可）。
3. 安装后应用可启动；Runtime sidecar 可起来（或等价可达）。
4. 可在设置中配置 OpenAI 兼容模型并完成至少一轮对话。
5. 可打开本地文件夹工作区，并成功跑通 **至少一个** 预置技能（例如公文排版或文档整理，以当时界面已启用者为准）。
6. 现有 `build-windows.yml` / `build-windows-msstore.yml` 无行为回归（契约测试或等价检查仍通过）。

---

## 6. Kill Criteria（失败即停）

出现任一条，**结束 MSIX spike**，默认回退建议为：继续 NSIS 直链；若仍要商店列表则采购 IV/OV 代码签名走 EXE 路径：

1. 安装后主程序无法稳定启动，或 sidecar 无法在合理工作量内拉起。
2. 工作区读写或技能执行因打包身份/路径限制，需大规模重写沙盒/权限模型才能继续。
3. 预估「仅为打包适配」的改动面明显超过 spike 边界（经验阈值：核心启动/路径以外还要改大量业务模块）。
4. 工具链（winapp/MakeAppx）在 GHA 上无法稳定产出可装包，且两周内无可行替代。

失败时在 spike 文档写明：现象、已尝试路径、建议回退方案。

---

## 7. Verification（本机 Windows）

最低手工路径：

1. 安装 MSIX。
2. 启动文书通。
3. 设置 → 配置可用模型地址与 Key → 发送一句对话。
4. 打开含示例 `.docx` 的文件夹。
5. 触发一个已启用技能并得到可打开的结果文件（或明确的成功/受控失败，而非进程崩溃）。

可选：卸载后确认用户数据目录策略符合预期（是否保留 `~/.office-agent`）。

---

## 8. Out of Scope / Later

- Partner Center 创建 MSIX 产品、商店截图/分级/提交认证
- 生产代码签名（商店重签前的提交用包策略另定）
- 用 MSIX 替换 NSIS 对内分发
- winget、自动更新协议变更
- 将现有 EXE Partner Center 草稿改为 MSIX（上架阶段再处理）

---

## 9. Risks

| 风险 | 缓解 |
|---|---|
| Sidecar + 固定端口在打包身份下失败 | 验收优先覆盖；失败走 kill |
| `~/.office-agent` 写入被拒 | 最小改默认数据目录 |
| 包体积大（Runtime + WebView2） | spike 不优化体积；仅记录 |
| winapp 文档/工具变更 | 允许 MakeAppx 回退 |
| 与 EXE 商店草稿并存造成混淆 | 文档写清：spike ≠ 上架；EXE 草稿可搁置 |

---

## 10. References

- [Tauri — Microsoft Store](https://v2.tauri.app/distribute/microsoft-store/)（官方仍以 EXE/MSI 为主）
- [Microsoft winapp CLI — Tauri guide](https://github.com/microsoft/winappCli/blob/main/docs/guides/tauri.md)
- [Code signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)（MSIX 商店重签 vs EXE 自签）
- 现有：`scripts/build-windows.ps1`、`.github/workflows/build-windows*.yml`、`apps/desktop/src-tauri/src/lib.rs`（sidecar）
