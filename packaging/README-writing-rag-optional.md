# 写作 RAG 可选包

与**标准底座包**分离的增购/选装包：公文写作 + 本地向量检索（`tier: heavy`）。**不要**合并进标准包的 `runtime/requirements.txt`。

## 仓库内已有内容

本仓库已迁入：

- Skill：`optional-skills/gongwen-rag-writing/`
- 依赖清单：`optional-skills/gongwen-rag-writing/requirements.txt`（含 torch，**勿**并入标准 `runtime/requirements.txt`）
- 模型目录占位：`optional-skills/gongwen-rag-writing/models/`（需自行放入 `bge-small-zh-v1.5/`）

源 zip：仓库根目录 `公文写作_gongwen-rag-writing.zip`（可继续用于客户侧离线导入）。

## 包内内容

| 组件 | 说明 |
|------|------|
| Skill 目录 | `optional-skills/gongwen-rag-writing/`（含 `SKILL.md`、`scripts/` 等） |
| 离线模型 | 随包或内网介质提供的 embedding 模型（如 bge 系列），**禁止**运行时从 Hugging Face 等公网拉取 |
| 声明依赖 | Torch / sentence-transformers 等仅在本可选包文档或 Skill 锁文件中声明，由运维在独立 venv 或扩展环境中安装 |

工作区索引与缓存默认落在当前工作区 `.office-agent/rag/gongwen-rag-writing/`（与产品设计一致）。

## 机器基线

- **推荐**：约 **8GB** 内存；模型按需加载，任务结束宜释放，避免在 4GB 机上常驻。
- 标准底座（4GB）仍可安装本 zip，但 UI 会在启用 heavy Skill 时提示内存要求；不建议在低配机默认启用。

## 如何 zip 导入

1. 在内网准备可选包 zip（含 Skill 目录结构及已审核的离线模型文件，若模型过大可拆为「Skill zip + 模型目录」两步拷贝，路径在 Skill 文档中说明）。
2. 打开办公智能体工作台 → **Skill** 面板 → **导入**（选择 zip 或内网路径）。
3. Runtime 解压到 `app_data` 下 Skill 安装区；首次启用前确认 embedding 模型路径已在内网就位（环境变量或 Skill 包内 `./models/`）。
4. 在 Skill 列表中启用 `gongwen-rag-writing`；若提示 heavy / 内存，确认本机满足约 8GB 后再保持启用。
5. 标准底座 Runtime **无需**重装；本包不修改标准 `requirements.txt`。若 Skill 自带 Python 额外依赖，按 Skill 附带的内部安装说明在受控环境中安装（仍须通过 `check_licenses.sh` 扫描）。

## 与标准包关系

- 标准包：[README-standard.md](./README-standard.md) — 无 Torch，4GB 基线。
- 断网/内网策略、许可证扫描与 NOTICE 与标准包一致；可选包单独发版时同样执行许可证检查。
