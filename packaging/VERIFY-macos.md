# macOS 内测 DMG 验证清单

> **内测用，不做 Apple 公证。** 本清单面向笔记本或另一台 Mac 上的手工验收，非正式分发流程。

在干净 macOS（或另一台测试机）上验收 `文书通` 内测盘镜像。

## 构建机

- [ ] macOS + Python 3.11+、Node.js/npm、Rust
- [ ] 仓库根目录执行：`./scripts/build-macos.sh`
- [ ] 产物存在：`apps/desktop/src-tauri/target/release/bundle/dmg/*.dmg`（或 `packaging/dist/mac/*.dmg`）

## 安装与启动

- [ ] 打开 `.dmg`，将「文书通.app」拖到「应用程序」
- [ ] 若 Gatekeeper 拦截：Finder 中右键 App →「打开」（内测未公证属预期）
- [ ] Dock / 应用程序图标与品牌图标一致
- [ ] 首次启动后 UI 显示 Runtime 就绪，或 `http://127.0.0.1:8765/health` 返回 `{"ok":true}`
- [ ] 能打开文件夹工作区并发送一条对话（需已配置内网模型网关）
- [ ] 技能列表含 `government-document-format`、`office-visual-design` 等预置技能（bundled seed）
- [ ] `~/.office-agent/` 已创建

## 说明

本清单仅覆盖**未公证内测包**。正式分发需 Developer ID 签名与 Apple 公证后再验收。
