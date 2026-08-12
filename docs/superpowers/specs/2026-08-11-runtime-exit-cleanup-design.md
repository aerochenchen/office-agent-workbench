# Runtime 退出清理与脏端口自愈

| 项 | 内容 |
|----|------|
| 日期 | 2026-08-11 |
| 状态 | 已批准（对话确认「按建议」） |
| 范围 | 桌面壳关窗后 `office-agent-runtime` 残留；再开因 8765 被占 skip spawn 导致异常 |

## 问题

关窗后 Windows 上 sidecar 偶发不退出。再开时壳见 8765 已监听便 skip auto-start，但旧进程持有上一轮 token，与本次启动 token 不一致，UI 表现为无法正常使用本地运行时。

## 目标

1. **关窗即停**：本应用拉起的 Runtime 随壳退出（含异常关窗路径）。
2. **脏端口自愈**：启动时若 8765 已有进程但不接受本次 token，先 `/shutdown` 再拉起。
3. **不破坏开发态**：未设 token / 接受本次 token 的外部 Runtime 仍可复用（skip spawn）。

## 非目标

- 托盘常驻、故意热保活 Runtime
- 持久化跨启动的 API token

## 方案

### A. 可靠退出清理

- 在 `RunEvent::ExitRequested` 与 `RunEvent::Exit` 均触发清理（幂等：`take` Child + AtomicBool）。
- Windows：spawn 后将子进程加入 **Job Object**（`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`），父进程退出时 OS 杀光作业内进程，兜底 `/shutdown` 未送达的情况。

### B. 启动自愈

- 若 TCP `127.0.0.1:8765` 可达：用本次 token 探测受保护接口（如 `GET /config`）。
- **200** → 视为可复用，skip spawn（开发态）。
- **否则**（401 / 失败）→ `POST /shutdown`，短等待端口释放，再 spawn，并置 `ATTEMPTED_RUNTIME_SPAWN`。

### C. 验收

- 关主窗口后任务管理器无残留 `office-agent-runtime`。
- 故意残留旧 Runtime 再开：能自愈并 `/health` 正常。
- 契约测试覆盖：ExitRequested 清理路径、token 探测与 reclaim 分支存在。

## 取舍

关干净会让下次付冷启动成本（数秒）。正确性优先于用孤儿进程换热启动。
