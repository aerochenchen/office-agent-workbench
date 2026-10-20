#!/usr/bin/env python3
"""生成《文书通（本地部署版）1.7.0 修改说明》Word 稿。

用法:
    runtime/.venv/bin/python scripts/build-1.7.0-audit-response-docx.py
"""
from __future__ import annotations

import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
HELPERS = HERE / "build-security-review-docx.py"
ROOT = HERE.parent
PRODUCT = "文书通"
VERSION = "1.7.0"
REPORT_DATE = "2026年10月20日"
OUT = ROOT / "docs" / "文书通-1.7.0-审查问题修改说明.docx"


def load_helpers():
    return runpy.run_path(str(HELPERS))


def build(out: Path) -> None:
    h = load_helpers()
    doc = h["new_doc"]()
    add_title = h["add_title"]
    add_meta = h["add_meta"]
    add_h1 = h["add_h1"]
    add_h2 = h["add_h2"]
    add_body = h["add_body"]
    add_table = h["add_table"]
    add_sign_line = h["add_sign_line"]

    add_title(doc, f"{PRODUCT}（本地部署版）{VERSION} 修改说明")
    add_meta(
        doc,
        f"对照两份安全审计报告　　软件版本 {VERSION}　　{REPORT_DATE}",
    )
    add_body(
        doc,
        "对照报告一：《文书通_本地部署_1.6.0 安全审计报告》第三版（原审）。"
        "对照报告二：《【1020】文书通_本地部署_1.6.0 安全审计报告》第三轮复审。"
        "本稿是开发方修改说明，不替代审查单位的正式复测意见。",
    )
    add_body(
        doc,
        "软件版本 1.7.0，回应第三轮「三轮包同为 1.6.0、只能靠哈希区分」。"
        "送审范围为内网本地部署安装包。"
        "1.7.0 本地部署 NSIS 包待构建后回填文件名与 SHA256，请以当场交付的哈希为准。",
    )
    add_body(
        doc,
        "第三轮指出：上一轮整改报告有材料与实物不符、L-02 写成已关闭、M-06 写成已落地。"
        "1.7.0 按该建议改表述、升版本；高危项保持第三轮已关闭的结论，不把未做的事写成已修。",
    )

    add_h1(doc, "1 总表")
    add_body(doc, "按两份报告里的原条目回应。不另编新编号。")
    add_table(
        doc,
        ["报告条目", "第三轮结论", "1.7.0"],
        [
            [
                "H-01 鉴权与档位",
                "已关闭",
                "保持。无令牌自行生成并强制 Bearer；封装的 local 档位不能被环境变量降级",
            ],
            [
                "H-02 Windows 脚本隔离",
                "进程内层已关闭",
                "保持。隔离不可用则拒绝执行。Windows 走 AppContainer（产品路径）",
            ],
            [
                "L-03 打开旧版 Word 宏",
                "已关闭",
                "保持。Open 前 AutomationSecurity = 3",
            ],
            [
                "M-03 WebView2",
                "已关闭（151.0.4129.107）",
                "保持。内网不启用自动更新，按 CVE 换安装包",
            ],
            [
                "M-04 技能校验白名单",
                "已关闭",
                "保持。导入默认拒绝；含进程/网络模块的包不能安装。安装技能仍可用",
            ],
            [
                "M-05 脚本参数根目录",
                "已关闭",
                "保持",
            ],
            [
                "L-02 任意 IP 字面量",
                "未关闭；要求更正表述",
                "按审查建议更正表述，实现不改：拒绝公网域名；IP 字面量一律放行",
            ],
            [
                "M-01 未签名",
                "残留",
                "本 NSIS 包仍不签名。完整性以当场 SHA256 为准",
            ],
            [
                "M-02 构建路径与 devUrl",
                "未整改",
                "如实未改：构建机绝对路径仍在；一处 http://localhost:1420 来自 devUrl，不是可调用接口",
            ],
            [
                "M-06 NOTICE / SBOM",
                "未落地",
                "如实未落地。1.7.0 安装包产出前不声称包内已附 CycloneDX",
            ],
            [
                "L-01 端口与令牌",
                "部分关闭（/shutdown 已鉴权）",
                "保持。默认 127.0.0.1:8765；无令牌不能关机",
            ],
            [
                "图片通道 workspace_look",
                "实现合格；扩大出站面，须单位知悉",
                "功能保留。路径受工作区约束；每张 ≤8MB、每轮最多 4 张；受权限闸门约束。公网域名被拒",
            ],
            [
                "提示词改为直接读文件夹",
                "审查写明不是代码缺陷",
                "不改。打开的文件夹就是办理范围",
            ],
            [
                "Office 内嵌图先解压再查大小",
                "低危建议",
                "不改。属本机格式处理",
            ],
            [
                "送审材料与哈希不一致",
                "材料问题（优先）",
                "1.7.0 报告、安装包、哈希同一批次。不用 1.6.0 旧哈希判定本版本",
            ],
        ],
        col_widths=[4.4, 4.8, 6.6],
    )

    add_h1(doc, "2 按第三轮「应予修正的材料问题」逐条")
    add_body(doc, "第三轮 6.3 建议 1 至 5 是复查优先项。本版本按下列履行。")
    add_h2(doc, "2.1 材料与实物一致")
    add_body(
        doc,
        "本说明不预填旧哈希。送审时文件名、大小、SHA256 与安装包为同一次构建。"
        "版本号改为 1.7.0，避免再与 1.6.0 三轮包混淆。",
    )
    add_h2(doc, "2.2 L-02 表述")
    add_body(
        doc,
        "采用审查原文：拒绝公网域名与解析为公网地址的域名；IP 字面量一律放行，"
        "以支持非 RFC1918 专网；该取舍由使用单位评估。"
        "终端能访问哪些 IP，由单位安全软件和网络权限审查，产品不二次拦截。"
        "请勿再用「填写公网 IP 应失败」或「已关闭、只允许回环/私网」核对本项。",
    )
    add_h2(doc, "2.3 M-06 表述")
    add_body(doc, "改为「未落地」。不以仓库脚本代替包内核验。")
    add_h2(doc, "2.4 M-02 表述")
    add_body(
        doc,
        "构成残留的是构建机绝对路径，以及 tauri.conf.json 的 devUrl（http://localhost:1420）。"
        "1.7.0 未剥离。",
    )
    add_h2(doc, "2.5 版本号")
    add_body(doc, "本包为 1.7.0。")

    add_h1(doc, "3 已关闭项（第三轮已认定，1.7.0 未回退）")
    add_body(
        doc,
        "H-01、H-02（进程内隔离）、L-03、M-03、M-04、M-05：与第三轮结论一致。"
        "1.7.0 未拆除鉴权、隔离 fail-closed、禁宏、WebView2 151、技能导入白名单、脚本参数根目录校验。",
    )
    add_body(
        doc,
        "恶意性结论沿用第三轮：未发现后门、窃密或远控；安装期无外联、无自启动。"
        "第三轮已代为完成出站与自启动复核，可引用该结果。",
    )

    add_h1(doc, "4 第三轮新增功能观察")
    add_h2(doc, "4.1 看图")
    add_body(
        doc,
        "第三轮认定路径越界被拒、体积与数量有上限、工具受闸门约束、会话库与审计不含图片字节，实现合格。"
        "这是办理功能，1.7.0 保留。"
        "本地部署拒绝公网云厂商域名；填 IP 时能否出站，由内网策略决定。",
    )
    add_h2(doc, "4.2 读文件夹材料")
    add_body(
        doc,
        "第三轮写明「不是代码缺陷，而是易用性与数据面的取舍」。"
        "1.7.0 不改提示词、不改读取闸门。打开的文件夹就是办理范围；"
        "谨慎/标准模式下写入与跑脚本仍要确认。",
    )
    add_h2(doc, "4.3 Office 内嵌图内存")
    add_body(doc, "低危工程建议，1.7.0 不改，不作为准入条件。")

    add_h1(doc, "5 书面标注（第三轮建议 11）")
    add_body(
        doc,
        "图形界面执行技能脚本时启用进程内隔离。"
        "命令行 --run-script 是调试入口，不启用该隔离，不能当作受保护入口。"
        "普通办公用户不使用该入口。",
    )
    add_body(
        doc,
        "第三轮其余工程建议（AppContainer 装包抽测、图片纳入不可信数据包裹、"
        "解压前先读 zip 大小、/chat 准备阶段诊断日志）本版本未作为关闭项承诺。",
    )

    add_h1(doc, "6 使用单位侧")
    add_body(doc, "一、安装介质在内网保管，安装前核对当场 SHA256。")
    add_body(
        doc,
        "二、模型填内网或本机地址。公网云厂商域名会被拒绝；专网模型直接填 IP。",
    )
    add_body(doc, "三、终端不出公网，或由单位防火墙限制出站。")
    add_body(doc, "四、技能安装走导入白名单；脚本执行受隔离约束。")

    add_sign_line(doc, "编制：开发方", f"日期：{REPORT_DATE}")

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))


def main() -> int:
    build(OUT)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
