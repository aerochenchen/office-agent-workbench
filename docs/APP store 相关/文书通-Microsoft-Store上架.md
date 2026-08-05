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
