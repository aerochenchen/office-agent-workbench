# AI Content Report (Store 11.16) Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** Add in-app “Report inappropriate AI content” via mailto so Store policy 11.16 passes.

**Architecture:** Pure `buildAiContentReportMailto` helper + small modal; wire into ChatPanel assistant bubbles and Settings about tab; open mailto via Tauri opener (with fallback).

**Tech Stack:** React 19, TypeScript, Vitest, Tauri 2 plugin-opener

## Global Constraints

- Report email: `wenshutongapp@163.com` (verbatim)
- Subject: `[文书通] 不当 AI 内容举报`
- No backend upload of report payloads
- Chinese UI copy only (existing app convention)

---

### Task 1: Mailto builder + tests

**Files:**
- Create: `apps/desktop/src/lib/aiContentReport.ts`
- Create: `apps/desktop/src/lib/aiContentReport.test.ts`
- Modify: `apps/desktop/src/lib/brand.ts` (SUPPORT_EMAIL constant)

- [ ] Write failing tests for subject, email, truncation, encodeURIComponent
- [ ] Implement builder + brand constant
- [ ] Tests pass

### Task 2: openMailto + capability

**Files:**
- Modify: `apps/desktop/src/lib/tauri.ts`
- Modify: `apps/desktop/src-tauri/capabilities/default.json`

- [ ] Add `openMailto` using opener `openUrl`, browser fallback `window.location.href`
- [ ] Allow `mailto:*` in opener permissions

### Task 3: Report modal + UI wiring

**Files:**
- Create: `apps/desktop/src/components/AiContentReportModal.tsx` (+ css if needed)
- Modify: `ChatPanel.tsx` / `.css`
- Modify: `SettingsModal.tsx`
- Modify: ops Notes in `docs/APP store 相关/文书通-MSIX-Store上架.md`

- [ ] Modal with optional note + confirm/cancel
- [ ] Bubble「举报」for done assistant messages
- [ ] About page entry
- [ ] Update certification notes with report path
