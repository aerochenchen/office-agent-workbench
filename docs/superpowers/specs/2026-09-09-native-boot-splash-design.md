# 文书通 · Windows 原生启动闪屏（方案 E：预渲染帧）

| 项 | 内容 |
|---|---|
| 状态 | 已实施（方案 E） |
| 日期 | 2026-09-09 |
| 范围 | Win10/Win11 安装包冷启动：WebView2 首帧前用**非 WebView**原生窗给出品牌反馈 |
| 非范围 | 假百分比进度、常驻 Runtime、macOS/Linux 原生闪屏（WKWebView/WebKit 通常够快） |

## 问题

主窗立刻可见时，WebView2 冷启动前只有纸感底色，用户会以为卡死。HTML 启动页要等 WebView 就绪才能画，盖不住前 ~10s。GDI `AngleArc` 会画出中心辐条且无抗锯齿，观感粗糙。

## 方案

1. Windows：`native_splash` 在独立 UI 线程创建 Win32 窗；内容为 **12 帧预渲染画面**（纸感底 `#f3f4f1`、Logo、品牌「文书通」、固定句「正在启动本地运行组件…」、浅灰底环 + 青色短弧，无辐条）。定时 `BitBlt` 切帧。
2. 资源：预览用 `frame_00.png` …；运行时嵌入 `frame_00.bgra` …（`u32le` 宽高 + top-down BGRA）。用 `scripts/gen-native-splash-frames.py` 按 Option E HTML 比例从 `apps/desktop/public/logo-mark.png` 重生成（透明 Logo、无白底方块）。
3. 主窗 `visible: false`；`PageLoadEvent::Finished` 时 `show` 主窗并 `dismiss` 原生闪屏。
4. 20s 兜底强制 `show`，避免永久隐身。
5. HTML `#boot-splash` 仍盖住「等 `/health`」阶段。

## 验收

- 双击后约立刻见到原生闪屏：有 Logo、文案、平滑短弧转圈（非空白主窗、无辐条）。
- WebView 就绪后切入主窗；启动页/主界面排版正常。
- 关应用不残留闪屏线程窗。
