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
