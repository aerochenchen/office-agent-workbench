# P-Plan 续跑 · 评测夹具

配合 `../../2026-08-04-capability-quality-ab-eval.md` 与 `../../../specs/2026-08-04-agent-plan-execute-design.md` §7 / §9.2 使用。

## 场景

模拟用户中断后恢复：工作区已有 active Plan，前两步已完成，后两步待执行。Agent 应续跑而非重建 Plan。

**与 P2 确认关的关系：**

- **新建计划**（`plan_create`）默认 `approval=pending`，须写 `工作成果/工作计划.html` 并经用户确认（`ask_user` → `plan_set_approval(approved)`）后方可推进步骤。
- **本夹具为续跑场景**：`seed-plan.json` 已标 `"approval": "approved"`，模拟用户此前已确认，Agent 可直接推进 s3/s4，**不**应再次全盘确认。
- 展示文件 `工作成果/工作计划.html` 仅供查阅；修改计划须在对话框提出，权威仍为 `.office-agent/work/plan.json`（§6.4）。

## 人工 / AB 步骤

1. 打开空文件夹作为临时工作区。
2. 将 `seed-plan.json` 复制为 `.office-agent/work/plan.json`。
3. （可选）在 `工作成果/` 放置两份占位已完成说明，与 s1/s2 的 `outputs` 对应：
   - `工作成果/材料清单.md`
   - `工作成果/要点摘录.md`
4. 用户话术：**按工作计划未完成项继续**
5. 观察 Agent 是否：
   - 调用 `plan_get` 读取现有 Plan；
   - 推进 **s3**（汇总对照），而非 `plan_create` 重建；
   - **不**因确认关再次 ask_user 全盘确认（seed 已 approved）；
   - 最终 Plan 标 `completed`，或至少剩余 pending 项减少。

## 金标（通过条件）

| 项 | 期望 |
|----|------|
| 续跑纪律 | 不重新规划；先 `plan_get` |
| 确认关 | 不重复确认（seed `approval=approved`） |
| 步骤推进 | s3 → s4 顺序执行，依赖满足 |
| 终态 | Plan `completed` 或 s3/s4 中至少一项变为 `done` |
| 产物 | `工作成果/` 出现 s3/s4 声明的交付物（或等价说明） |

## 文件

| 文件 | 说明 |
|------|------|
| `seed-plan.json` | 4 步示例 Plan（s1/s2 `done`，s3/s4 `pending`，`approval=approved`）；须通过 `validate_plan` |

## 本地校验

```bash
cd runtime && python3 -c "
from pathlib import Path
from office_agent.plan_store import validate_plan
import json
p=Path('../docs/superpowers/evals/fixtures/plan-resume/seed-plan.json')
validate_plan(json.loads(p.read_text(encoding='utf-8')))
print('ok')
"
```

Expected: `ok`
