# 标准底座安装包

面向内网办公场景的默认交付物：**不含** PyTorch / sentence-transformers / transformers 等写作 RAG 重依赖。

## 包内内容

| 组件 | 说明 |
|------|------|
| `apps/desktop/` | Tauri 2 + React 工作台（工作区、对话、Skill 面板） |
| `runtime/` | 本地 Python Runtime（FastAPI，127.0.0.1），轻量 `requirements.txt` |
| `bundled/skills/` | 预置轻量 Skill（如 `government-document-format`，`tier: light`） |
| `bundled/shared-scripts/` | 与轻量 Skill 配套的共享脚本（如排版占位/实现） |

标准包**不包含** `optional-skills/gongwen-rag-writing/`、离线 embedding 模型或 Torch 运行时。

## 机器基线

- **最低**：Windows 10+（交付重点），约 **4GB** 内存 — 底座对话 + 轻量 Skill。
- **磁盘**：预留 Python 虚拟环境与 SQLite 会话数据；具体体积随 Skill 选装变化。
- 启用重量级写作 RAG 请改用 [写作 RAG 可选包](./README-writing-rag-optional.md)（建议 **8GB** 内存）。

## 依赖原则

- `runtime/requirements.txt` 仅声明 FastAPI、uvicorn、openai、pydantic、PyYAML、httpx 等轻依赖。
- 发版前在 `runtime/.venv` 执行仓库根目录 `scripts/check_licenses.sh`，禁止 GPL/AGPL 污染。
- 运行时仅允许白名单内网 API Host；Skill/模型禁止运行时从公网下载。

## 安装与升级（概要）

1. 解压或安装标准底座到目标目录。
2. 创建并填充 `runtime/.venv`（`pip install -e runtime` 或按内部安装手册）。
3. 启动桌面壳；Runtime 由 Tauri 拉起或按文档独立启动。
4. 额外 Skill 通过 UI「导入 zip」安装到 `app_data`，不影响标准包体积。

详细联调步骤见项目根 `README` 与 `docs/superpowers/specs/2026-07-23-office-agent-runtime-design.md`。
