# 文书通 PKS 离线包（银河麒麟 × 飞腾 aarch64）

面向 **PKS 信创终端** 的离线交付物：在 **有网 Mac** 上用 Docker 打出安装目录，经 **U 盘** 拷到 **断网银河麒麟 V10 SP1（aarch64）** 安装验收。

技术向验收步骤见 [VERIFY-kylin-pks.md](./VERIFY-kylin-pks.md)；非开发人员跟测见 [验收清单-PKS-给非开发人员.md](./验收清单-PKS-给非开发人员.md)。

## 包内内容

| 组件 | 说明 |
|------|------|
| `文书通_<version>_aarch64.deb` | Tauri 桌面主包（含 WebViewGTK 壳、预置 Skill、Runtime sidecar） |
| `deps/*.deb` | 目标机可能缺失的系统库离线包（以实机 `ldd` 回填） |
| `install-offline.sh` | 断网安装脚本（先 deps 后主包） |
| `deps.manifest` | 依赖清单与说明 |
| `fixtures/` | 验收用样例 `.docx`（排版 / 校对；见下文） |

标准 PKS 包**不含**写作 RAG / Torch 等重依赖，与 [标准底座](./README-standard.md) 策略一致。

## 构建机要求

- **macOS**（Apple Silicon 或 Intel 均可；推荐 Apple Silicon，arm64 构建更顺）
- **Docker Desktop** 已安装并运行
  - 启用 **containerd** 镜像存储（Settings → General，按 Docker 版本界面为准）
  - 能拉取 / 运行 **`linux/arm64`** 容器（Apple Silicon 原生；Intel Mac 需 QEMU 仿真，较慢）
- 仓库根目录可访问网络（拉 Docker 基础镜像、npm/cargo 等）
- Python 3（仅宿主脚本读 `tauri.conf.json` 版本号）

## 一键出包

在仓库根目录：

```bash
./scripts/build-kylin-pks.sh
```

常用参数：

| 参数 | 含义 |
|------|------|
| `--clean` | 删除 `packaging/dist/pks/` 与 `packaging/.venv-pks/` 后重打 |
| `-h` / `--help` | 打印用法 |

脚本流程概要：

1. 读取 `apps/desktop/src-tauri/tauri.conf.json` 的 `version`
2. `docker build --platform=linux/arm64` → 镜像 `wenshutong-pks-builder:ubuntu22-arm64`
3. 容器内执行 `packaging/pks/build-inside.sh`（编译 Runtime、Tauri deb）
4. 组装 USB 分发目录

## 产物路径

```
packaging/dist/pks/wenshutong-pks-<version>-aarch64/
├── 文书通_<version>_aarch64.deb
├── install-offline.sh
├── deps.manifest
├── deps/              # 若有预下载 .deb
├── fixtures/          # 若 packaging/pks/fixtures 存在则自动拷入
└── README-安装说明.txt
```

版本示例：当前 `1.6.0` → `packaging/dist/pks/wenshutong-pks-1.6.0-aarch64/`。

构建成功时终端会打印：`USB bundle ready: .../wenshutong-pks-<version>-aarch64`。

## 验收样例材料

`./scripts/build-kylin-pks.sh` 组装 USB 包时，若存在 `packaging/pks/fixtures/`，会自动拷入分发目录的 `fixtures/`（无需手动 `cp`）。

| 文件 | 用途 |
|------|------|
| `fixtures/sample-format.docx` | 公文排版 B 档样例 |
| `fixtures/sample-proofread.docx` | 通篇校对 B 档样例 |

来源：`bundled/skills/government-document-format/fixtures/sample.docx`、`docs/superpowers/evals/fixtures/w1-proofread/数字化转型情况汇报-待校.docx`。

## U 盘与断网验收

1. **仅拷贝整个** `wenshutong-pks-<version>-aarch64/` **目录**到 U 盘（含 `.deb`、`install-offline.sh`、`fixtures/` 等全部内容）。
2. 在 **断网** 的验收机（银河麒麟 V10 SP1 · aarch64 · 已装 **WPS**）上，将目录拷到本地磁盘。
3. 进入该目录执行：`bash install-offline.sh`
4. 从应用菜单启动「文书通」，配置单位内网模型，按 [VERIFY-kylin-pks.md](./VERIFY-kylin-pks.md) 完成 B 档勾选。

**重要：** 验收机全程断网；不要在麒麟机上编译或拉依赖。缺库时按 `VERIFY-kylin-pks.md` 收集 `ldd`/日志，在构建侧回填 `packaging/pks/deps/` 后重跑 `./scripts/build-kylin-pks.sh`。

## 相关文档

| 文档 | 读者 |
|------|------|
| [VERIFY-kylin-pks.md](./VERIFY-kylin-pks.md) | 构建者 / 测试（B 档技术清单） |
| [验收清单-PKS-给非开发人员.md](./验收清单-PKS-给非开发人员.md) | 业务同事跟测 |
| [2026-08-11-kylin-pks-baseline-design.md](../docs/superpowers/specs/2026-08-11-kylin-pks-baseline-design.md) | 设计规格 §4 验收标准 |
