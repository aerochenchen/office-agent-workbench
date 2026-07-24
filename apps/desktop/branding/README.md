# 品牌资源

产品名：**文书通**  
定位：**政务文书 · 智能通办**  
（代码常量见 `src/lib/brand.ts`）

## 正式应用图标（已锁定）

当前视觉效果已确认为正式版，用于：

- macOS Dock / 窗口图标（`icon.icns`）
- Windows `.exe` 图标（`icon.ico`）
- NSIS 安装器 / 卸载器图标
- 安装后开始菜单与桌面快捷方式（跟随 `icon.ico`）

| 文件 | 用途 |
|------|------|
| `app-icon.png` | **唯一源图**（1024²）：白底圆角板 + 主图约 70% 居中（约 15% 边距） |
| `app-icon-rounded-preview.png` | 与上相同的圆角预览 |
| `logo 白底版.png` / `logo 透明底版.png` | 用户提供的原图（勿直接当打包图标） |
| `../src/assets/logo-mark.png` 与 `../public/logo-mark.png` | 界面透明角标 |
| `../src-tauri/icons/*` | 由源图生成的打包产物（勿手改） |

打包配置见 `src-tauri/tauri.conf.json` 的 `bundle.icon` 与 `bundle.windows.nsis.installerIcon`。

## 重新生成（仅在改源图后）

```bash
cd apps/desktop
npx tauri icon ./branding/app-icon.png -o ./src-tauri/icons
```

或使用仓库脚本：

```bash
./scripts/generate-app-icons.sh
```

改完后需重新执行 `tauri build` / `scripts/build-windows.ps1`，安装包与桌面快捷方式才会带上新图标。
