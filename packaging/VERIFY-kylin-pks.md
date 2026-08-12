# 银河麒麟 PKS 离线包验证清单（B 档）

在 **断网** 目标机（银河麒麟桌面 **V10 SP1** · **aarch64** · 已装 **WPS** `/usr/bin/wps`）上验收 `wenshutong-pks-*-aarch64/` 分发目录。

设计规格 §4 六条用例 + 健康检查与失败采集。非开发人员可读版见 [验收清单-PKS-给非开发人员.md](./验收清单-PKS-给非开发人员.md)。

## 构建机（有网 Mac）

- [ ] Docker Desktop 可用，能跑 `linux/arm64` 容器
- [ ] 仓库根目录：`./scripts/build-kylin-pks.sh`（可选 `--clean`）
- [ ] 产物目录存在：`packaging/dist/pks/wenshutong-pks-<version>-aarch64/`
- [ ] 目录内含主包 `文书通_*_aarch64.deb`、`install-offline.sh`、`deps.manifest`
- [ ] 已将 `packaging/pks/fixtures/` 拷入分发目录的 `fixtures/`（见 [README-kylin-pks.md](./README-kylin-pks.md)）
- [ ] 整目录拷入 U 盘，准备断网验收

## 验收样例路径

验收前，将 U 盘内 `fixtures/` 复制到工作区测试文件夹（例如 `~/文书通测试/`）：

| 样例 | 路径（分发包内） | 用途 |
|------|------------------|------|
| 排版 | `fixtures/sample-format.docx` | 用例 5 · 公文排版 |
| 校对 | `fixtures/sample-proofread.docx` | 用例 6 · 通篇校对 |

## B 档验收（规格 §4）

### 1 · 断网安装

- [ ] 验收机 **已断网**（拔网线 / 关 Wi‑Fi）
- [ ] 在解压后的分发目录执行：`bash install-offline.sh`
- [ ] `dpkg` 安装成功，无致命报错（缺库时记录包名，见文末「失败采集」）
- [ ] 应用菜单 / 桌面可找到并启动 **「文书通」**

### 2 · 冷启动

- [ ] 双击启动后 **主窗口出现**（非长时间空白或秒退）
- [ ] Runtime 就绪，满足 **其一**：
  - [ ] 终端：`curl -sf http://127.0.0.1:8765/health` 返回含 `"ok":true` 的 JSON
  - [ ] 或 UI 显示 Runtime / 服务 **在线**（验收机若无 `curl`，以 UI 为准）
- [ ] `~/.office-agent/` 已创建

### 3 · 模型配置

- [ ] 打开设置，可填写并保存 **api_base / api_key / model / allowed_hosts**
- [ ] 保存后密钥不以明文长串暴露（可显示「已设置」等）
- [ ] **无内网模型** 时：发起对话有 **明确不可达/配置错误提示**，应用 **不崩溃**
- [ ] （可选，有内网模型时）发送一条简单对话，有正常回复

### 4 · 工作区

- [ ] 通过「打开工作区 / 选择文件夹」选定含样例 docx 的目录（如 `~/文书通测试/`）
- [ ] 工作区路径显示正确；后续工具读写落在该目录下（如 `工作成果/`）

### 5 · 公文排版 + WPS

准备：工作区中已有 `sample-format.docx`（或从 `fixtures/` 拷入）。

- [ ] 右侧技能栏可见 **「公文排版」**（或等价名称）且已启用
- [ ] 在对话中请其对 `sample-format.docx` 做公文排版（可附该文件）
- [ ] 任务结束，有结果说明或产出路径
- [ ] 产出文件（如带 `_formatted` 后缀）存在
- [ ] 用 **WPS** 打开产出文件：**能正常打开**，主流程成功（B 档不要求版式像素级一致）

### 6 · 通篇校对 + WPS

准备：工作区中已有 `sample-proofread.docx`。

- [ ] 右侧技能栏可见 **「通篇校对」**（或等价名称）且已启用
- [ ] 在对话中请其对 `sample-proofread.docx` 做通篇校对
- [ ] 任务结束，有校对结果或产出路径
- [ ] 用 **WPS** 打开结果文件或查看工作区内的校对产出：**能正常查看**

## 技能与范围说明

- [ ] 预置轻量 Skill 已 seed（至少含 `government-document-format`、`doc-proofread`）
- [ ] 本版 **不要求** 写作 RAG、Torch、OFD、国密签章
- [ ] 完整「聪明多轮对话」若现场无内网模型，可用例 3 降级标准；有模型时再补测

## 失败采集（任一条未通过时）

在验收机收集以下信息，U 盘带回开发侧：

```bash
# 主程序动态库（路径按实际安装调整，常见在 /opt/ 或 /usr/bin/）
ldd "$(which 文书通 2>/dev/null || echo /usr/bin/文书通)" 2>&1 | tee /tmp/wenshutong-ldd.txt

# 系统 / 桌面日志（择可用者）
journalctl -b --no-pager -n 200 2>/dev/null | tee /tmp/wenshutong-journal.txt
# 或 Kylin 用户会话日志、~/.local/share/ 下应用日志

# Runtime sidecar 错误日志
cat /tmp/office-agent-runtime.err.log 2>/dev/null | tee /tmp/wenshutong-runtime.err.txt
```

另附：失败步骤编号、屏幕截图、`install-offline.sh` 完整终端输出、缺库包名（若有）。

缺系统库时：将包名写入 `packaging/pks/deps.manifest`，离线 `.deb` 放入 `packaging/pks/deps/`，在 Mac 上重跑 `./scripts/build-kylin-pks.sh`，再 U 盘复测。

## 过关标准

规格 §4 **六条全部勾选** + 冷启动 health/UI 就绪 → B 档通过。单条失败不算项目终止，回填 deps 或修代码后复测该条即可。
