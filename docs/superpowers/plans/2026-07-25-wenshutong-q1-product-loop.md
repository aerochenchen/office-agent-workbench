# 文书通 Q+1 · 产品闭环（A+B+D）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付附件进对话、Markdown/打开产物、导入 Skill 前结构校验，形成可感知的产品闭环；**不含**写作 RAG 验收与降级 Skill（C 明确不做）。

**Architecture:** 桌面壳用已有 dialog/opener 插件选文件并 `openPath`；`attached_paths` 经现有 chat API 传入 Runtime。Markdown 仅渲染助手气泡。Skill 安装路径在 `SkillRegistry.install_*` 前调用 Runtime 内 `skill_validate`（从 skill-builder 规则提炼的轻量版，不依赖该 Skill 已安装）。

**Tech Stack:** Tauri 2（dialog/opener）· React · TypeScript · `react-markdown` + `remark-gfm` · Python FastAPI · pytest

**Spec:** `docs/superpowers/specs/2026-07-25-wenshutong-audit-roadmap-design.md` §5.3（仅 A/B/D）

## Global Constraints

- 不做 C：写作 RAG 端到端、无向量降级写作 Skill。
- 不做完整脚本 jail / macOS 公证。
- `attached_paths` 必须落在当前工作区内（Runtime 已有或补校验）。
- Markdown 只渲染 assistant（及可选 tool 摘要），user/error 保持纯文本防 XSS 噪音。
- 打开文件：仅 Tauri `opener`；浏览器模式显示路径 +「复制路径」。
- Skill validate：**error 拒装**；warning 可装但 UI 展示。
- 品牌：文书通。英文 conventional commits；用户要求或执行本计划时再 commit。

---

## File Structure

```
runtime/src/office_agent/
  skill_validate.py      # NEW — 轻量结构校验（frontmatter/权限/路径）
  skills.py              # install_* 前 validate
  app.py                 # inspect/install 返回 validation；可选 chat 校验 attached_paths
  agent_loop.py          # 确保 attached_paths 注入 prompt（若尚未）
apps/desktop/src/
  components/ChatPanel.tsx / ChatPanel.css
  components/MarkdownMessage.tsx   # NEW
  lib/tauri.ts                     # pickWorkspaceFiles + openPath
  lib/runtimeClient.ts / types.ts
  App.tsx
  src-tauri/src/lib.rs             # 可选：多选文件 dialog（若 JS API 不够）
runtime/tests/
  test_skill_validate.py           # NEW
  test_skills.py / test_app_api.py / test_agent_loop.py
```

---

### Task 1: Runtime — attached_paths 边界 + prompt 注入确认

**Files:**
- Modify: `runtime/src/office_agent/app.py` 和/或 `agent_loop.py`
- Modify: `runtime/tests/test_agent_loop.py` / `test_app_api.py`

**Interfaces:**
- Chat 请求体已有 `attached_paths: list[str]`。
- Produces: 每个 path `Workspace.resolve`；越界 → 400 或工具前过滤并记 error。
- System/user 侧注入简短「用户附带文件」列表（相对工作区路径），供本轮使用。

- [ ] **Step 1:** 写测试：越界 path 被拒；合法 path 出现在发给模型的上下文/history 中。
- [ ] **Step 2–4:** TDD 实现。
- [ ] **Step 5:** Commit `feat: validate and inject attached_paths into chat context`

---

### Task 2: Desktop — 附件选择 UI 并发送

**Files:**
- Modify: `apps/desktop/src/lib/tauri.ts`、`ChatPanel.tsx`、`App.tsx`、`runtimeClient`（若类型需显式）
- Modify: `ChatPanel.css`

**行为:**
- 输入区旁「附件」按钮：Tauri 多选文件；**过滤/校验**所选路径在 `workspacePath` 下（用字符串前缀 + normalize；不在则提示）。
- 浏览器模式：可粘贴工作区内绝对路径（一行一个）或禁用多选并提示。
- Chip 展示已选文件，可移除；`onSend(text, attachedPaths)` → `chatStream({ message, attached_paths, session_id })`。
- 发送成功后清空附件列表（或保留——**选定：发送后清空**）。

- [ ] **Step 1–3:** 实现 + `npm run build`
- [ ] **Step 4:** Commit `feat: attach workspace files to chat turns`

---

### Task 3: Markdown 气泡

**Files:**
- Create: `apps/desktop/src/components/MarkdownMessage.tsx` (+ css module/section in ChatPanel.css)
- Modify: `ChatPanel.tsx`、`package.json`（加依赖）

**依赖:**
```bash
cd apps/desktop && npm install react-markdown remark-gfm
```

**行为:**
- `role === "assistant"` 且 `phase === "done"` 用 Markdown 渲染；pending/live 仍纯文本/步骤 UI。
- 允许：标题、列表、粗体、代码块、链接（`http(s)` 与相对看起来像路径的代码/`file` 样式）。
- 禁止：原始 HTML（react-markdown 默认不解析 raw HTML）。

- [ ] **Step 1–3:** 安装依赖、组件、接线、`npm run build`
- [ ] **Step 4:** Commit `feat: render assistant replies as Markdown`

---

### Task 4: 产物「用系统打开」

**Files:**
- Modify: `apps/desktop/src/lib/tauri.ts`（`openPath(path: string)` 封装 `@tauri-apps/plugin-opener`）
- Modify: `MarkdownMessage.tsx` / `ChatPanel.tsx`：识别消息中的工作区绝对路径或 `` `相对路径.ext` ``，渲染为可点击按钮/链接。
- 能力：`opener:default` 已在 capabilities——确认路径打开权限足够；若需 `opener:allow-open-path` 按 Tauri 2 文档补。

**启发式（够用即可）:**
- 匹配以工作区根开头的绝对路径；
- 或匹配 `` `output/...` `` / `` `.office-agent/...` `` 等相对片段 + 已知后缀（`.docx .xlsx .pdf .md .txt .json`）。
- 点击 → `openPath`；失败 toast/气泡错误。
- 浏览器：复制路径到剪贴板。

- [ ] **Step 1–3:** 实现 + build
- [ ] **Step 4:** Commit `feat: open deliverable paths with system default app`

---

### Task 5: Runtime skill_validate + 安装拒收

**Files:**
- Create: `runtime/src/office_agent/skill_validate.py`
- Modify: `runtime/src/office_agent/skills.py`（`install_dir` / `install_zip` / `install_md` 前校验）
- Modify: `runtime/src/office_agent/app.py`（`/skills/inspect` 与 install 错误体带 `errors`/`warnings`）
- Create: `runtime/tests/test_skill_validate.py`；扩展 `test_skills.py`

**校验范围（轻量，对标 skill-builder 核心 error，非全文复刻）:**
- 存在 `SKILL.md`；YAML frontmatter 可解析
- 必填：`name`, `description`, `version`, `tier`（`display_name` 缺省时 warning）
- `tier ∈ {light, heavy}`；`permissions ⊆` 白名单
- `name`/`id` 符合安全 id 规则（无 `..` / 路径分隔）
- description 长度 > 60 → **warning**（与 skill-builder 一致可 warning 不拒）
- 有 `scripts/*.py` 则语法 `ast.parse`；禁止明显外网 import（requests/httpx/socket）→ error

**不在本 Task：** 强制「何时/步数预算」章节（可 warning）；跑 smoke_pipeline。

- [ ] **Step 1:** 坏包 install 抛错；好包通过；inspect 返回 validation 字段
- [ ] **Step 2–4:** 实现
- [ ] **Step 5:** Commit `feat: validate skill packages before install`

---

### Task 6: Desktop — 安装预览展示校验结果

**Files:**
- Modify: `SkillPanel.tsx`、`runtimeClient.ts`、`types.ts`

**行为:**
- inspect/install 响应含 `validation: { ok, errors, warnings }`
- 预览弹层：error 红色列表且「确认安装」禁用；warning 黄色可装
- install API 若仍被调用且 error → 展示 Runtime 返回详情

- [ ] **Step 1–3:** 接线 + build
- [ ] **Step 4:** Commit `feat: show skill validation errors in install preview`

---

### Task 7: 回归与规格回写

- [x] Full `pytest` + `npm run build`
- [x] 更新审计规格 §5.3：标注 A/B/D 完成，**C 明确跳过**
- [x] Commit `docs: record Q+1 A/B/D completion`

---

## Self-Review

| 项 | Task |
|----|------|
| A 附件 | 1–2 |
| B Markdown | 3 |
| B 打开产物 | 4 |
| D 安装校验 | 5–6 |
| C 写作 RAG | **不做** |
| 回归 | 7 |

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-07-25-wenshutong-q1-product-loop.md`.
