# 会话右键重命名设计

| 项 | 内容 |
|---|---|
| 日期 | 2026-09-23 |
| 状态 | 已批准（对话确认方案 A） |
| 范围 | 左侧会话栏右键菜单、行内改名、`PATCH /sessions/{id}` |
| 非目标 | 双击改名、悬停改名按钮、拖拽排序、分组 |

## 背景

左侧「对话」栏已能列出、新建、切换、删除会话。标题由首条用户消息自动生成（或默认「新对话」），用户无法手动改名。后端 `SessionStore.set_title` 已存在，但无 HTTP 暴露，桌面端无入口。

## 目标

1. 右键会话行打开菜单，含「重命名」「删除」。
2. 「重命名」进入行内编辑；保存后列表与 SQLite 标题一致。
3. 去掉行上悬停「删除」按钮，删除仅走右键菜单（与「重命名」并列）。

## 交互

| 动作 | 行为 |
|---|---|
| 右键会话行 | 在指针附近弹出菜单；右键目标会话可选中高亮（不强制切换消息区，若已在改名中则忽略新菜单） |
| 菜单「重命名」 | 该行标题变为单行 `<input>`，预填当前标题并全选；菜单关闭 |
| Enter | 提交保存 |
| Esc | 取消，恢复原标题 |
| 失焦（blur） | 提交保存（与 Enter 相同校验） |
| 菜单「删除」 | 沿用现有 `confirm` 文案与 `deleteSession` 流程 |
| 发送中 / Runtime 未就绪 | 菜单项禁用；不可进入改名 |
| 改名进行中 | 禁止点击其它会话切换；其它行右键可取消当前编辑或忽略（实现选：**Esc 等价取消后允许新右键**；未保存切换则先取消） |

空串或仅空白 → 存为「新对话」。展示与存储前 `strip`，长度上限 **80** 字符（超出截断）。未改动（与当前标题相同）则不发请求。

## API

`PATCH /sessions/{session_id}`

请求：

```json
{ "title": "季度总结" }
```

响应（200）：

```json
{ "ok": true, "session": { "id": "...", "workspace_path": "...", "title": "季度总结", "created_at": 0, "updated_at": 0 } }
```

错误：

- `404`：会话不存在
- `422` / 校验失败：body 缺 `title` 或类型非字符串（Pydantic）

实现：规范化标题后调用 `office.sessions.set_title`；`get_session` 返回最新 meta。  
审计：记录 `session_renamed`（`session_id`；`attrs` 可含规范化后标题长度，**不**强制记旧标题全文以免噪声）。与 `session_deleted` 对称。

桌面：`runtimeClient.renameSession(id, title)` → 上述 PATCH。

## UI 结构

- `SessionList`：`onContextMenu` → 定位菜单；状态 `renamingId` + `draft`。
- 菜单：`position: fixed` 小面板，点击外部或选菜单项后关闭；`z-index` 低于权限/设置弹层、高于会话列表。
- 样式：沿用 `--paper-2` / `--ink-*` / `--radius-sm`，与现有工具条按钮气质一致；勿引入新色板。

`App.tsx`：`handleRenameSession` → `renameSession` → 刷新 `sessions` 列表（或本地 patch `title` + `updated_at`）。

## 测试

- Runtime：`PATCH` 改标题成功；空标题 →「新对话」；过长截断；不存在 → 404。
- 桌面：标题规范化纯函数单测（trim / 空 / 截断）；可选组件级 smoke 若仓库已有模式则跟，否则不强求。

## 验收

1. 打开文件夹后，右键某会话 → 见「重命名」「删除」。
2. 重命名保存后，列表立刻显示新标题；重启应用后仍保留。
3. 删除仍可用且需确认；行上无悬停「删除」文字按钮。
4. 发送中右键菜单项不可用。
