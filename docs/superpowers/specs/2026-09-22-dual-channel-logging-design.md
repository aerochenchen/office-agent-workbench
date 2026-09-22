# 文书通 · 双通道日志（诊断 + 安全审计）设计

| 项 | 内容 |
|---|---|
| 状态 | 已实施 |
| 日期 | 2026-09-22 |
| 版本 | V1.0 |
| 范围 | Runtime 诊断 JSONL、审计事件表升级、桌面壳启停/健康诊断；设置页导出 |
| 对照 | `runtime/src/office_agent/audit.py`、`app.py`、`permissions.py`、`gateway.py`、`paths.py`；`apps/desktop/src-tauri/src/lib.rs` `log_line`；`docs/文书通-数据类型清单-中国合规.md` D07/D10 |
| 看板 | Cursor Canvas：`logging-and-audit-design.canvas.tsx` |

---

## 1. 目的

把「这次为什么失败」和「谁在何时做了何决策」拆开。

当前 `audit.sqlite` 只记工具调用（`ts, tool, args_json, ok, detail, turn_id`），正文/密钥已脱敏。配置变更、技能安装、权限弹窗里点允许、删会话、本地部署拒公网模型、非交互 `/chat` 绕过确认——都不落库。`logs/` 目录会创建但几乎不写。桌面壳把非结构化行写到系统临时目录 `office-agent-desktop.log`，与 Runtime 对不上。

目标：一次失败对话能用 `turn_id` 还原因果；单位能导出证明「谁开过自定义脚本 / 改过权限 / 导过 zip」。

---

## 2. 决策

| 项 | 选择 |
|---|---|
| 形态 | **方案 B 双通道**：诊断 JSONL + 审计事件表。不扩成一张万能表，也不做本机 SIEM |
| P0 范围 | Runtime 进程日志 **含** 桌面壳 sidecar 启停与健康失败（否则分不清壳先挂还是 Runtime 先挂） |
| 审计存储 | 升级现有 `db/audit.sqlite`，不新建第二套 sqlite |
| 上报 | 默认不上报到开发者；syslog / 管理员目录镜像为 P2 |
| 完整性 | P0/P1 预留 `prev_hash` 列但可空；P2 再填。不宣称本机不可篡改 |
| 身份 | 无账号。`actor` = OS 用户名；`instance_id` = 首次启动写入应用数据目录的 UUID |

否决：A（只扩现有表，排障与取证搅在一起）；C（第一期上 hash 链 + syslog + 仪表盘）。

---

## 3. In / Out

**In**

- 结构化诊断：按日 JSONL，滚动保留约 30 天
- 审计从「只记 tool」改为通用 `event_type`；旧行兼容为 `tool_invoked`
- 配置 / 权限决策 / 技能安装卸载 / 删会话 / 模型 host 拒绝 / API 路由形态入审计
- 桌面壳：`boot` / `sidecar_spawn` / `sidecar_exit` / `health_fail` 写入同一 `logs/` 树
- 设置：只读「最近审计」+ 导出 JSONL（已脱敏）；界面不提供清空审计

**Out（本规格）**

- 崩溃/分析遥测 SDK、把会话全文镜像进审计
- 用户 ID / 邮箱当指标标签
- 第一期 syslog、只读网络盘镜像、hash 链强制非空
- 改 `sessions.sqlite` 的对话存储语义
- 把 `%TEMP%/office-agent-desktop.log` 立刻删掉（P0 可双写，P1 再把 UI 提示改到 `logs/`）

---

## 4. 架构

```
桌面壳 (boot_id) ──JSONL──► logs/desktop-YYYY-MM-DD.jsonl
Runtime HTTP (turn_id=request_id)
  ├─ 诊断 ──JSONL──► logs/runtime-YYYY-MM-DD.jsonl
  └─ 审计 ──INSERT─► db/audit.sqlite
对话全文 ──────────────► db/sessions.sqlite（不复制进审计）
```

同一动作允许写两条：诊断带 `duration_ms` / `error_code`；审计带 `actor` / `outcome` / 对象。写盘失败不得拖垮对话：审计失败记一条诊断 `audit_write_failed`，业务继续。

路径均在 `app_data_dir()` 下（`~/.office-agent` 或 `OFFICE_AGENT_DATA`）。`logs/` 已由 `paths.py` 创建。

---

## 5. 诊断日志

### 5.1 文件

| 文件 | 写入方 |
|---|---|
| `logs/runtime-YYYY-MM-DD.jsonl` | Runtime（Python logging JSON handler，sidecar 启动时配置） |
| `logs/desktop-YYYY-MM-DD.jsonl` | 桌面壳 `log_line` 升级为结构化行；P0 可同时 append 旧临时文件 |

滚动：按日换文件。启动时删除早于 30 天的 `runtime-*.jsonl` / `desktop-*.jsonl`。单文件超过 20MB 则改写 `…-YYYY-MM-DD.N.jsonl`。级别：`error` / `warn` / `info` / `debug`；默认 info，环境变量 `OFFICE_AGENT_LOG_LEVEL` 可调。

### 5.2 每行字段（稳定名）

必填：`ts`（ISO-8601 UTC）、`level`、`event`、`boot_id`（壳）或 `turn_id`（对话内；无对话时用 `-`）。

常用：`session_id`、`duration_ms`、`error_code`、`tool`、`returncode`、`route`。

禁止：`api_key`、token、密码、公文/材料正文、完整 `messages`、模型生成全文。路径只记工作区相对名或末级目录名。

### 5.3 P0 诊断事件

| event | 何时 |
|---|---|
| `boot` | 桌面进程启动；带 `boot_id`、版本 |
| `sidecar_spawn` / `sidecar_exit` | 拉起/回收 Runtime；exit 带 returncode |
| `health_fail` | `/health` 连续失败达到现有阈值 |
| `runtime_start` | FastAPI 进程起来；回写 `boot_id`（若环境变量传入） |
| `chat_started` / `chat_finished` | 一轮对话起止；finished 带 status、步数、耗时 |
| `gateway_error` | 模型调用失败；`error_code` + `host_class`（loopback / intranet / denied）+ `status_class`（4xx/5xx/timeout），不存响应体 |
| `script_denied` / `script_timeout` | jail / 超时；稳定码，stderr 仍截断 ≤500 且不进诊断全文时可只放 `error_code` |
| `session_persist_failed` | 会话 SQLite 写入失败 |
| `audit_write_failed` | 审计 INSERT 失败 |
| `permission_timeout` | 权限弹窗 300s 超时 |

---

## 6. 安全审计

### 6.1 表迁移

表名仍为 `audit`。`CREATE TABLE IF NOT EXISTS` 保持旧列，用 `PRAGMA table_info` 补列（与现有 `turn_id` 迁移同一模式）：

| 列 | 类型 | 说明 |
|---|---|---|
| ts | REAL | 已有 |
| tool | TEXT | 已有；非工具事件可空或填 `-` |
| args_json | TEXT | 已有；继续走 `_redact_args` |
| ok | INTEGER | 已有；与 `outcome` 对齐：ok=1 仅当 outcome=ok |
| detail | TEXT | 已有；≤500 |
| turn_id | TEXT | 已有 |
| event_type | TEXT | 新；旧行读取时默认 `tool_invoked` |
| session_id | TEXT | 新 |
| actor | TEXT | 新；OS 用户名 |
| instance_id | TEXT | 新 |
| outcome | TEXT | 新；`ok` / `deny` / `timeout` / `error` |
| error_code | TEXT | 新；稳定码 |
| attrs_json | TEXT | 新；小白名单对象 |
| prev_hash | TEXT | 新；P0/P1 可空 |

`AuditLog.record` 改为：

```text
record(event_type, *, outcome, turn_id=None, session_id=None,
       tool=None, args=None, detail="", error_code=None, attrs=None)
```

旧 `record(tool, args, ok, detail, turn_id=)` 保留为包装，映射到 `event_type=tool_invoked`，避免一次改光所有测试调用点；新代码走新签名。

`instance_id`：文件 `app_data/instance_id`（单行 UUID，`chmod` 与 config 同级私有）。首次启动生成。

### 6.2 审计事件（P1 必做）

| event_type | 触发点 | attrs 要点 | 用途 |
|---|---|---|---|
| `tool_invoked` | `ToolExecutor._audit`（已有） | 补 session_id、error_code、duration_ms 可放诊断 | 操作追溯 |
| `chat_started` | `/chat` 与 `/chat/stream` 入口 | `route`、`workspace_hash` | 任务起点；区分非交互绕过 |
| `permission_decision` | `PermissionGate.resolve` / 超时 / deny | tool、`decision=allow\|deny\|timeout`、mode | 知情同意；**允许也要记** |
| `config_changed` | `POST /config` 保存前 | 变更键；`allow_workspace_scripts` / `permission_mode` 记新旧值；`api_base` 只记 host | 开脚本、改信任、改出口 |
| `model_host_rejected` | 本地部署拒绝公网 host | host、profile=local | 试图外联 |
| `skill_install` | `POST /skills/install` 成功后 | skill_id、source=zip\|dir、sha256（文件）、permissions 列表 | 来路 |
| `skill_uninstall` | `DELETE /skills/{id}` | skill_id | 卸证 |
| `skill_enabled` | `POST /skills/{id}/enabled` | skill_id、enabled | 开关 |
| `session_deleted` | `DELETE /sessions/{id}` **先于** 真正删除 | session_id | 灭迹 |
| `workspace_opened` | `POST /workspace/open` | `workspace_hash`（sha256 规范化路径）；不存绝对路径明文 | 材料范围 |
| `api_auth_fail` | token 中间件拒绝 | route、reason=missing\|mismatch | 本机口被扫 |
| `script_denied` | jail / 工作区脚本关闭 | jail_reason、path 相对名 | 越权尝试 |
| `sandbox_escape_blocked` | argv/路径逃出工作区 | attempted 类别 | 提权未遂 |

`finish` 后 P1 做交付核对：诊断事件 `deliverable_claimed` / `deliverable_verified`（路径存在且魔数为 zip/xlsx/pptx）。核对失败不拦截用户可见回复，但 `chat_finished.status` 标 `unverified_deliverable`。

### 6.3 导出与 UI

- `GET /audit/export?since=`（unix ts，可选）：`application/x-ndjson`，每行一条已脱敏审计。仅本机 + 现有 API token。
- 设置页：「导出使用审计」下载上述 JSONL；「最近 20 条」只读列表（时间、event_type、outcome、对象摘要）。
- **不提供**清空/删除单条。用户仍可用资源管理器删 `audit.sqlite`——产品不得假装挡得住，见 §8。

---

## 7. 关联 ID

| ID | 生命周期 | 谁生成 |
|---|---|---|
| `boot_id` | 一次桌面进程 | 壳启动；经环境变量 `OFFICE_AGENT_BOOT_ID` 传给 sidecar |
| `turn_id` | 一次用户发送 | Runtime 已有；等于 HTTP 本轮 request_id |
| `session_id` | 一个对话 | 已有 |
| `instance_id` | 该安装实例 | 见 §6.1 |

脚本子进程环境带 `OFFICE_AGENT_TURN_ID`（有则写入）。诊断与审计同行必须能靠 `turn_id` 对齐。

---

## 8. 脱敏、合规、完整性

沿用 `_redact_args`：`content` 只记长度；`api_key` / `key` / `token` / `password` / `passwd` 完全遮罩。新增：`attrs_json` 不得包含上述键；`api_base` 只存 host。

工作区绝对路径：审计用 `sha256(utf-8(resolved))` 十六进制；诊断可用末级目录名。

数据类型清单：诊断 JSONL 新增为「本机使用日志」，处理目的=故障定位，默认不离开本机。D07 从「工具审计」扩展为「安全事件审计」，仍不上报。实现落地后回写 `docs/文书通-数据类型清单-中国合规.md`。

完整性（P2，本规格只预留）：

1. UI 不提供清空。
2. 每条 `prev_hash`（可选 HMAC，密钥在 `secrets.key` 旁，脚本 jail 已拒绝读该文件）。
3. 本地部署可选：把每日审计 JSONL 副本写到管理员配置的目录或本机 syslog。

没有副本时，对外口径是「本机可追溯、用户可删库」，不是「不可篡改」。

---

## 9. 接缝（实现时改这些文件）

| 位置 | 改什么 |
|---|---|
| `audit.py` | 新 `record`、补列、`instance_id`、脱敏复用 |
| `app.py` | chat 起止、`/config`、skill 安装卸载启用、workspace open、session delete、auth fail、export |
| `permissions.py` | allow/deny/timeout 各记 `permission_decision`（注入 AuditLog，避免循环依赖则用回调） |
| `gateway.py` | `GatewayError` 带 `error_code` / `host_class` |
| `tools.py` | 已有 `_audit`；补 duration、error_code；jail 拒绝稳定码 |
| `__main__.py` | 启动配置 JSON 文件 handler 到 `logs/`，替换仅 uvicorn stderr |
| `lib.rs` `log_line` | 结构化 JSON 写入 `logs/desktop-*.jsonl`；生成并下发 `boot_id` |
| 设置 UI | 最近审计 + 导出；`runtimeLogHint` P1 改为指向 `logs/` |

---

## 10. 分期与验收

### P0 先让故障可查

- Runtime + 桌面 JSONL 按日滚动；`boot` / `sidecar_*` / `health_fail` / `chat_*` / `gateway_error` / 脚本稳定码。
- 审计表补列；`tool_invoked` 带 `session_id`、`error_code`。
- 验收：人为断模型地址或杀 sidecar，能用 `boot_id`/`turn_id` 在 `logs/` 里还原，不必翻源码。pytest 覆盖 JSON handler 与旧库迁列。

### P1 再让违规可证

- §6.2 除 hash 链外的全部审计事件。
- 导出 API + 设置页只读/导出。
- `deliverable_verified`。
- 验收：打开自定义脚本、改模型地址（含本地部署拒绝公网）、导入 zip、点拒绝权限——四条都能在导出 JSONL 里找到。`GET /config` 仍不回明文 key。

### P2 单位侧加固（本规格不实施）

- `prev_hash`、可选 syslog/目录镜像、保留策略审计 180 天、本机低基数计数（失败率、拒绝率、脚本开启次数，不上报）。

---

## 11. 测试要点

- 旧 `audit.sqlite` 无新列时打开不丢历史行；新写入含 `event_type`。
- `workspace_write` 的 content 与 api_key 仍不出现在审计/诊断文件中（扩现有 `test_audit_log_redacts_sensitive_args`）。
- `POST /config` 切换 `allow_workspace_scripts` 产生 `config_changed`，新旧值可区分。
- 权限 allow 与 deny 各有 `permission_decision`。
- 删会话：审计行先于 session 行消失。
- 诊断文件不含 `messages` 数组全文。
- 导出接口无 token 时 401（与现有中间件一致）。

---

## 12. 与现行设计的关系

不修改「精炼 Runtime + 选装 Skill」原则。安全基线仍是本机可追溯、默认不上收。本文件是日志/审计的专项规格；冲突时：产品原则以 `2026-07-23-office-agent-runtime-design.md` 为准，日志字段与事件以本文为准。

---

## Spec Self-Review

- [x] 无 TBD；P2 项标明本规格不实施
- [x] 双通道与「单表 / SIEM」取舍已写
- [x] P0 含桌面壳，与用户确认的「可以写规格」及推荐范围一致
- [x] 脱敏与数据类型清单口径一致；导出不上报
- [x] 范围可拆为一个实施计划（P0+P1），P2 单列
