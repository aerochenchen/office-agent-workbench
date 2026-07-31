# 对话优先入门与用词统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户打开文书通后以对话框为第一注意点（发送为唯一主题绿），可先聊天入门；对外只用「文件夹」；无 API Key 时固定文案引导去设置。

**Architecture:** 文案集中在 `guide.ts`。壳层先拦截「未配置 Key」并本地插入固定回复；已配置 Key 但未开文件夹时，Runtime 允许无 workspace 的 chat（入门 system prompt + 不传工具）。开文件夹后恢复现有沙箱办事路径。沙箱越界规则不放松。

**Tech Stack:** React · TypeScript · Vitest · FastAPI · pytest · 现有 SSE `/chat/stream`

**Spec:** `docs/superpowers/specs/2026-07-31-chat-first-onboarding-design.md`（已批准）

## Global Constraints

- 用户可见主词：**仅「文件夹」**；禁止对用户露出「工作区」「项目」「项目文件夹」。
- 代码标识符可继续用 `workspace`（变量名、API path、`trust_workspace` 枚举值不变）。
- **发送**为唯一主题绿 CTA；「打开文件夹」一律 `btn--ghost` / 次要。
- 未选文件夹：可对话；**禁止**读/写本地文件与依赖文件夹的工具（入门模式 `tools=None`）。
- 未选文件夹会话：`workspace_path=""`，不出现在按路径列出的会话列表；「新建对话」禁用。
- 品牌：文书通。Commit：英文 conventional commits。

---

## File Structure

```
apps/desktop/src/lib/
  guide.ts                 # 用户文案：提示、空态、无 Key 固定回复
  guide.test.ts            # NEW — 文案契约（禁止禁用词、固定回复必含字段）
  runtimeStatus.ts         # 不改语义（needs_config 已存在）
apps/desktop/src/components/
  ChatPanel.tsx            # 解锁发送、空态、占位符、附件禁用文案
  SessionList.tsx          # 「当前文件夹」、打开按钮非主绿、新建禁用
  SettingsModal.tsx        # 「信任此文件夹」
  WorkspaceTree.tsx        # 历史组件文案对齐（仍未挂载）
apps/desktop/src/App.tsx   # handleSend 无文件夹 / 无 Key；打开文件夹文案
runtime/src/office_agent/
  agent_loop.py            # 入门 system prompt；run_agent 支持无工具
  app.py                   # _prepare_chat 允许无 workspace
runtime/tests/
  test_app_api.py          # 无 workspace chat、无 key 仍 400
  test_agent_loop.py       # 若已有；否则在 test_app_api 覆盖
```

---

### Task 1: `guide.ts` 文案源与契约测试

**Files:**
- Modify: `apps/desktop/src/lib/guide.ts`
- Create: `apps/desktop/src/lib/guide.test.ts`

**Interfaces:**
```ts
export const GUIDE_HINTS: {
  noWorkspace: string;       // 侧栏空会话等次要说明，不再要求「先开才能聊」
  emptyChat: string;         // 对话空态轻提示
  workspaceReady: string;
  noSessions: string;
  noSkills: string;
  noEnabledSkills: string;
  newSessionNeedsFolder: string; // 新建对话禁用 title
};

export const MODEL_SETUP_REPLY: string; // 无 Key / 模型未连通时插入的助手固定回复

export const FORBIDDEN_USER_TERMS: readonly string[]; // 测试用：["工作区","项目文件夹"]
```

- [ ] **Step 1: 写失败测试**

```ts
import { describe, expect, it } from "vitest";
import {
  FORBIDDEN_USER_TERMS,
  GUIDE_HINTS,
  GUIDE_PILLARS,
  MODEL_SETUP_REPLY,
} from "./guide";

function collectUserCopy(): string[] {
  return [
    ...GUIDE_PILLARS.flatMap((p) => [p.title, p.summary, p.body]),
    ...Object.values(GUIDE_HINTS),
    MODEL_SETUP_REPLY,
  ];
}

describe("guide copy", () => {
  it("does not expose forbidden terms to users", () => {
    const blob = collectUserCopy().join("\n");
    for (const term of FORBIDDEN_USER_TERMS) {
      expect(blob, `found forbidden term: ${term}`).not.toContain(term);
    }
  });

  it("MODEL_SETUP_REPLY guides user to settings and API key", () => {
    expect(MODEL_SETUP_REPLY).toMatch(/设置/);
    expect(MODEL_SETUP_REPLY).toMatch(/API|密钥|Key/i);
    expect(MODEL_SETUP_REPLY).toMatch(/模型/);
  });

  it("emptyChat invites chatting first", () => {
    expect(GUIDE_HINTS.emptyChat.length).toBeGreaterThan(8);
    expect(GUIDE_HINTS.emptyChat).toMatch(/问|聊|试/);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/desktop && npm test -- src/lib/guide.test.ts`
Expected: FAIL（缺 `MODEL_SETUP_REPLY` / `emptyChat` / 仍含「工作区」等）

- [ ] **Step 3: 更新 `guide.ts`**

要点（完整写入文件，勿留旧混用词）：

```ts
export const FORBIDDEN_USER_TERMS = ["工作区", "项目文件夹"] as const;

export const GUIDE_PILLARS = [
  {
    id: "local",
    title: "本地可控",
    summary: "材料在文件夹里办，用什么模型自己定。",
    body:
      "选定文件夹后，材料在本机该文件夹内读取与生成，不越界到文件夹外。大模型接口由你在设置中自行配置（地址、密钥、模型名），不绑定某一家公网云服务。",
  },
  // light / method / skills：检查 body，去掉「工作区」字样，改为「文件夹」
] as const;

export const GUIDE_HINTS = {
  noWorkspace: "打开文件夹后，对话与成果会保存在本地；办事时文书通只在该文件夹内读写。",
  emptyChat: "先随便问一句，我再告诉你文书通能帮你做什么。",
  workspaceReady: "描述要办的事即可；对话与成果会留在本地文件夹内。",
  noSessions: "暂无对话。点击上方「新建对话」开始。",
  noSkills: "可导入本地技能包增强能力；安装与运行均在本机。",
  noEnabledSkills: "暂无启用中的技能；可在技能管理中启用或导入。",
  newSessionNeedsFolder: "打开文件夹后可新建并保存对话",
} as const;

export const MODEL_SETUP_REPLY =
  "要开始对话，需要先连上大模型。请打开右上角「设置」，填写 API 地址、API Key（密钥）和模型名。" +
  "材料仍在你的本机；配置的是你自己的接口。配好后，直接在下方再发一句即可。";
```

`GUIDE_PILLARS` 可仍导出供设置「使用说明」；欢迎空态不再渲染四柱卡片（见 Task 3）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd apps/desktop && npm test -- src/lib/guide.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/lib/guide.ts apps/desktop/src/lib/guide.test.ts
git commit -m "feat: unify guide copy around 文件夹 and model setup reply"
```

---

### Task 2: 壳层用词与文件夹按钮降权

**Files:**
- Modify: `apps/desktop/src/components/SessionList.tsx`
- Modify: `apps/desktop/src/components/SettingsModal.tsx`
- Modify: `apps/desktop/src/components/WorkspaceTree.tsx`
- Modify: `apps/desktop/src/App.tsx`（仅错误文案：「打开文件夹失败」）

**Interfaces:** 无新 API；用户可见字符串替换。

- [ ] **Step 1: `SessionList.tsx`**

- 标签：`项目文件夹` → `当前文件夹`
- 打开按钮：始终 `btn btn--full btn--ghost`（去掉「未打开时 btn--primary」）
- `title` / 禁用新建：`请先打开工作区` → 使用 `GUIDE_HINTS.newSessionNeedsFolder`；未开文件夹时「新建对话」`disabled`
- placeholder：`或粘贴工作区绝对路径` → `或粘贴文件夹绝对路径`
- 空列表：保留 `GUIDE_HINTS.noWorkspace` / `noSessions`（Task 1 已改口径）

- [ ] **Step 2: `SettingsModal.tsx`**

```ts
{ value: "trust_workspace", label: "信任此文件夹", hint: "本会话内自动允许写入与跑脚本" },
```

枚举值 `trust_workspace` **不要改**。

- [ ] **Step 3: `WorkspaceTree.tsx` + `App.tsx` 错误串**

- 标题 `工作区` → `文件夹`
- 空态 / 脚注中的「工作区」→「文件夹」
- `App.tsx`: `"打开工作区失败"` → `"打开文件夹失败"`

- [ ] **Step 4: 静态检查**

Run: `rg '工作区|项目文件夹' apps/desktop/src --glob '*.tsx' --glob '*.ts'`
Expected: 无用户文案命中（允许注释/变量名 `workspacePath`；`trust_workspace` 枚举值可保留）。若 `ChatPanel` 仍有旧文案，留到 Task 3 一并改。

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/components/SessionList.tsx \
  apps/desktop/src/components/SettingsModal.tsx \
  apps/desktop/src/components/WorkspaceTree.tsx \
  apps/desktop/src/App.tsx
git commit -m "fix: replace workspace jargon with 文件夹 in shell chrome"
```

---

### Task 3: `ChatPanel` 对话优先 UI

**Files:**
- Modify: `apps/desktop/src/components/ChatPanel.tsx`
- Modify: `apps/desktop/src/components/ChatPanel.css`（若欢迎区样式需收束）

**Interfaces:**
```ts
// props 保持；行为变更：
// disabled = sending || !runtimeReady   // 不再依赖 workspaceOpen
// 发送按钮：runtimeReady && !sending → btn--primary，否则 btn--ghost
```

- [ ] **Step 1: 解锁发送与主绿**

将：

```ts
const disabled = !workspaceOpen || sending || !runtimeReady;
```

改为：

```ts
const disabled = sending || !runtimeReady;
```

发送按钮：

```tsx
className={`btn${runtimeReady && !sending ? " btn--primary" : " btn--ghost"}`}
disabled={disabled}
```

附件按钮：未 `workspaceOpen` 时保持 disabled；title/aria 用「请先打开文件夹」「添加文件夹内文件」等（禁止「工作区」）。

- [ ] **Step 2: 空态**

- `messages.length === 0 && !workspaceOpen`：品牌块 + `GUIDE_HINTS.emptyChat`；**删除**「打开文件夹」主按钮与四柱 `GUIDE_PILLARS` 列表（四柱仅留设置说明）。
- `messages.length === 0 && workspaceOpen`：品牌块 + `GUIDE_HINTS.workspaceReady`。
- 可移除对 `onOpenWorkspace` 的空态依赖（prop 若无其他用途可从 props 删除，并改 `App.tsx`）。

- [ ] **Step 3: 占位符与阶段提示**

```ts
const PHASE_HINTS = ["理解指令…", "查看文件夹…", "读写或运行脚本…", "整理结果…"] as const;
// placeholder:
workspaceOpen ? "描述要办的事…" : "试着问：文书通能帮我做什么？"
```

附件相关用户串全部「文件夹」化（含浏览器粘贴提示）。

- [ ] **Step 4: 桌面类型检查**

Run: `cd apps/desktop && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/components/ChatPanel.tsx apps/desktop/src/components/ChatPanel.css apps/desktop/src/App.tsx
git commit -m "feat: make chat composer usable before opening a folder"
```

---

### Task 4: Runtime — 无文件夹入门对话

**Files:**
- Modify: `runtime/src/office_agent/agent_loop.py`
- Modify: `runtime/src/office_agent/app.py`
- Modify: `runtime/tests/test_app_api.py`

**Interfaces:**
```python
# agent_loop.py
def _build_onboarding_system_prompt() -> str: ...

def run_agent(
    ...,
    *,
    onboarding: bool = False,  # True → 入门 prompt，且 gateway.chat(..., tools=None)
) -> AgentResult: ...

# app._prepare_chat
# 当 office.workspace is None：
#   - 不 require_workspace
#   - session: create_session("") 或沿用 session_id（须 workspace_path 为空或不存在路径）
#   - tools: 仍构造 ToolExecutor 需 Workspace → 改为 onboarding 时 tools 传占位；
#     推荐：onboarding 分支不创建 ToolExecutor，run_agent(onboarding=True) 内不调用 tools
#   - attached_paths 非空 → 400「请先打开文件夹后再附加文件」
```

- [ ] **Step 1: 失败测试 — 无 workspace 可 chat**

在 `test_app_api.py`（沿用现有 mock gateway fixture）追加：

```python
def test_chat_without_workspace_onboarding(client: TestClient, app_state: ProcessState):
    assert app_state.workspace is None
    r = client.post("/chat", json={"message": "你好，你能做什么？"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]
    assert body["session_id"]
    meta = app_state.sessions.get_session(body["session_id"])
    assert meta["workspace_path"] in ("", None) or meta["workspace_path"] == ""


def test_chat_without_workspace_rejects_attachments(client: TestClient, tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    r = client.post(
        "/chat",
        json={"message": "看这个", "attached_paths": [str(f)]},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd runtime && .venv/bin/pytest tests/test_app_api.py::test_chat_without_workspace_onboarding tests/test_app_api.py::test_chat_without_workspace_rejects_attachments -v`
Expected: FAIL（`workspace not open`）

- [ ] **Step 3: 实现入门 prompt 与 `run_agent(onboarding=...)`**

```python
def _build_onboarding_system_prompt() -> str:
    return (
        "你是「文书通」助手，用户是机关办公人员，可能刚打开软件。"
        "当前用户还没有选择本机文件夹，你不能读写任何本地文件，也不要假装已经处理了文件。"
        "目标：用自然口语接住用户这句话，并在大约 3～5 轮对话内让用户明白："
        "（1）文书通能帮他做什么（本地材料、对话办事、可安装技能等）；"
        "（2）大概怎么用（先说清任务；要处理本机材料时再让他「打开文件夹」，你只在该文件夹内读写）；"
        "（3）还有设置、技能等可探索，点到为止。"
        "先回应用户原话，再带出能力，不要像强制教程。"
        "若用户明确要处理本地文件/Word/材料，立刻请他使用界面「打开文件夹」，不要硬凑满 5 轮。"
        "不要使用或提及「工作区」「项目文件夹」等词，统一说「文件夹」。"
        "不要让用户去终端执行命令。"
    )
```

在 `run_agent` 中：

```python
system = _build_onboarding_system_prompt() if onboarding else _build_system_prompt(catalog)
# ...
tool_arg = None if onboarding else TOOL_SCHEMAS
response = gateway.chat(messages, tools=tool_arg)
# onboarding 时若模型仍返回 tool_calls：忽略并 finish 为文本，或强制再请求无 tools；
# 最小实现：onboarding 且存在 tool_calls → 将 content 或固定句作为 final，不调用 tools.execute
```

- [ ] **Step 4: 改 `_prepare_chat` / `chat` / `chat_stream`**

```python
onboarding = office.workspace is None
if onboarding:
    if body.attached_paths:
        raise HTTPException(status_code=400, detail="请先打开文件夹后再附加文件")
    session_id = body.session_id or office.sessions.create_session("")
    if body.session_id and not office.sessions.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    gateway = office.gateway_factory(office.config)  # 无 key 仍 GatewayError → 400
    # tools=None 传给 run_agent；catalog=[] 
    return session_id, gateway, None, [], [], office.config.max_steps, history
else:
    # 现有逻辑
```

同步改 `run_agent` 类型：`tools: ToolExecutor | None`。`chat`/`chat_stream` 调用 `run_agent(..., onboarding=tools is None)`。

无 Key 时保持现有 `HTTP 400` + Gateway 文案（壳层 Task 5 会优先本地固定回复，不依赖此路径）。

- [ ] **Step 5: 跑测试通过**

Run: `cd runtime && .venv/bin/pytest tests/test_app_api.py::test_chat_without_workspace_onboarding tests/test_app_api.py::test_chat_without_workspace_rejects_attachments tests/test_app_api.py::test_chat_returns_reply_and_session -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add runtime/src/office_agent/agent_loop.py runtime/src/office_agent/app.py runtime/tests/test_app_api.py
git commit -m "feat: allow onboarding chat without an open workspace"
```

---

### Task 5: `App.tsx` 接线 — 无 Key 固定回复 + 无文件夹发送

**Files:**
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/components/ChatPanel.tsx`（若需 `onOpenSettings` 可选，第一期可不加链接按钮，文案已指向设置）

**Interfaces:**
```ts
// handleSend 伪代码
async (text, attachedPaths) => {
  if (!runtimeReady) return;
  // 展示 user + pending/assistant
  if (!config.api_key_set) {
    // 用 MODEL_SETUP_REPLY 作为 assistant 最终内容；不调用 chatStream
    return;
  }
  let activeId = sessionIdRef.current;
  if (!activeId) {
    const created = await runtimeClient.createSession(workspacePath ?? undefined);
    activeId = created.session.id;
    setSessionId(activeId);
  }
  // chatStream as today；onFinal 时仅当 workspacePath 存在才 refreshSessions(workspacePath)
}
```

- [ ] **Step 1: 改 `handleSend` 入口**

删除 `if (!workspacePath || !runtimeReady) return;` → `if (!runtimeReady) return;`

无 Key 分支（在插入 user 消息之后）：

```ts
if (!config.api_key_set) {
  setMessages((prev) => [
    ...prev.filter((m) => m.id !== assistantId),
    userMsg,
    { id: assistantId, role: "assistant", content: MODEL_SETUP_REPLY, phase: "done" },
  ]);
  setSending(false);
  return;
}
```

（实现时注意与现有 pending 消息插入顺序一致，避免闪烁。）

- [ ] **Step 2: 无文件夹时创建Session**

```ts
const created = await runtimeClient.createSession(workspacePath ?? undefined);
```

`onFinal` / 成功后：

```ts
if (workspacePath) void refreshSessions(workspacePath);
```

- [ ] **Step 3: 打开文件夹时的会话策略（第一期）**

在 `handleOpenPath` 成功后：

- 若此前 `sessionId` 对应无路径入门会话：保留**界面** `messages`（用户能接着看），但 `setSessionId` 为文件夹下新建/最近会话，使后续发送走沙箱模式。
- 最小实现：打开文件夹后 `setMessages([])` 并加载该文件夹会话（实现简单）。**推荐折中**：打开文件夹时若当前 messages 非空则保留展示，同时 `sessionId` 换到文件夹新会话（入门轮次不写入该会话历史）。在代码注释标明第一期取舍。

- [ ] **Step 4: 流式错误映射**

在 `onError` 中：若 `message` 匹配 `/API Key|未配置|api key|401|403|连接/i`，展示 `MODEL_SETUP_REPLY`（或前缀一句失败原因 + 固定引导），避免技术堆栈。

- [ ] **Step 5: `tsc` + 桌面单测**

Run: `cd apps/desktop && npx tsc --noEmit && npm test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/App.tsx
git commit -m "feat: chat-first send path with API key setup fallback"
```

---

### Task 6: 手工验收清单（实现者执行并勾选）

**Files:** 无代码；验证 Spec §7。

- [ ] **Step 1: 冷启动（未开文件夹、未配 Key）**

1. 打开应用，对话区空态无绿色「打开文件夹」；发送为绿色。
2. 输入「你好」发送 → 出现 `MODEL_SETUP_REPLY` 口径回复；未发起成功模型请求（网络面板无成功 chat，或 Runtime 未收到）。
3. 侧栏「打开文件夹」非主绿；「新建对话」禁用。

- [ ] **Step 2: 配好 Key，仍未开文件夹**

1. 设置中填写有效 Key。
2. 发送「你能做什么？」→ 模型自然回复，且不出现「工作区」用词。
3. 附件按钮不可用。

- [ ] **Step 3: 打开文件夹后**

1. 打开一文件夹 → 可附加文件、可新建对话、会话列表出现。
2. 发送读写类任务 → 行为与改前一致（沙箱内）。

- [ ] **Step 4: Commit 无代码则跳过；若验收改了文案则小补丁 commit**

---

## Spec coverage（自检）

| Spec 要求 | Task |
|-----------|------|
| 用词仅「文件夹」 | 1, 2, 3 |
| 发送唯一主题绿 | 3, 2 |
| 未开文件夹可输入发送 | 3, 5 |
| 无 Key 固定文案 | 1, 5 |
| 有 Key 入门 3～5 轮策略 | 4（system prompt） |
| 未开文件夹不读写 | 4（tools=None）+ 3（附件禁用） |
| 新建对话未开文件夹禁用 | 2 |
| 会话不进文件夹列表 | 4（`workspace_path=""`） |
| 打开文件夹后正常办事 | 4 else 分支 + 5 |
| 不做强制向导 | 全文未引入 |

## Placeholder scan

无 TBD；`run_agent` onboarding 下意外 `tool_calls` 的处理已写明最小策略。
