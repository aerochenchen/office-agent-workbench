# 文书通 Microsoft Store · MSIX 上架设计规格

| 项 | 内容 |
|---|---|
| 状态 | 已确认；实现计划见 `docs/superpowers/plans/2026-08-06-msix-store-listing.md` |
| 日期 | 2026-08-06 |
| 范围 | 新建 Partner Center **MSIX** 产品，用 CI 产出**商店身份对齐**的可提交包，手工完成首提认证并上架 |
| 非目标 | EXE/MSI 买证上架、msstore CLI 自动上传、付费/IAP、英文列表精修、用 MSIX 替换 NSIS 直链、关闭旧 EXE 草稿 |

相关：

- Spike（已完成构建能力）：`docs/superpowers/specs/2026-08-05-msix-spike-design.md`
- 旧 EXE 路径（并行搁置）：`docs/APP store 相关/文书通-Microsoft-Store上架.md`
- 操作短文（实现计划阶段补写）：建议 `docs/APP store 相关/文书通-MSIX-Store上架.md`

---

## 1. Problem Statement

如何在**不采购 Authenticode 证书**的前提下，把已验证可跑的 Windows MSIX（含 PDF 等核心能力）正式提交 Microsoft Store，完成首发上架？

背景约束：

- 真 MSIX 可由商店**免费重签**；EXE/MSI 路径需发布者自备 Trusted Root 证书，本期不采用。
- MSIX spike 已能在 GHA 打出可旁加载包；核心路径（启动、对话、工作区、技能、PDF）已在 Windows 上验证。
- Spike 清单身份（`ChenZai.Wenshutong` / `CN=ChenZai Wenshutong Spike`）**不能**直接提交；必须与 Partner Center Package identity 一致。
- 不带直角引号的名称 `文书通` 不可用；可用预留名为 **`「文书通」`**（含 U+300C / U+300D）。
- 开发以 Mac 为主；构建用 GHA；Partner Center 提交可在浏览器完成；验收与截图需 Windows。

---

## 2. Decision

采用 **方案 A：手工首提 + CI 产出商店提交用 MSIX**。

1. Partner Center **新建** MSIX（或 PWA）产品，预留名 **`「文书通」`**；与旧 EXE/MSI 草稿分离，不向 EXE 产品上传 MSIX。
2. 从 Product identity 抄下商店分配的 `Name` / `Publisher` / `Publisher display name`，注入商店构建清单。
3. 扩展现有 MSIX 构建（或新增 `Build Windows MSIX Store`），产出 Artifact 供浏览器上传。
4. **提交包不依赖个人开发证书对齐 Publisher**；商店认证通过后重签。旁加载自测可继续用 spike/devcert 路径，与商店包分开。
5. 定价：**免费**。市场：尽量全球可见。列表语言一期仅**简体中文**。
6. 支持联系邮箱：**`wenshutong@163.com`**。隐私政策：`https://aerochenchen.github.io/wenshutong-privacy/`。
7. 首提通过后再考虑 CI 自动上传（另开规格）；本期不做。

不采用：一上来全自动 msstore 上传；不回头主推 EXE+买证。

---

## 3. Architecture

```
Partner Center
  · New MSIX product, reserve 「文书通」
  · Copy Package identity (Name / Publisher / …)
        │
        ▼
 Repo + GitHub Actions
  · Inject Store identity into Package.appxmanifest (store variant)
  · Reuse spike payload layout (App\ + resources + Assets)
  · Keep MakeAppx sanitization (fixtures, [Content_Types] template, …)
  · Pack → Artifact wenshutong-windows-msix-store
        │
        ▼
 Windows（提交前）
  · Install store-identity build (sideload or equivalent test path)
  · Smoke: launch → chat → folder → skill → PDF
  · Capture Desktop screenshots
        │
        ▼
 Partner Center submission
  · Upload .msix
  · Properties / declarations / IARC / zh-CN listing
  · Notes for certification → Submit
        │
        ├── Pass → In the Store
        └── Fail → fix package/listing; retry (do not switch to EXE unless kill)
```

---

## 4. Components

### 4.1 Partner Center 产品

| 项 | 约定 |
|---|---|
| 产品类型 | MSIX or PWA app |
| 预留名 | `「文书通」`（含 U+300C / U+300D） |
| 定价 | 免费 |
| 市场 | 尽量勾选全球；接受非中文市场暂用中文列表 |
| 旧 EXE 草稿 | 搁置；不混用 |

创建后**必须**记录并用于构建：

- Package/Identity **Name**
- Package/Identity **Publisher**（`CN=…`，商店分配）
- **Publisher display name**

### 4.2 清单与构建

| 项 | 约定 |
|---|---|
| DisplayName / 磁贴 DisplayName | `「文书通」`（与预留名一致） |
| Version | 四段式，**第 4 段必须为 0**（例：`0.1.0.0`） |
| Executable | 保持 spike 布局：`App\Wenshutong.exe` |
| Capabilities | 至少 `runFullTrust`；不扩大无依据权限 |
| 身份注入 | 商店构建用 Partner Center 值覆盖 spike 身份。实现优先：`Package.store.appxmanifest`（或构建时替换）+ `workflow_dispatch` 输入/Secrets 填入 `Publisher` 等；提交包不得残留 spike 的 `CN=ChenZai Wenshutong Spike` |
| 签名 | 商店提交包：未签名或临时签均可，**不以**个人 Publisher 与商店身份对齐为成功条件；最终以商店重签为准 |
| MakeAppx 清理 | 保留 spike 已验证规则（非 ASCII fixtures、解包 docx 模板中的 `[Content_Types].xml` 等） |

CI：

- 触发：`workflow_dispatch`
- Artifact 名建议：`wenshutong-windows-msix-store`
- 与 `build-windows.yml` / `build-windows-msstore.yml`（EXE）行为互不影响

### 4.3 属性、声明与列表

| 项 | 值 |
|---|---|
| 类别 | Productivity |
| 隐私政策 URL | `https://aerochenchen.github.io/wenshutong-privacy/` |
| 支持邮箱 | `wenshutong@163.com` |
| 是否访问/收集/传输个人信息 | 是 |
| 生成式 AI | 是 |
| 驱动 / NT 服务 / 已通过辅助功能测试 / 笔墨 | 否 |
| 年龄分级 | IARC 问卷；按生产力工具 + 用户内容/联网如实填写 |
| 列表语言 | 简体中文 |
| 描述 | 由 Mac 商店文案改写为 Windows 纯文本；**描述正文不放 URL**（隐私/支持用专用字段） |
| 截图 | Desktop PNG，≥1366×768；至少 1 张，建议 ≥4（主界面、对话、结果、模型设置；勿含真实 Key） |

认证备注须说明：无登录；模型用户自配；访问用户 `api_base`；本地工作区读写；本机 sidecar/loopback；展示名含直角引号的原因；测试联系 `wenshutong@163.com`。

### 4.4 文档

实现阶段新增短操作文：`docs/APP store 相关/文书通-MSIX-Store上架.md`（建产品 → 抄身份 → 跑 Actions → 上传 → 填表 → 提交），并附可粘贴中文列表初稿与认证备注模板。

---

## 5. Acceptance Criteria（通过）

同时满足：

1. Partner Center 存在名为 `「文书通」` 的 **MSIX** 产品，且已用该产品 Package identity 打出提交包。
2. GHA 能稳定产出 Artifact `wenshutong-windows-msix-store`（或规格实现计划中确定的等价名）。
3. 提交前 Windows smoke：启动 → 配置模型对话 → 打开文件夹 → 至少一个技能 → PDF 抽取可用。
4. 提交认证并通过，产品状态达到 **In the Store**（或等价已发布）。
5. 商店页可安装；安装后上述 smoke 仍成立。
6. 现有 NSIS / EXE 商店工作流无行为回归。

---

## 6. Kill / 回退

出现任一条，**暂停 MSIX 上架冲刺**并书面记录：

1. 认证连续失败且根因是架构级（打包身份下 sidecar/工作区无法在合理改动内修复）。
2. 预留名 `「文书通」` 在认证/策略层被判定不可用，又无可用替代名可在短周期内预留。
3. 预估「仅为上架」的改动面明显超出清单/CI/文案范围，需大规模重做运行时沙盒。

默认回退：继续 GitHub/直链 NSIS 分发；若仍要商店且 MSIX 不可行，再评估 EXE + 付费代码签名（另开决策，不在本规格默认路径内）。

---

## 7. Out of Scope / Later

- `msstore` CLI / CI 自动上传与自动提交
- 付费、试用、IAP
- 英文或其他语言精修列表
- 用 MSIX 替换对内 NSIS 分发
- 删除或迁移旧 EXE Partner Center 草稿
- Azure Trusted Signing（非商店旁路分发场景）

---

## 8. Risks

| 风险 | 缓解 |
|---|---|
| 商店身份与清单不一致导致拒包 | 构建日志打印 Identity；上传前人工核对 Partner Center |
| 自签包 Publisher 与商店不符 | 提交包不以个人 devcert 为准；按官方「商店重签」路径 |
| 展示名含 `「」` 引发元数据/认证疑问 | 认证备注说明；包内 DisplayName 与预留名一致 |
| 全球市场 + 仅中文列表转化差 | 一期接受；后续加英文列表 |
| fullTrust + 本机 HTTP sidecar 被认证追问 | Notes 写清；准备演示步骤与联系邮箱 |
| Version 第 4 段非 0 | CI/清单校验强制 `x.y.z.0` |

---

## 9. References

- [Microsoft Store code signing / MSIX re-sign FAQ](https://learn.microsoft.com/en-us/windows/apps/publish/faq/get-started-with-the-microsoft-store)
- [App package requirements (version 4th segment)](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/app-package-requirements)
- [Screenshots and images](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/screenshots-and-images)
- [Age ratings (IARC)](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/age-ratings)
- Spike：`docs/superpowers/specs/2026-08-05-msix-spike-design.md`、`docs/APP store 相关/文书通-MSIX-spike.md`
