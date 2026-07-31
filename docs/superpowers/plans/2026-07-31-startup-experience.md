# 启动体验（去白屏 + 轻度加速）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 安装版双击后立刻显示带四条介绍轮播的启动页；sidecar 非阻塞拉起；Runtime 更快可 `/health`（目标同机约 3–5s），避免长时间白屏感。

**Architecture:** 内联 HTML/CSS/JS 启动层不依赖 React bundle；Rust `setup` 后台线程 spawn sidecar（去掉 sleep）；Runtime lifespan 后台 seed，且 `openai`/`httpx` 延迟到 `ModelGateway` 构造时导入；前端启动期高频轮询 `/health`，超时标为未就绪。

**Tech Stack:** Tauri 2 · React · TypeScript · Vitest · FastAPI · uvicorn · PyInstaller sidecar · pytest

**Spec:** `docs/superpowers/specs/2026-07-31-startup-experience-design.md`（已批准）

## Global Constraints

- 启动主文案固定：**「正在启动本地运行组件…」**
- 轮播四条必须与 `GUIDE_PILLARS` 的 **title + summary** 同义一致（`index.html` 与 `guide.ts` 两处同改）
- 不做 Runtime 常驻、不换打包方案、不做原生多窗口闪屏、不做假百分比进度
- 关应用仍停止 sidecar（`stop_child` / `/shutdown`）
- Commit：英文 conventional commits；用户可见文案用中文

---

## File Structure

```
apps/desktop/
  index.html                 # 内联启动层 + 轮播 JS
  src/main.tsx               # React 挂载后 dismiss 启动层
  src/App.tsx                # 启动期高频 health 轮询 + 超时 → down
  src/lib/guide.ts           # 已有四条支柱（对照源）
  src/lib/guide.test.ts      # 增加：四条与启动页契约（读 index.html）
  src/lib/bootSplash.ts      # NEW — dismissBootSplash() 单一入口
  src/lib/bootSplash.test.ts # NEW — DOM dismiss 行为
  src-tauri/src/lib.rs       # 后台 spawn；删除 sleep(800ms)
runtime/src/office_agent/
  gateway.py                 # openai/httpx 延迟 import
  app.py                     # lifespan：后台 seed，不挡 startup complete
runtime/tests/
  test_gateway.py            # 延迟 import 后行为仍正确
  test_bundled_seed.py       # 异步 seed 下轮询等到技能出现
```

---

### Task 1: 内联启动页 + React 淡出

**Files:**
- Modify: `apps/desktop/index.html`
- Create: `apps/desktop/src/lib/bootSplash.ts`
- Create: `apps/desktop/src/lib/bootSplash.test.ts`
- Modify: `apps/desktop/src/main.tsx`
- Modify: `apps/desktop/src/lib/guide.test.ts`

**Interfaces:**
- Consumes: `GUIDE_PILLARS` 文案（手工同步进 `index.html`）
- Produces: `dismissBootSplash(): void` — 查找 `#boot-splash`，加 `.boot-splash--done`，约 200ms 后 `remove()`；幂等

- [ ] **Step 1: Write failing dismiss test**

```ts
// apps/desktop/src/lib/bootSplash.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dismissBootSplash } from "./bootSplash";

describe("dismissBootSplash", () => {
  beforeEach(() => {
    document.body.innerHTML =
      '<div id="boot-splash" class="boot-splash"><span>x</span></div>';
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("adds done class then removes the node", () => {
    dismissBootSplash();
    const el = document.getElementById("boot-splash");
    expect(el?.classList.contains("boot-splash--done")).toBe(true);
    vi.advanceTimersByTime(250);
    expect(document.getElementById("boot-splash")).toBeNull();
  });

  it("is a no-op when splash missing", () => {
    document.body.innerHTML = "";
    expect(() => dismissBootSplash()).not.toThrow();
  });
});
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd apps/desktop && npm test -- src/lib/bootSplash.test.ts`

Expected: FAIL（模块不存在）

- [ ] **Step 3: Implement `bootSplash.ts`**

```ts
const SPLASH_ID = "boot-splash";
const FADE_MS = 200;

export function dismissBootSplash(): void {
  const el = document.getElementById(SPLASH_ID);
  if (!el) return;
  el.classList.add("boot-splash--done");
  window.setTimeout(() => {
    el.remove();
  }, FADE_MS);
}
```

- [ ] **Step 4: Replace `apps/desktop/index.html` body with splash + root**

保留 `lang="zh-CN"` / charset / viewport / title「文书通」。在 `<head>` 增加内联 `<style>`，在 `<body>` 增加 `#boot-splash` 与轮播脚本。要点：

- 背景 `#f3f4f1`；居中品牌「文书通」、主句「正在启动本地运行组件…」
- 轮播数组与 `GUIDE_PILLARS` title/summary 一致（四条）；每 2800ms 切换；`opacity` 过渡
- `#boot-splash` 使用 `position:fixed; inset:0; z-index:9999`
- `.boot-splash--done { opacity: 0; pointer-events: none; transition: opacity 200ms ease-out; }`
- `#root` 仍存在；轮播用纯 DOM，不依赖外部文件

轮播数据（必须逐字一致）：

```js
var PILLARS = [
  { title: "本地可控", summary: "材料在文件夹里办，用什么模型自己定。" },
  { title: "轻量可跑", summary: "标准包轻，老旧机也能用。" },
  { title: "方法沉淀", summary: "好流程变成可复用技能。" },
  { title: "能力插拔", summary: "专项技能可安装、可分享。" }
];
```

- [ ] **Step 5: Call dismiss from `main.tsx` after render**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { dismissBootSplash } from "./lib/bootSplash";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
dismissBootSplash();
```

- [ ] **Step 6: Extend `guide.test.ts` — splash copy sync**

```ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));

it("index.html boot splash mirrors GUIDE_PILLARS title+summary", () => {
  const html = readFileSync(resolve(here, "../../index.html"), "utf8");
  for (const p of GUIDE_PILLARS) {
    expect(html, p.title).toContain(p.title);
    expect(html, p.summary).toContain(p.summary);
  }
  expect(html).toContain("正在启动本地运行组件");
});
```

- [ ] **Step 7: Run tests**

Run: `cd apps/desktop && npm test -- src/lib/bootSplash.test.ts src/lib/guide.test.ts`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add apps/desktop/index.html apps/desktop/src/main.tsx \
  apps/desktop/src/lib/bootSplash.ts apps/desktop/src/lib/bootSplash.test.ts \
  apps/desktop/src/lib/guide.test.ts
git commit -m "$(cat <<'EOF'
feat: show inline boot splash with pillar carousel

Avoid blank WebView while React loads; dismiss splash after mount.
EOF
)"
```

---

### Task 2: 启动期高频 health 轮询与超时

**Files:**
- Create: `apps/desktop/src/lib/bootHealth.ts`
- Create: `apps/desktop/src/lib/bootHealth.test.ts`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/lib/guide.ts`（可选 `bootWaiting` / down 文案）
- Modify: `apps/desktop/src/components/ChatPanel.tsx`（可选空态）

**Interfaces:**
- Consumes: `runtimeClient.health()`、`runtimeLogHint()`
- Produces:
  - `BOOT_TIMEOUT_MS = 25_000`
  - `bootPollInterval(elapsedMs: number): number`
  - `shouldMarkDownDuringBoot(elapsedMs: number, lastOk: boolean): boolean`

推荐行为：

| 阶段 | 轮询间隔 | down 条件 |
|------|----------|-----------|
| 自挂载起 `elapsed < 25s` | **1000ms** | 仅当 `elapsed >= 25000` 且仍失败 |
| `elapsed >= 25s` 后 | **8000ms** | 连续失败 ≥ 2（保持现逻辑） |

- [ ] **Step 1: Add `bootHealth.ts` + failing test**

```ts
// apps/desktop/src/lib/bootHealth.ts
export const BOOT_TIMEOUT_MS = 25_000;
export const BOOT_POLL_MS = 1_000;
export const STEADY_POLL_MS = 8_000;

export function bootPollInterval(elapsedMs: number): number {
  return elapsedMs < BOOT_TIMEOUT_MS ? BOOT_POLL_MS : STEADY_POLL_MS;
}

export function shouldMarkDownDuringBoot(elapsedMs: number, lastOk: boolean): boolean {
  if (lastOk) return false;
  return elapsedMs >= BOOT_TIMEOUT_MS;
}
```

```ts
// apps/desktop/src/lib/bootHealth.test.ts
import { describe, expect, it } from "vitest";
import {
  BOOT_TIMEOUT_MS,
  bootPollInterval,
  shouldMarkDownDuringBoot,
} from "./bootHealth";

describe("bootHealth", () => {
  it("polls every 1s during boot window", () => {
    expect(bootPollInterval(0)).toBe(1000);
    expect(bootPollInterval(24_999)).toBe(1000);
  });
  it("polls every 8s after boot window", () => {
    expect(bootPollInterval(BOOT_TIMEOUT_MS)).toBe(8000);
  });
  it("marks down only after boot timeout while still failing", () => {
    expect(shouldMarkDownDuringBoot(5_000, false)).toBe(false);
    expect(shouldMarkDownDuringBoot(BOOT_TIMEOUT_MS, false)).toBe(true);
    expect(shouldMarkDownDuringBoot(BOOT_TIMEOUT_MS, true)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test — expect FAIL then implement — expect PASS**

Run: `cd apps/desktop && npm test -- src/lib/bootHealth.test.ts`

- [ ] **Step 3: Wire `App.tsx` health effect**

替换现有「立即 check + `setInterval(8000)`」为：

- `bootStartedAt = Date.now()`（effect 内）
- 用可重排的 `setTimeout` 链：每次 `checkHealth` 后按 `bootPollInterval(Date.now()-bootStartedAt)` 安排下一次
- 成功：`setHealth("ok")`；失败且 `shouldMarkDownDuringBoot(...)`：`setHealth("down")`；boot 窗口内失败保持 `"checking"`（不要因 `failCount>=2` 过早 down）
- cleanup：`clearTimeout`

可选：`GUIDE_HINTS.bootWaiting = "首次启动约需数秒，请稍候。"`；`health==="down"` 时空态提示关闭重开并带 `runtimeLogHint()`。

- [ ] **Step 4: Run frontend tests**

Run: `cd apps/desktop && npm test`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/lib/bootHealth.ts apps/desktop/src/lib/bootHealth.test.ts \
  apps/desktop/src/App.tsx apps/desktop/src/lib/guide.ts \
  apps/desktop/src/components/ChatPanel.tsx
git commit -m "$(cat <<'EOF'
feat: poll runtime health aggressively during boot

Keep checking status until timeout instead of blank waiting.
EOF
)"
```

---

### Task 3: Tauri 后台 spawn，去掉 sleep

**Files:**
- Modify: `apps/desktop/src-tauri/src/lib.rs`

**Interfaces:**
- Consumes: 现有 `try_spawn_runtime(app, api_token) -> Option<Child>`
- Produces: 同签名；调用改为后台线程；`RuntimeProcess` 在线程内写入；删除 `sleep(800ms)`

- [ ] **Step 1: Remove sleep in `try_spawn_sidecar`**

删除成功分支中的 `std::thread::sleep(Duration::from_millis(800));`

- [ ] **Step 2: Spawn runtime off the setup thread**

```rust
.setup(|app| {
    let api_token = generate_runtime_token();
    app.manage(RuntimeAuthToken(Mutex::new(api_token.clone())));
    app.manage(RuntimeProcess(Mutex::new(None)));
    let handle = app.handle().clone();
    std::thread::spawn(move || {
        let child = try_spawn_runtime(&handle, &api_token);
        if let Some(state) = handle.try_state::<RuntimeProcess>() {
            if let Ok(mut guard) = state.0.lock() {
                *guard = child;
            }
        }
    });
    Ok(())
})
```

`Exit` 处理：在 `stop_child` 之外，若 `guard` 仍为 `None`，仍调用现有 `request_runtime_shutdown()`，避免竞态下子进程已监听但尚未塞进 Mutex。

- [ ] **Step 3: Compile check**

Run: `cd apps/desktop/src-tauri && cargo check`

Expected: 无 error

- [ ] **Step 4: Commit**

```bash
git add apps/desktop/src-tauri/src/lib.rs
git commit -m "$(cat <<'EOF'
fix: spawn runtime sidecar off the UI setup thread

Remove post-spawn sleep so the window can show sooner.
EOF
)"
```

---

### Task 4: Gateway 延迟导入 `openai` / `httpx`

**Files:**
- Modify: `runtime/src/office_agent/gateway.py`
- Modify: `runtime/tests/test_gateway.py`

**Interfaces:**
- Consumes: `AppConfig`
- Produces: `ModelGateway.__init__` 行为不变；模块加载时不 import `openai`/`httpx`

- [ ] **Step 1: Add failing test for lazy import**

```python
def test_gateway_module_does_not_import_openai_at_load():
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src/office_agent/gateway.py"
    text = src.read_text(encoding="utf-8")
    preamble = text.split("class ModelGateway")[0]
    assert "from openai import OpenAI" not in preamble
    assert "from httpx import Timeout" not in preamble
    cfg = AppConfig(
        api_base="http://10.0.0.8:8000/v1",
        api_key="x",
        model="deepseek-v4-flash",
        allowed_hosts=["10.0.0.8"],
    )
    ModelGateway(cfg).assert_allowed()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd runtime && .venv/bin/pytest tests/test_gateway.py::test_gateway_module_does_not_import_openai_at_load -v`

- [ ] **Step 3: Implement lazy imports in `gateway.py`**

在 `ModelGateway.__init__` 内：

```python
from httpx import Timeout
from openai import OpenAI
```

删除文件顶部对应 import。保留既有 allowlist / API Key 校验与 `Timeout(600.0, connect=30.0)`。

- [ ] **Step 4: Run full gateway tests**

Run: `cd runtime && .venv/bin/pytest tests/test_gateway.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add runtime/src/office_agent/gateway.py runtime/tests/test_gateway.py
git commit -m "$(cat <<'EOF'
perf: lazy-import openai/httpx in ModelGateway

Shorten runtime cold-start import chain before /health.
EOF
)"
```

---

### Task 5: Lifespan 后台 seed，health 不阻塞

**Files:**
- Modify: `runtime/src/office_agent/app.py`（`_app_lifespan`）
- Modify: `runtime/tests/test_bundled_seed.py`

**Interfaces:**
- Consumes: `seed_bundled_assets()`
- Produces: lifespan 在 seed 完成前即可响应 `/health`；seed 仍在进程内尽快执行

- [ ] **Step 1: Add test — health OK while seed artificially slow**

```python
import threading
import time

def test_health_available_before_slow_seed_finishes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    repo_bundled = Path(__file__).resolve().parents[2] / "bundled"
    monkeypatch.setenv("OFFICE_AGENT_BUNDLED", str(repo_bundled.resolve()))

    release = threading.Event()
    real_seed = seed_bundled_assets

    def slow_seed(*args, **kwargs):
        release.wait(timeout=5)
        return real_seed(*args, **kwargs)

    monkeypatch.setattr("office_agent.app.seed_bundled_assets", slow_seed)

    with TestClient(create_app()) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        release.set()
        deadline = time.time() + 5
        while time.time() < deadline:
            skills = client.get("/skills").json()["skills"]
            if any(s["id"] == "government-document-format" for s in skills):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("seed did not finish")
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd runtime && .venv/bin/pytest tests/test_bundled_seed.py::test_health_available_before_slow_seed_finishes -v`

- [ ] **Step 3: Change lifespan**

```python
@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    t = threading.Thread(target=seed_bundled_assets, name="seed-bundled", daemon=True)
    t.start()
    yield
```

- [ ] **Step 4: Update `test_bundled_assets_seeded_on_app_startup` to poll**

在 `with TestClient(...) as client:` 内短轮询（最多 ~3s）直到 `government-document-format` 出现，再做原有断言。

- [ ] **Step 5: Run seed + health tests**

Run: `cd runtime && .venv/bin/pytest tests/test_bundled_seed.py tests/test_app_api.py::test_health -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add runtime/src/office_agent/app.py runtime/tests/test_bundled_seed.py
git commit -m "$(cat <<'EOF'
perf: seed bundled assets after runtime accepts health

Start uvicorn readiness without waiting on skill copy.
EOF
)"
```

---

### Task 6: 同机冷启动计时验收

**Files:**
- 可选：`packaging/VERIFY-macos.md`、`packaging/VERIFY-windows.md` 增加启动页勾选

**Interfaces:** 无

- [ ] **Step 1: 测 staged sidecar 冷/热启动至 `/health`**

```bash
lsof -ti:8765 | xargs kill -9 2>/dev/null || true
SIDECAR="apps/desktop/src-tauri/resources/runtime/office-agent-runtime"
# 若无，则 packaging/dist/office-agent-runtime/office-agent-runtime
cd "$(dirname "$SIDECAR")"
"$SIDECAR" --host 127.0.0.1 --port 8765 &
# 轮询 /health，记录秒数；目标相对基线 ~8.4s 下降，落在约 3–5s 更佳
```

记录冷启动与热启动秒数。

- [ ] **Step 2: 手工打开桌面壳**

确认：启动页 + 轮播 → 淡出三栏 → 顶栏「启动中…」→「就绪/待配置」；关应用后 8765 退出。

- [ ] **Step 3: 回归**

```bash
cd runtime && .venv/bin/pytest -q
cd apps/desktop && npm test && npm run build
cd apps/desktop/src-tauri && cargo check
```

Expected: 全绿

- [ ] **Step 4: 若改了 VERIFY 清单则 commit，否则跳过**

```bash
git commit -m "docs: note boot splash checks on package verify lists"
```

---

## Self-Review (plan vs spec)

| Spec 要求 | Task |
|-----------|------|
| 内联启动页 + 纸感色 + 主文案 | Task 1 |
| 四条 GUIDE_PILLARS 轮播 + 与 guide.ts 同步 | Task 1 |
| React 挂载后淡出 | Task 1 |
| 启动期轮询 / 20–30s 超时 → down | Task 2 |
| Rust 后台 spawn、去 sleep、退出仍停 | Task 3 |
| health 不依赖 seed | Task 5 |
| openai/httpx 延迟 import | Task 4 |
| 冷启动计时验收 | Task 6 |
| 不做常驻 / 换打包 / 原生闪屏 / 假进度 | Global Constraints |

无 TBD；前后 Task 接口名一致。
