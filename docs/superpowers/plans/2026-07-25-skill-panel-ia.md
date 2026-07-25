# 文书通 · 技能面板 IA 重组 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 右侧技能栏仅纯展示已启用技能；底栏「技能管理」打开独立界面，承载总览、开/关、导入校验、卸载与刷新。

**Architecture:** 将现有 `SkillPanel.tsx` 拆为展示壳 + `SkillManager` 模态。Handlers（inspect/install/enable/uninstall/refresh）仍由 `App.tsx` 注入，不改 Runtime API。

**Tech Stack:** React · TypeScript · 现有 `SkillPanel.css` 扩展 · Vitest（可选纯函数测）

**Spec:** `docs/superpowers/specs/2026-07-25-skill-panel-ia-design.md`（已批准）

## Global Constraints

- 右栏：**无**开关、**无**卸载、**无**刷新；只渲染 `enabled === true`。
- 底栏主按钮文案：**技能管理**（不再用「导入技能」作主按钮）。
- 开/关/导入/卸载/刷新：**仅**在技能管理内。
- 导入预览与卸载确认：作为管理界面子对话框，复用现有校验逻辑。
- 预置标注：若无 Runtime `source` 字段，首版用已知 bundled id 集合（如 `government-document-format`、`multidoc-digest`、`skill-builder`）显示「预置」角标；不做禁止卸载。
- 品牌：文书通。英文 conventional commits。

---

## File Structure

```
apps/desktop/src/components/
  SkillPanel.tsx           # 右栏展示 + 打开管理
  SkillPanel.css           # 展示 + 管理样式
  SkillManager.tsx         # NEW — 管理模态（列表/导入/确认）
  SkillManager.css         # NEW 或并入 SkillPanel.css
apps/desktop/src/lib/
  skillUtils.ts            # NEW — isBundledSkillId、filterEnabledSkills（可测）
  skillUtils.test.ts       # NEW
  guide.ts                 # 空态文案（若有）
App.tsx                    # 接线不变或微调 props
```

---

### Task 1: 纯函数 — 启用过滤与预置 id

**Files:**
- Create: `apps/desktop/src/lib/skillUtils.ts`
- Create: `apps/desktop/src/lib/skillUtils.test.ts`

**Interfaces:**
```ts
export const BUNDLED_SKILL_IDS: ReadonlySet<string>;
export function isBundledSkillId(id: string): boolean;
export function filterEnabledSkills<T extends { enabled: boolean }>(skills: T[]): T[];
```

- [ ] **Step 1:** Vitest：enabled 过滤；bundled id 识别。
- [ ] **Step 2:** 实现最小函数；`npm test` 通过。
- [ ] **Step 3:** Commit `feat: add skill list helpers for enabled filter`

---

### Task 2: SkillManager — 管理模态（总览 / 开关 / 卸载 / 导入）

**Files:**
- Create: `apps/desktop/src/components/SkillManager.tsx`
- Modify: `SkillPanel.css` 或 NEW `SkillManager.css`（复用现有 preview/uninstall 样式类名可减少漂移）

**Props（建议）：**
```ts
interface SkillManagerProps {
  open: boolean;
  skills: SkillMeta[];
  onClose: () => void;
  onToggle: (id: string, enabled: boolean) => void;
  onInspect: (path: string) => Promise<SkillInspectResult>;
  onConfirmInstall: (path: string, enabled: boolean) => Promise<void>;
  onUninstall: (id: string) => Promise<void>;
  onRefresh: () => void;
}
```

**行为:**
- `open===false` 时不渲染或 `return null`。
- 列表展示**全部** skills；分组「已启用」「已停用」（规格推荐 A）。
- 每行：名称、短简介、版本（若有）、增强角标、预置角标（`isBundledSkillId`）、开关、卸载按钮。
- 导入：迁移现 `SkillPanel` 的 pick 菜单 + preview 校验 + 仅安装 / 安装并启用。
- 卸载确认对话框（现有文案可微调，预置多一句说明）。
- 顶栏或底栏：刷新、关闭；Esc / 遮罩关闭调用 `onClose`。
- 浏览器模式：无 Tauri 时隐藏文件夹/zip 选择（与现逻辑一致），开关/卸载仍可用。

- [ ] **Step 1–3:** 从 `SkillPanel.tsx` 迁出管理相关 state/JSX，拼成 SkillManager；`npm run build`。
- [ ] **Step 4:** Commit `feat: add SkillManager modal for install and lifecycle`

---

### Task 3: SkillPanel — 右栏纯展示 + 入口

**Files:**
- Modify: `apps/desktop/src/components/SkillPanel.tsx`
- Modify: `SkillPanel.css`
- Modify: `apps/desktop/src/lib/guide.ts`（空态文案，若适用）
- Modify: `App.tsx`（若 props 收敛）

**行为:**
- `const enabled = filterEnabledSkills(skills)` 渲染列表。
- 每项：标题 + heavy 角标；`title={description}` 可选；**无** switch、**无**卸载、**无**顶栏刷新。
- 空态：说明 + 按钮打开管理。
- 底栏：「技能管理」→ `setManagerOpen(true)`。
- 内嵌 `<SkillManager open={...} ... />`。
- 去掉右栏内原导入/卸载/开关 UI。

- [ ] **Step 1–2:** 改面板；目测结构符合规格 §4.1。
- [ ] **Step 3:** `npm test` + `npm run build`。
- [ ] **Step 4:** Commit `feat: show only enabled skills in side panel`

---

### Task 4: 回归与规格勾选

- [ ] `npm test` + `npm run build`
- [ ] 手工核对验收：右栏无开关/卸载；管理内可开/关/导入/卸；关后右栏消失
- [ ] 规格审批表已标明已批准；计划 Task 勾选完成
- [ ] Commit `docs: note skill panel IA implementation complete`（若仅改计划/规格一小段）或与 Task 3 合并若无文档增量

---

## Self-Review

| 规格项 | Task |
|--------|------|
| 右栏仅启用 + 纯展示 | 3 |
| 技能管理总览/开关/导入/卸载/刷新 | 2 |
| 空态 CTA | 3 |
| 预置角标（无 API） | 1–2 |
| Runtime 不改 | — |

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-07-25-skill-panel-ia.md`.
