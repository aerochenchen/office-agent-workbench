# Microsoft Store（EXE/MSI）+ GitHub Actions 设计规格

| 项 | 内容 |
|---|---|
| 状态 | 已确认；实现计划见 `docs/superpowers/plans/2026-08-05-microsoft-store-exe-gha.md` |
| 日期 | 2026-08-05 |
| 范围 | 用 GitHub Actions 打出符合 Microsoft Store 要求的 Windows NSIS 安装包；Mac 上手动下载 Artifact 并提交 Partner Center |
| 非目标 | 自动上传商店、真 MSIX、代办 Partner Center 账号、商店自动更新、一期强制完成代码签名采购 |

---

## 1. Problem Statement

如何在仅有 Mac 开发环境的前提下，借助 GitHub Actions 产出可向 Microsoft Store 正式上架的 Windows 安装包，使「文书通」成为商店中的正版官方列表，同时不破坏现有直链 NSIS 分发链路？

背景约束：

- Tauri 2 **不原生支持** MSIX；官方推荐 Partner Center 创建 **EXE or MSI app**。
- 微软对新应用更推崇 MSIX，但对 Tauri + Python sidecar 工程，务实路径是先走 EXE/MSI 正式上架。
- 仓库已有 `.github/workflows/build-windows.yml` + `scripts/build-windows.ps1`（直链 NSIS）。

---

## 2. Decision

采用 **方案 1：商店专用 NSIS 工作流 + Mac 手动上架**。

1. **新建**独立 GitHub Actions 工作流（手动触发），产出商店向 `*-setup.exe`。
2. **新建** `tauri.microsoftstore.conf.json`，叠加商店要求（至少 `offlineInstaller`）。
3. **扩展** `build-windows.ps1`（开关默认关闭），避免影响直链构建。
4. **现有** `build-windows.yml` 行为保持不变。
5. Partner Center 注册、文案、HTTPS 托管、提交审核：人工 + 文档；CI 不自动上传。
6. Authenticode 签名：规格中列为**上架硬门槛**；实现可分步——先跑通未签名商店构建，再接证书 Secrets。

不采用真 MSIX（winapp/MakeAppx）作为一期目标。

---

## 3. Architecture

```
[workflow_dispatch]
        │
        ▼
 GitHub Actions (windows-latest)
   · 对齐现有 Windows 构建依赖（Python / Node / Rust / 缓存）
   · scripts/build-windows.ps1 -MicrosoftStore
   · 合并 tauri.microsoftstore.conf.json → NSIS
        │
        ▼
 Artifact: wenshutong-windows-msstore
   （文书通_*_x64-setup.exe，offline WebView2）
        │
        ▼
 开发者（Mac）
   · 下载 Artifact
   · 放到版本化、提交后不可变的 HTTPS URL
   · Partner Center：EXE/MSI 产品，静默参数 /S，提交认证
```

包内组件与现有标准底座一致：桌面壳、Runtime sidecar、预置轻量 Skill；不含写作 RAG 重依赖。

---

## 4. Components

### 4.1 工作流

| 项 | 约定 |
|---|---|
| 路径 | `.github/workflows/build-windows-msstore.yml` |
| 名称 | 建议：`Build Windows MS Store` |
| 触发 | 仅 `workflow_dispatch` |
| Runner | `windows-latest` |
| Artifact 名 | `wenshutong-windows-msstore` |
| 产物路径 | `apps/desktop/src-tauri/target/release/bundle/nsis/*-setup.exe` |

步骤结构对齐 `build-windows.yml`；构建步骤改为带 `-MicrosoftStore`（或等价参数）调用脚本。

### 4.2 Tauri 商店配置

路径：`apps/desktop/src-tauri/tauri.microsoftstore.conf.json`

至少包含：

- `bundle.windows.webviewInstallMode.type`: `offlineInstaller`
- `bundle.publisher`: 显式发布者名（**不得**与 `productName`「文书通」相同；实现时选定具体文案，例如组织/个人法律名）

默认 `tauri.conf.json` 保持直链策略（当前 `embedBootstrapper` + `targets: ["nsis"]`），不被商店配置永久覆盖。

### 4.3 构建脚本

扩展 `scripts/build-windows.ps1`：

- 新增开关：`-MicrosoftStore`（默认关闭）
- 开启时：`tauri build` / `tauri bundle` 合并 `--config` 指向 `tauri.microsoftstore.conf.json`
- 关闭时：行为与今日一致

### 4.4 上架文档

新增简短文档：`docs/APP store 相关/文书通-Microsoft-Store上架.md`，覆盖：

1. 注册 Partner Center 开发者账号  
2. 新建产品：**EXE or MSI app**，预留应用名  
3. 安装包要求摘要：离线安装器、静默 `/S`、PE 需可信根签名、HTTPS 版本化不可变 URL  
4. 如何从 Actions 下载 Artifact 并托管  
5. 签名为上架前必做（指向证书准备说明）

---

## 5. Signing strategy（分步）

| 阶段 | 内容 |
|------|------|
| 一期 CI | 可产出未签名商店配置安装包，验证配置与体积/路径 |
| 上架前 | 安装包及内含 PE 须用链式到 [Microsoft Trusted Root Program](https://learn.microsoft.com/en-us/security/trusted-root/participants-list) 的证书签名；自签名不可用 |
| 实现预留 | Actions Secrets + Tauri `signCommand` / Azure Trusted Signing（具体厂商在实现计划中选定，不绑定本期必须采购完成） |

EXE/MSI 商店路径下微软**不会**免费重签安装包（与 MSIX 不同）。

---

## 6. Partner Center 操作约定（人工）

- 产品类型：EXE or MSI app（非 MSIX 包提交）
- 静默安装参数：`/S`（NSIS，大写 S）
- 安装包 URL：HTTPS、按版本固定；提交后该 URL 上的二进制不得再被覆盖
- 更新：每次新版本提供新的版本化 URL，并新建/更新提交
- 隐私政策、截图、分级、认证说明：人工填写

---

## 7. Out of Scope

- `msstore` CLI / Partner Center API 自动上传与自动提交审核  
- 真 MSIX / Desktop Bridge 一期落地  
- 修改直链 NSIS 工作流行为或默认 WebView2 模式  
- 写作 RAG 选装打入底座  
- 商店内购 / 许可商务  
- Tauri updater 与商店更新模型的整合  

---

## 8. Risks

| 风险 | 缓解 |
|------|------|
| `offlineInstaller` 约 +127MB | 仅商店 Artifact 使用；直链包不变 |
| 无签名无法通过认证 | 文档标明硬门槛；CI 与签名分步 |
| 自托管 HTTPS 运维 | 文档推荐 GitHub Releases 版本资源 |
| 改脚本影响直链构建 | `-MicrosoftStore` 默认关；双 workflow |
| publisher 与产品名冲突 | 商店 conf 显式 `bundle.publisher` |
| 未来若改走 MSIX | 需新 Partner Center 产品类型；本规格不阻塞二期另开 |

---

## 9. Acceptance

- [ ] 手动运行商店工作流成功，上传 Artifact `wenshutong-windows-msstore`
- [ ] 产物为配置了 `offlineInstaller` 的 `文书通_*_x64-setup.exe`
- [ ] 现有 `Build Windows Installer` 工作流行为不变
- [ ] 上架说明文档已写入仓库，含 `/S`、HTTPS URL、签名门槛
- [ ] 默认 `tauri.conf.json` 未被破坏

---

## 10. References

- [Microsoft Store — Get started](https://learn.microsoft.com/en-us/windows/apps/publish/get-started)
- [Choose packaging model](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/choose-packaging-model)
- [MSI/EXE app package requirements](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msi/app-package-requirements)
- [Tauri — Microsoft Store](https://v2.tauri.app/distribute/microsoft-store/)
- 相关既有规格：`docs/superpowers/specs/2026-07-26-windows-nsis-installer-design.md`
