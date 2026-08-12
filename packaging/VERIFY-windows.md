# Windows 安装包验证清单

在干净 Windows 10+ 机器（或虚拟机）上，按下列步骤验收标准底座 `*-setup.exe`。

## 构建机

- [ ] 已安装 Python 3.11+、Node.js/npm、Rust MSVC toolchain
- [ ] 发版门禁：`bash scripts/check_licenses.sh` 通过（Python + npm，无 GPL/AGPL）
- [ ] 发版门禁：`bash scripts/generate_notice.sh` 已生成仓库根 `NOTICE`
- [ ] 仓库根目录执行：`.\scripts\build-windows.ps1`
- [ ] 产物存在：`apps\desktop\src-tauri\target\release\bundle\nsis\*-setup.exe`
- [ ] 安装包内含 `NOTICE`（或与仓库根生成物一致）

## 干净机安装

- [ ] 双击安装器完成安装（当前用户即可）
- [ ] 开始菜单 / 桌面出现「文书通」，快捷方式图标与 `apps/desktop/branding/app-icon.png` 一致
- [ ] 安装目录中的 `文书通.exe` 显示同一套图标
- [ ] 首次启动后 `http://127.0.0.1:8765/health` 返回 `{"ok":true}`（或 UI 显示 Runtime 在线）
- [ ] 能打开工作区、发送一条对话（需已配置内网模型网关）
- [ ] Skill 列表含 `government-document-format`、`meeting-followup`、`material-gap`、`sheet-to-brief`、`one-to-three`、`brief-deck`、`chart-generation`、`doc-proofread` 等预置技能（bundled seed）
- [ ] `%USERPROFILE%\.office-agent\` 已创建

## 卸载

- [ ] 「应用和功能」卸载后，主程序目录移除
- [ ] `%USERPROFILE%\.office-agent\` **仍在**（用户数据保留）

## 本环境说明

若构建机缺少 Python/Node/Rust，无法在本机完成端到端打包；代码与脚本已就绪，请在具备工具链的 Windows 构建机执行上述清单。
