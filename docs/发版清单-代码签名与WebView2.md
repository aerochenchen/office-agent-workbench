# 发版清单：代码签名与 WebView2

本清单对应安全审计 M-01 与 M-03。当前整改不更换证书文件，也不替换已随包的 WebView2 固定版二进制。

## M-01 代码签名

审计对象是内网 NSIS 包 `文书通_本地部署_*-setup.exe`，不是商店 MSIX。

能用于这个安装包的证书，必须同时满足：

- 证书链到 Microsoft Trusted Root Program
- 可以用 `signtool` 对 PE 签名

这与商店 EXE/MSI 上架使用的付费 Authenticode 证书是同一类。微软不会为 EXE 免费重签。Partner Center 的 MSIX 开发证书、`store-devcert.pfx`，以及商店上架后的微软重签，只覆盖 `.msix`，不能签本次被审计的 NSIS 安装包。

发版时对下列文件签名并加时间戳：

- `文书通_本地部署_*-setup.exe`
- `desktop.exe`
- `office-agent-runtime.exe`
- `uninstall.exe`

第三方 `.pyd` 与 `.dll` 优先保留上游已有签名。随包附一份 SHA256 清单，便于核对未被上游签名的文件。

## M-03 WebView2 固定版

本地部署继续使用固定版 WebView2。内网环境不能依赖常青版的系统更新。

当前钉死的版本是 `133.0.3065.92`（见 `apps/desktop/src-tauri/tauri.localdeploy.conf.json`）。审计报告指出其 PDFium 需要 Chromium 149 及以上的修复（检索到的编号为 CVE-2026-11306，发版前用厂商公告复核）。

漏洞披露后的窗口：确认受影响后，在下一个本地部署包中更换 `webview2-runtime` 目录并重新打包。不要只改配置里的版本号而不替换二进制。再分发声明写在 `scripts/generate_notice.sh` 生成的 NOTICE 中。
