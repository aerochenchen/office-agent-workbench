# 文书通隐私政策（公开页）

单页文件：`index.html`  
对应正文草稿：`../文书通-隐私政策.md`

## 已发布公开 URL

- 仓库：https://github.com/aerochenchen/wenshutong-privacy  
- 隐私政策页：**https://aerochenchen.github.io/wenshutong-privacy/**  
- App Store Connect → App 信息 → 隐私政策 URL：填上述链接

处理者：Chenchen XU　·　邮箱：wenshutongapp@163.com

## 用 GitHub Pages 挂出公开 URL（已完成；备查）

### 方式一：本仓库 `/docs` 站点（若仓库已公开）

1. 将含 `docs/privacy/index.html` 的提交推到 GitHub 默认分支。
2. 仓库 **Settings → Pages**：
   - Source：Deploy from a branch
   - Branch：`main`（或你的默认分支）
   - Folder：**`/docs`**
3. 保存后等待 1–2 分钟。
4. 公开地址一般为：

   `https://<你的用户名>.github.io/<仓库名>/privacy/`

   或（用户/组织站点）：

   `https://<你的用户名>.github.io/privacy/`

5. 浏览器无痕窗口打开上述 URL，确认：
   - 无需登录即可查看
   - HTTPS 有效
   - 占位符已替换

6. 将该 URL 填入 App Store Connect → App 信息 → **隐私政策 URL**。

### 方式二：单独建一个极简公开仓库（更干净）

1. 新建公开仓库，例如 `wenshutong-privacy`。
2. 只放入本目录的 `index.html`（可改名为仓库根目录的 `index.html`）。
3. Settings → Pages → Branch：`main` / Folder：`/`（根目录）。
4. URL 形如：`https://<用户名>.github.io/wenshutong-privacy/`

### 方式三：先本地预览

```bash
open docs/privacy/index.html
```

本地 `file://` 仅供校对；**不能**用作 App Store 的隐私政策 URL（必须是公网 https）。

## 提交审核前自检

- [ ] 处理者名称与 Apple 开发者账号主体一致
- [ ] 公网 HTTPS 可打开、无需登录
- [ ] 内容与实际上线功能、模型部署策略一致
- [ ] ASC 中已粘贴该 URL
