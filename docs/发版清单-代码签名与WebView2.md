# 发版清单：代码签名与 WebView2

本清单对应安全审计 M-01 与 M-03。本地部署的 WebView2 固定版已改为 `151.0.4129.107`。安装包签名接到了 Windows 构建脚本，真正签上还要发版机提供能签 EXE 的证书。

## M-01 代码签名

审计对象是内网 NSIS 包 `文书通_本地部署_*-setup.exe`，不是商店 MSIX。

能用于这个安装包的证书，必须同时满足：

- 证书链到 Microsoft Trusted Root Program
- 可以用 `signtool` 对 PE 签名

这与商店 EXE/MSI 上架使用的付费 Authenticode 证书是同一类。微软不会为 EXE 免费重签。Partner Center 的 MSIX 开发证书、`store-devcert.pfx`，以及商店上架后的微软重签，只覆盖 `.msix`，不能签本次被审计的 NSIS 安装包。

GitHub Actions 的 Windows 安装包工作流从仓库 secret 取证书。把能签 EXE 的 PFX 做成一行 base64 后写入 secret，密码单独一个 secret：

```bash
base64 -i /path/to/codesign.pfx | tr -d '\n' | gh secret set WENSHUTONG_SIGN_PFX_B64
gh secret set WENSHUTONG_SIGN_PASSWORD
```

工作流在 `windows-latest` 上把证书写到临时目录，设置 `WENSHUTONG_SIGN_PFX` 和 `WENSHUTONG_SIGN_PASSWORD`，再调用 `scripts/build-windows.ps1`。`signtool` 在打包前签主程序和运行时，安装包生成后再签 `setup.exe`，时间戳服务器为 `http://timestamp.digicert.com`。secret 缺失时工作流直接失败，不会发布未签名安装包。本机打包时如果没设置这两个环境变量，脚本仍会跳过签名。

发版时对下列文件签名并加时间戳：

- `文书通_本地部署_*-setup.exe`
- `desktop.exe`
- `office-agent-runtime.exe`
- `uninstall.exe`

第三方 `.pyd` 与 `.dll` 优先保留上游已有签名。随包附一份 SHA256 清单，便于核对未被上游签名的文件。

## M-03 WebView2 固定版

本地部署继续使用固定版 WebView2。内网环境不能依赖常青版的系统更新。

本地部署钉死的版本已改为 `151.0.4129.107`（见 `apps/desktop/src-tauri/tauri.localdeploy.conf.json`）。它高于审计报告所称的 Chromium 149 修复线（CVE-2026-11306）。打包时由 `scripts/fetch-webview2-fixed.ps1` 从 NuGet 包 `WebView2.Runtime.X64` 拉取。漏洞披露后的窗口：确认受影响后，提高该版本号并重新打包。不要只改配置里的版本号而不重新下载二进制。再分发声明写在 `scripts/generate_notice.sh` 生成的 NOTICE 中。
