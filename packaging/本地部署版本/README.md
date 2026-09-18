# 文书通 · 本地部署版本

面向**单位内网、断公网**环境的封装路径。与标准安装包共用同一套代码，启动时读取 `deployment-profile=local`，强制下列约束：

- 模型地址只能是本机、内网域名或任意 IP 字面量（拒绝 DeepSeek / OpenAI 等公网 API 域名）
- 未配置模型地址前不能对话；内网服务若不校验密钥，API Key 可留空
- 默认谨慎模式；工作区自定义脚本默认关闭，用户可在设置中手动开启（有风险提示）
- 脚本子进程在 Linux/macOS 上进入无网命名空间（`unshare --net` / `sandbox-exec`）；Windows 上截断输出、缩短超时，并用文件系统狱限制 `open()`

标准（可连公网模型）安装包仍然可用；本目录只用于打「本地部署」安装包。

## 构建

**Windows NSIS**

```powershell
.\scripts\build-windows.ps1 -LocalDeploy
```

产物与标准包相同路径（`apps/desktop/src-tauri/target/release/bundle/nsis/*-setup.exe`），但安装目录 `resources/deployment-profile` 内容为 `local`。桌面壳启动 sidecar 时会设置 `OFFICE_AGENT_DEPLOYMENT=local`。

本地部署包会合并 `tauri.localdeploy.conf.json`，将 WebView2 改为 **fixedRuntime**（把 Fixed Version 运行时打进安装目录，约再增大 ~180–250MB）。安装时**不会**调用系统 WebView2 / Edge Update 安装器，可避开内网常见的 `0xA043050D`（`-1606220531`）。标准包仍用 `embedBootstrapper`（体积小，但安装时需能访问微软 CDN）。构建前脚本 `scripts/fetch-webview2-fixed.ps1` 会自动下载并解压固定版本运行时。

**macOS DMG**

```bash
./scripts/build-macos.sh --local-deploy
```

建议安装包文件名自行加后缀，例如 `文书通_本地部署_1.6.0.dmg`，避免与标准包混淆。

## 安装后

1. 打开设置 → 模型，填写**内网或本机** OpenAI 兼容地址（如 `http://127.0.0.1:8000/v1` 或专网 IP）。服务不校验密钥时可留空 API Key。
2. 公网云厂商域名会被运行时拒绝，界面会提示「本地部署版本仅允许本机或内网模型地址」。IP 字面量（含非 RFC1918 专网号段）可以通过。
3. Windows 上如需进一步禁止脚本进程出站，以管理员运行 `apply-windows-firewall.ps1`（可选；主进程仍需能访问内网模型）。
4. 银河麒麟可用 `linux-unshare-wrapper.sh` 核验系统是否支持用户命名空间。

## 与标准包的差异（安全）

| 项 | 标准包 | 本地部署版本 |
|---|---|---|
| 默认模型 | DeepSeek 公网（须用户改） | 空，必须配内网/本机 |
| 公网模型 | 允许（用户配置） | 拒绝 |
| `/chat` 危险工具 | 拒绝（409） | 同左 |
| 未附加文件读取 | 需确认 | 同左 |
| 工作区自定义脚本 | 默认关，设置中可开 | 默认关，设置中可开（有确认提示） |
| 脚本 OS 网络隔离 | 尽力 | 要求（非 Windows） |
| WebView2 | 嵌入引导程序（安装时可能需联网） | Fixed Version 随包（不跑系统安装器） |
