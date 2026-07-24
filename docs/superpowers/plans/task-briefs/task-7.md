### Task 7: Tauri desktop workbench (M0 UI)

**UI Design Direction (审美约束 — 必须遵守):**

面向机关办公，气质应是「沉稳文书工作台」，不是消费级 AI 聊天玩具。

| 维度 | 要求 |
|---|---|
| 视觉方向 | 浅色为主（机关白天办公）；冷灰纸感背景 + 深墨字；点缀色用 muted 青绿或靛蓝（**禁止**紫粉渐变、霓虹 glow、大面积圆角胶囊） |
| 字体 | 中文用「思源黑体 / Noto Sans SC」或系统「PingFang SC / Microsoft YaHei」层级清晰；英文/代码用等宽；**禁止** Inter / Roboto 作为品牌感来源 |
| 布局 | 三栏工作台一体构图；左侧文件树、中间对话为视觉重心、右侧 Skill 次要；留白克制，信息密度中等 |
| 组件 | 默认少用「卡片叠卡片」；工具调用用细分割线/行内状态条，而非厚阴影卡片墙 |
| 动效 | 2–3 处即可：消息淡入、工具状态点、侧栏展开；禁止花哨 |
| 品牌 | 产品名在顶栏清晰可辨；不要用泛 AI 插画填空 |

实现时用 CSS 变量集中定义色板与字号；Task 7 验收含「不像通用 AI 模板页」。

**Files:**
- Create: `apps/desktop/**` (React-TS Tauri template)
- Create: `apps/desktop/src/lib/runtimeClient.ts`
- Create: `apps/desktop/src/components/WorkspaceTree.tsx`
- Create: `apps/desktop/src/components/ChatPanel.tsx`
- Create: `apps/desktop/src/components/SkillPanel.tsx`
- Create: `apps/desktop/src/components/SettingsModal.tsx`
- Modify: `apps/desktop/src-tauri` to spawn runtime on `127.0.0.1:8765`

**Interfaces:**
- `runtimeClient.health|openWorkspace|getTree|chat|listSkills|installSkill|setEnabled|saveConfig`
- Tauri `pick_folder(): Promise<string>`
- SkillPanel shows tier badge; heavy shows `min_ram_gb` confirm on install

- [ ] **Step 1: Scaffold**

```bash
mkdir -p apps && cd apps
npm create tauri-app@latest desktop -- --template react-ts
cd desktop && npm install
```

- [ ] **Step 2: Implement `runtimeClient.ts` against `http://127.0.0.1:8765`**

- [ ] **Step 3: Three-pane App** — 文件树 | 对话（含 tool_events 卡片）| Skill 列表

- [ ] **Step 4: Manual verify**

```bash
# A: runtime
cd runtime && source .venv/bin/activate
uvicorn office_agent.app:app --app-dir src --host 127.0.0.1 --port 8765

# B: UI
cd apps/desktop && npm run tauri dev
```

Expected: 选文件夹 → 树刷新；发消息（无有效 API 时可看到明确错误，不崩溃）。

- [ ] **Step 5: Commit if requested** — `feat: add Tauri workbench UI wired to local runtime`

---

