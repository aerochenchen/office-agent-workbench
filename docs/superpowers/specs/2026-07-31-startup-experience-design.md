# 文书通 · 启动体验（去白屏 + 轻度加速）

| 项 | 内容 |
|---|---|
| 状态 | 已批准（2026-07-31） |
| 日期 | 2026-07-31 |
| 版本 | V1.0 |
| 范围 | 安装包冷启动观感与轻度加速：内联启动页、Tauri 非阻塞拉起 sidecar、Runtime 先健康后播种与延迟导入 |
| 非范围 | 常驻后台服务、更换打包方案（如弃用 PyInstaller）、多窗口原生闪屏、假百分比进度 |
| 受众假设 | 机关/办公室办事员；双击安装版后应立刻看到品牌反馈 |
| 对照 | `apps/desktop/index.html`、`App.tsx`、`guide.ts`、`src-tauri/src/lib.rs`、`runtime/.../app.py`、`gateway.py`、`bundled_seed.py` |
| 前置结论 | 本机实测打包 sidecar 冷启动至 `/health` 约 **8.4s**；热启动约 **0.6s**；前端 dist 约 0.5MB，非主因 |

---

## 1. 目的与问题

### 1.1 目的

1. **消除白屏感**：双击后尽快显示品牌与状态文案，避免长时间空白窗口。
2. **缩短真实冷启动**：在不大改架构的前提下，将 `/health` 可用时间从约 8–10s 压向约 **3–5s**（视机器浮动，以同机前后对比为准）。
3. **等待期有价值**：启动等待时轮播产品四条短介绍，降低焦虑并传递能力印象。

### 1.2 现状问题

- 安装版启动时 Tauri 同步拉起 PyInstaller onedir sidecar；子进程大量原生库冷映射，壁钟约 8s+。
- `index.html` 的 `#root` 在 React/CSS 就绪前为空，浏览器默认白底，叠加「运行时未就绪」空态，用户感知为白屏。
- `lib.rs` 在 spawn 后 `sleep(800ms)`，且 spawn 在 `setup` 主路径上，轻微拖慢窗口就绪。
- Runtime lifespan 内同步 `seed_bundled_assets()`；`gateway` 模块级导入 `openai`/`httpx`，拉长 import 链。

---

## 2. 已确认决策

| 决策 | 结论 |
|------|------|
| 优先级 | **观感 + 轻度加速**（方案 2）；不做常驻 Runtime |
| 改动幅度 | **小改动、低风险**；保持 Tauri + sidecar 架构 |
| 冷启动目标 | 同机相对现状压到约 **3–5s** 可 `/health` |
| 首屏目标 | 双击后约 **&lt;0.5s** 见到内联启动页 |
| 启动主文案 | **「正在启动本地运行组件…」** |
| 轮播内容 | `GUIDE_PILLARS` 四条 **title + summary**（不用长 body） |
| 失败策略 | 约 20–30s 仍无 health →「未就绪」+ 重开/日志 hint；不自动反复 spawn |
| 退出语义 | 关应用仍停止 sidecar（与现网一致） |

---

## 3. 架构与数据流

```
双击应用
  ├─ WebView 加载 index.html → 立刻显示内联启动页
  │     （品牌 +「正在启动本地运行组件…」+ 四条短介绍轮播）
  ├─ Rust setup：后台线程 spawn sidecar（无 sleep）
  └─ React 挂载 → 淡出并移除启动页 → 三栏骨架
        └─ 轮询 GET /health
              ├─ OK → getConfig / listSkills → 顶栏「就绪」或「待配置」
              └─ 超时 →「未就绪」+ 日志路径提示
```

Runtime 进程内目标顺序：

1. 完成必要 import，uvicorn 开始监听。
2. **`/health` 立即返回**（不依赖 seed 完成）。
3. 其后执行 `seed_bundled_assets`（后台或 lifespan 内先对外可探测再 seed）。
4. `openai` / `httpx` 延迟到首次构造 `ModelGateway` / 真正调模型时再 import。

不改：HTTP API 契约、sidecar 资源路径、API token 机制、沙箱与 Skill 语义。

---

## 4. 启动页与前端

### 4.1 内联启动页

- 修改 Vite 源 `apps/desktop/index.html`：在 `#root` 旁（或内）放置启动层，**内联 CSS + 少量内联 JS**，不依赖 `/assets/*.js|css`。
- 视觉：纸感背景 `#f3f4f1`（与 `theme.css` `--paper-0` 一致）；品牌「文书通」；主句「正在启动本地运行组件…」。
- 轮播：四条 `GUIDE_PILLARS` 短文案，约每 **2.5–3s** 切换，淡入淡出；不定进度百分比。
- React 首次挂载完成后：给启动层加隐藏类并移除（或 `display:none` + remove），避免叠层。

### 4.2 文案同步

启动页内联文案必须与 `apps/desktop/src/lib/guide.ts` 中 `GUIDE_PILLARS` 的 **title / summary** 保持同义一致。改介绍词时 **两处同改**（`index.html` 与 `guide.ts`）。

现行四条（V1.0 快照）：

| 标题 | summary |
|------|---------|
| 本地可控 | 材料在文件夹里办，用什么模型自己定。 |
| 轻量可跑 | 标准包轻，老旧机也能用。 |
| 方法沉淀 | 好流程变成可复用技能。 |
| 能力插拔 | 专项技能可安装、可分享。 |

### 4.3 主界面（Runtime 未就绪）

- 壳层照常渲染；顶栏「启动中…」；输入区保持「本地运行时未就绪…」类提示。
- 可选：对话空态补一句「首次启动约需数秒，请稍候」；超时后换成失败文案。
- 不做整页强制 loading 挡住骨架。

### 4.4 超时

- 前端在持续失败约 **20–30s** 后将 health 视为 `down`（可与现有连续失败计数结合或单独 boot 超时）。
- 文案指引关闭重开，并复用 `runtimeLogHint()`。

---

## 5. Rust / Runtime 变更要点

### 5.1 Tauri `lib.rs`

- `try_spawn_runtime` 放入后台线程；`setup` 尽快返回。
- 删除 spawn 成功后的 `std::thread::sleep(800ms)`。
- 仍 best-effort 一次；日志写入现有 temp log；`Exit` 时 `stop_child` 不变。

### 5.2 Runtime

- **`/health` 与 seed 解耦**：监听就绪后即可 200；seed 不阻塞首个 health。
- **`gateway.py`**：去掉模块顶层 `from openai import OpenAI` / `from httpx import Timeout`；在 `__init__`（或首次 chat）内延迟 import。
- 其他已 lazy 的 docx/openpyxl 等保持现状，不必为启动再扩 scope。

### 5.3 验收

| 项 | 标准 |
|----|------|
| 观感 | 冷启动可见启动页（含轮播），无明显长时间纯白 |
| 冷启动 | 同机 `/health` 时间相对基线下降，目标落在约 3–5s 区间（记录前后秒数） |
| 热启动 | 不显著劣化（仍近亚秒～1s 量级） |
| 功能 | 配置、对话、Skill 列表、关应用停 sidecar 回归通过 |
| 文案 | 启动页四条与 `GUIDE_PILLARS` summary 一致 |

---

## 6. 测试要点

- 前端：启动层存在于无 JS bundle 时的静态 HTML；挂载后移除；轮播切换不抛错。
- Runtime：单元/集成测 health 在 seed 未完成（或 mock 慢 seed）时仍可用；`ModelGateway` 延迟 import 后 chat 仍正常。
- 手工：安装包或 staged sidecar 冷启动计时；杀毒开启的 Windows 机抽测观感。

---

## 7. 明确不做（本期）

- Runtime 关应用后常驻 / 系统服务预热。
- 更换为 Nuitka、嵌入式 CPython 发行版等大搬家。
- 独立原生闪屏窗口。
- 假的百分比进度条。
- 为启动体验重写对话入门逻辑（已由 chat-first 规格覆盖）。

---

## 8. 实现顺序建议

1. 内联启动页 + 四条轮播 + React 淡出。  
2. Rust 后台 spawn、去 sleep。  
3. Runtime：health/seed 解耦 + gateway 延迟 import。  
4. 超时文案与同机冷启动计时对比，写入验收记录。  
