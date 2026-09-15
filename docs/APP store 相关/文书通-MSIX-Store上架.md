# 文书通 · Microsoft Store（MSIX）上架

对应规格：`docs/superpowers/specs/2026-08-06-msix-store-listing-design.md`。  
**产品类型：MSIX。** 不要往旧 EXE/MSI 草稿上传本包。  
**当前目标版本：`1.6.0.0`**（与桌面 `APP_VERSION` / `tauri.conf.json` 对齐；第 4 段必须为 0）。

## 1. Partner Center：产品与身份（已建则跳过）

1. New product → **MSIX or PWA app**（更新提交：打开既有「文书通」MSIX 产品 → Create new submission）
2. 预留名：`「文书通」`
3. Package identity（已用于 1.5 提交，重建包时原样填入）：

| 项 | 值 |
|----|-----|
| Name | `Lirenda.130889291737B` |
| Publisher | `CN=A6EE867D-F6C9-459F-91F8-BF851B420BB6` |
| Publisher display name | `Lirenda` |

4. 定价：免费；市场尽量全球；列表语言先做简体中文

## 2. 打出商店包（1.6.0）

1. Actions → **Build Windows MSIX Store** → Run workflow  
2. 填入上表三项身份 + 版本 **`1.6.0.0`**  
3. 下载包（二选一）：
   - Actions → 该 run → Artifacts → `wenshutong-windows-msix-store`
   - 或 **Releases** → 标签 `msix-store-1.6.0.0`（Artifact 配额满时仍可从 Release 取 `Wenshutong_1.6.0.0_x64.msix` + `store-devcert.pfx`）

## 3. 提交前本机核对（Windows）

1. 以管理员身份启动 PowerShell 后，信任 `store-devcert.pfx`（若 Artifact 含证书）：`winapp cert install .\store-devcert.pfx`
2. `Add-AppxPackage .\Wenshutong_1.6.0.0_x64.msix`  
3. Smoke：启动 → 配模型对话 → 开文件夹 → 技能 → PDF / 扫描 PDF OCR → 设置→关于→举报  
4. 截图（Desktop PNG ≥1366×768，建议 ≥4 张；设置页勿含真实 Key）

## 4. Partner Center 填表（更新提交）

| 项 | 值 |
|----|-----|
| 隐私政策 | https://aerochenchen.github.io/wenshutong-privacy/ |
| 支持邮箱 | wenshutongapp@163.com |
| 网站（可选） | https://www.lirenda.cn |
| 类别 | Productivity（生产力） |
| 收集个人信息 | 是 |
| 生成式 AI | 是 |
| 驱动/NT/辅助功能/笔墨 | 否 |
| 年龄分级 | IARC 问卷（生产力 + 用户内容/联网如实填） |

Packages：上传 **`Wenshutong_1.6.0.0_x64.msix`**（替换旧 1.5 包）→ 更新 Store listing / What’s new → Notes for certification → Submit。

## 5. 简体中文列表

### 短描述（建议 ≤270 字）

```
会干活的助手，不是会说话的窗口。打开材料文件夹，用自然语言完成排版、汇总与写作；材料留在本机，模型由你配置。
```

### 完整描述（纯文本；勿再贴 URL）

```
文书通是装在本机的办公文书工作台：打开材料所在文件夹，用自然语言下任务，在受控范围内读写文件、调用技能，直接产出可交付的 Word、PDF 等结果。

会干活的助手，不是会说话的窗口。

【它和普通 AI 聊天有何不同】
• 主战场是本地文件夹，不是对话框附件
• 能力可安装、可扩展——薄底座 + 选装技能
• 模型接口由你配置（建议单位内网或本机模型）
• 结果常落成可打开、可流转、可复核的文档
• 操作可控：权限可确认、步骤看得见、调用可审计

【现在能做什么】
1. 公文排版 —— 按规范处理格式，输出新文件便于核对
2. 批量整理 —— 多文档汇总，报告带引用出处
3. 正式配色 —— 为汇报生成正式配色并可套用到幻灯片
4. PDF 文本抽取 —— 文本型与扫描印刷体 PDF 均可纳入办理材料
5. 图表生成 —— 从材料生成图表（预置技能）
6. 创建与沉淀技能 —— 把反复流程固化、导出、分享

【推荐使用路径】
安装 → 在设置中配置模型地址与密钥 → 先对话了解能力 → 打开材料文件夹办事 → 在技能管理中启用需要的能力。

【本地可控】
• 读写范围限制在你选定的文件夹内
• 高危操作可按权限模式要求人工确认
• 模型仅连接你配置并允许的地址
• 工具调用留在本机审计（敏感字段脱敏）
• 开发者不运营用于汇聚你公文内容的云端账号体系

出品：立人达创新工作室（www.lirenda.cn）

一句话：让大模型进入真实文书工作流——本地可控，轻量可跑，方法可沉淀，能力可插拔。
```

### 此版本的新增内容（1.6.0）

```
• 扫描类 PDF 印刷体页面支持 RapidOCR 识别，便于抽取正文
• 新增预置「图表生成」技能，方便从材料出图
• 启动体验优化：运行时就绪后再进入主界面，减少空白等待
• 主工作台界面细化；关于页展示出品方与版本
• 设置 → 关于 提供「举报不当 AI 内容」（符合商店生成式 AI 政策）
• 安全与稳定性加固
```

（隐私政策与支持联系请填 Partner Center 专用字段，不要写进描述正文。）

## 6. Notes for certification（英文模板，可直接粘贴）

把 `__CERT_TEST_API_KEY__` 换成你提供给审核员的临时 DeepSeek Key。

```
Date: 2026-09-15
Version: 1.6.0.0 (MSIX update from 1.5.0.0)

Product: 「文书通」 (Wenshutong) — local productivity agent for office documents on Windows (MSIX).
Publisher listing: Lirenda / 立人达创新工作室 (www.lirenda.cn)

Account / login:
- No user registration or in-app account.
- The user configures their own OpenAI-compatible model endpoint (api_base) and API key in Settings.

Network:
- Outbound HTTPS to the user-configured model endpoint only (plus normal OS/store update channels).
- Local loopback HTTP to a bundled sidecar runtime on 127.0.0.1 (office document tools).

Files:
- Reads/writes only within the folder the user explicitly opens as the workspace.
- Supports Office documents and PDF text extraction (including scanned print pages via RapidOCR).

Display name:
- Reserved Store name includes CJK corner quotes: 「文书通」 (U+300C / U+300D), because the unquoted name was unavailable.

Testing:
- No test account required (no sign-in).
- Contact: wenshutongapp@163.com
- Generative AI reporting (Store 11.16): Settings (设置) → 关于 → 「举报不当 AI 内容」. This opens the system mail client to wenshutongapp@163.com with a prefilled report (optional note + clipboard fallback).
- Model configuration for certification (Settings → 模型):
  - 选用模型 / Model: deepseek-v4-flash
  - API Base: https://api.deepseek.com
  - API Key: __CERT_TEST_API_KEY__
  - Save, then send one short chat (e.g. “你好”) to verify generative output, then open Settings → 关于 and test 「举报不当 AI 内容」.
- Suggested path: launch → set model as above → send one chat → Settings → 关于 → 「举报不当 AI 内容」 (cancel after mail opens) → open a folder → run one skill → open a PDF in workspace and extract/summarize.
```

## 7. 失败时

按规格 Kill / 回退：继续 NSIS 直链；勿默认改回买证 EXE，除非书面改决策。
