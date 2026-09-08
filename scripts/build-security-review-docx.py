#!/usr/bin/env python3
"""生成文书通网信源代码安全检测送审 Word 套件。

用法:
    python3 scripts/build-security-review-docx.py

可选:
    --hash-file PATH   读取快照 SHA-256（默认 packaging/dist/security-review/SHA256.txt）
    --out-dir PATH     输出目录（默认 docs/网信送审物料）

依赖 python-docx。优先使用 runtime/.venv。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
except ImportError:
    sys.exit("缺少依赖 python-docx，请先运行: runtime/.venv/bin/pip install python-docx")

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "文书通"
VERSION = "1.5.0"
SNAPSHOT_NAME = f"{PRODUCT}-{VERSION}-源代码检测快照.zip"
BLACK = RGBColor(0x00, 0x00, 0x00)
GRAY = RGBColor(0x33, 0x33, 0x33)

FONT_HEI = "黑体"
FONT_FANG = "仿宋_GB2312"
FONT_KAI = "楷体_GB2312"
FONT_SONG = "宋体"


def set_run(run, cn_font: str, size_pt: float, *, bold: bool = False, color=BLACK) -> None:
    run.bold = bold
    run.font.size = Pt(size_pt)
    run.font.color.rgb = color
    run.font.name = cn_font
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), cn_font)
    rfonts.set(qn("w:hAnsi"), cn_font)
    rfonts.set(qn("w:eastAsia"), cn_font)
    rfonts.set(qn("w:cs"), cn_font)


def set_page(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.7)
    section.bottom_margin = Cm(3.5)
    section.left_margin = Cm(2.8)
    section.right_margin = Cm(2.6)


def _format_para(p, *, first_indent=None, align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=0, space_after=0):
    pf = p.paragraph_format
    pf.alignment = align
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(29)
    if first_indent is not None:
        pf.first_line_indent = first_indent
    pf.widow_control = True
    return p


def add_text(
    doc: Document,
    text: str,
    *,
    font=FONT_FANG,
    size=16,
    bold=False,
    align=WD_ALIGN_PARAGRAPH.JUSTIFY,
    first_indent=True,
    space_before=0,
    space_after=0,
):
    p = doc.add_paragraph()
    indent = Cm(0.74) if first_indent else None  # 约 2 个三号汉字
    _format_para(p, first_indent=indent, align=align, space_before=space_before, space_after=space_after)
    run = p.add_run(text)
    set_run(run, font, size, bold=bold)
    return p


def add_title(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    _format_para(p, first_indent=None, align=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=12)
    run = p.add_run(text)
    set_run(run, FONT_HEI, 22, bold=True)


def add_h1(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    _format_para(p, first_indent=None, align=WD_ALIGN_PARAGRAPH.LEFT, space_before=6, space_after=0)
    run = p.add_run(text)
    set_run(run, FONT_HEI, 16, bold=True)


def add_h2(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    _format_para(p, first_indent=None, align=WD_ALIGN_PARAGRAPH.LEFT, space_before=4, space_after=0)
    run = p.add_run(text)
    set_run(run, FONT_KAI, 16, bold=True)


def add_meta(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    _format_para(p, first_indent=None, align=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=6)
    run = p.add_run(text)
    set_run(run, FONT_KAI, 14, color=GRAY)


def add_body(doc: Document, text: str) -> None:
    add_text(doc, text, font=FONT_FANG, size=16, first_indent=True)


def add_center(doc: Document, text: str, *, font=FONT_FANG, size=16) -> None:
    add_text(doc, text, font=font, size=size, first_indent=False, align=WD_ALIGN_PARAGRAPH.CENTER)


def add_text_colored(
    doc: Document,
    text: str,
    *,
    font=FONT_KAI,
    size=14,
    first_indent=True,
    align=WD_ALIGN_PARAGRAPH.JUSTIFY,
    color=GRAY,
):
    p = doc.add_paragraph()
    indent = Cm(0.74) if first_indent else None
    _format_para(p, first_indent=indent, align=align)
    run = p.add_run(text)
    set_run(run, font, size, color=color)
    return p


def set_cell_border(cell, **kwargs) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), kwargs.get("val", "single"))
        element.set(qn("w:sz"), kwargs.get("sz", "8"))
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), kwargs.get("color", "000000"))
        tcBorders.append(element)
    tcPr.append(tcBorders)


def shade_cell(cell, fill: str = "F2F2F2") -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    shd.set(qn("w:val"), "clear")
    tcPr.append(shd)


def set_cell_text(cell, text: str, *, font=FONT_FANG, size=12, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    pf = p.paragraph_format
    pf.alignment = align
    pf.space_before = Pt(2)
    pf.space_after = Pt(2)
    pf.line_spacing = 1.15
    run = p.add_run(text)
    set_run(run, font, size, bold=bold)


def add_table(doc: Document, headers: list[str], rows: list[list[str]], *, col_widths: list[float] | None = None) -> None:
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        set_cell_text(cell, h, font=FONT_HEI, size=12, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        shade_cell(cell, "E7E6E6")
        set_cell_border(cell)
    for r_idx, row in enumerate(rows, start=1):
        for c_idx, val in enumerate(row):
            cell = table.rows[r_idx].cells[c_idx]
            set_cell_text(cell, val, font=FONT_FANG, size=12)
            set_cell_border(cell)
    if col_widths:
        for row in table.rows:
            for i, w in enumerate(col_widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph()


def add_sign_line(doc: Document, left: str, right: str) -> None:
    p = doc.add_paragraph()
    _format_para(p, first_indent=None, align=WD_ALIGN_PARAGRAPH.LEFT, space_before=12, space_after=0)
    run = p.add_run(f"{left}                  {right}")
    set_run(run, FONT_FANG, 16)


def add_blank_sign_block(doc: Document, party: str) -> None:
    add_body(doc, f"{party}（签字）：____________________")
    add_body(doc, "职务 / 部门：____________________")
    add_body(doc, "日期：________年____月____日")


def new_doc() -> Document:
    doc = Document()
    set_page(doc)
    return doc


def read_hash(hash_file: Path) -> str:
    if hash_file.is_file():
        text = hash_file.read_text(encoding="utf-8").strip().split()[0]
        if text:
            return text
    return "（正式值以当场打包为准；下方「填写示例」在生成快照后回填）"


def build_plan(out: Path) -> None:
    doc = new_doc()
    add_title(doc, f"关于配合开展{PRODUCT}源代码安全检测的工作方案")
    add_meta(doc, f"软件版本：{VERSION}　　文稿性质：工作文稿（非正式发文）　　日期：2026年8月19日")
    add_body(doc, "送审部门：____________________　　联系人：____________________　　电话：____________________")
    add_body(doc, "检测部门：____________________（本单位网络信息安全部门）　　检测地点：____________________")

    add_h1(doc, "一、目的")
    add_body(
        doc,
        f"为落实本单位网络安全与数据安全管理要求，拟将{PRODUCT}（桌面端办公文书智能体，版本{VERSION}）交付网络信息安全部门进行源代码安全检测。"
        "检测应当完整、可复核；同时控制源代码副本扩散，避免产品实现与未公开技能细节形成可带走、可再分发的拷贝。",
    )
    add_body(
        doc,
        "本方案作为双方对齐口径的工作文稿，不作为等保测评、密评或第三方渗透测试结论，亦不替代检测部门出具的正式意见。",
    )

    add_h1(doc, "二、检测对象与安全定位")
    add_body(
        doc,
        f"{PRODUCT}为安装在办公终端上的桌面应用（Tauri 2 壳 + Python Runtime），用于在用户选定的本机文件夹内完成文书辅助。"
        "当前版本不设开发者自建用户账号与云端用户数据库，不包含将对话、文档或设备标识上报至开发者分析/广告/崩溃统计服务器的功能。"
        "为完成智能任务，应用会将用户指令及按任务读取的文档片段发送至用户自行配置的大模型服务接口（api_base），并经主机白名单校验。",
    )
    add_body(
        doc,
        "数据合规与安全检测的重心是：是否存在未声明外联或后门、公文与凭据是否离开本机或落入明文日志、第三方组件是否存在已知漏洞、工作区沙箱与权限控制是否有效。"
        "业务技能文案、排版细则与产品规划不属于本次检测必需范围。",
    )

    add_h1(doc, "三、原则")
    add_body(doc, "（一）检测完整发生。允许静态代码扫描、依赖漏洞分析、安装包联网行为监测，以及对安全相关源码的现场审阅。")
    add_body(doc, "（二）源码不扩散。源代码不以可复制副本离开约定场所。优先在指定现场机检测；检测结束销毁副本，检测部门只归档报告、文件哈希与双方签字单。")
    add_body(doc, "（三）不对抗检测。不采用混淆、加密源码、抽空安全相关模块等方式送检。已知残留风险在技术附件中主动说明。")
    add_body(doc, "（四）范围对等。交与发版安装包对应的源码快照，不交开发机完整仓库、依赖安装目录、真实密钥与测试公文。")

    add_h1(doc, "四、建议检测方式（优先现场）")
    add_h2(doc, "（一）首选：现场检测")
    add_body(
        doc,
        "在网信指定房间或送审方提供的专用机上进行。机器可断外网或仅通内网扫描平台；禁止将源码拷入个人U盘或个人邮箱。"
        "双方在场运行部门指定的代码安全检测工具与依赖扫描，必要时抽审安全相关路径。检测结束后共同确认报告，按确认单销毁源码副本。",
    )
    add_h2(doc, "（二）备选：部门扫描平台限期存放")
    add_body(
        doc,
        "若必须上传至部门扫描平台，建议书面约定：权限仅限本次检测账号、禁止下载源码包、检测完成后限期删除并出具销毁记录。"
        "该方式仍形成平台侧副本，保护强度低于现场检测，须经双方同意后采用。",
    )

    add_h1(doc, "五、送交材料")
    add_body(doc, "本次送审材料分为文稿套件与源码检测快照两类。文稿可打印签字；快照仅在约定场所使用。")
    add_table(
        doc,
        ["序号", "材料", "形态", "用途"],
        [
            ["1", "本工作方案", "Word", "对齐检测目的、原则、流程与职责"],
            ["2", "现场检测与销毁确认单", "Word", "记录版本、哈希、存放与销毁，双方签字"],
            ["3", "保密与使用目的限定条款（草稿）", "Word", "供检测部门改定或盖章"],
            ["4", "技术附件（范围、导读、组件与已知风险）", "Word", "现场扫描与抽审时对照"],
            ["5", f"{SNAPSHOT_NAME}", "zip 快照", "供工具扫描；不含 git 历史与依赖安装目录"],
        ],
        col_widths=[1.5, 5.5, 2.2, 6.4],
    )
    add_body(
        doc,
        "快照由脚本 scripts/pack-security-review-snapshot.sh 从当前发版树生成，并计算 SHA-256。"
        "纳入与排除范围见技术附件。快照根目录含批次水印文件 SECURITY_REVIEW_WATERMARK.txt，仅标识本次检测用途，不干扰扫描。",
    )

    add_h1(doc, "六、双方职责")
    add_table(
        doc,
        ["角色", "职责"],
        [
            [
                "送审方",
                "提供与版本对应的快照与文稿；到场配合；对扫描误报提供设计说明；不提供真实密钥与公文样例；检测结束后参与销毁确认。",
            ],
            [
                "检测方",
                "在约定场所完成检测；不将源码用于复制产品或二次分发；对外只引用检测结论；归档报告与哈希，不归档可运行源码树。",
            ],
        ],
        col_widths=[3.0, 12.6],
    )

    add_h1(doc, "七、建议日程")
    add_table(
        doc,
        ["步骤", "工作内容", "产出"],
        [
            ["1", "材料交接：核对应版本号、快照文件名与 SHA-256", "确认单「交接」栏签字"],
            ["2", "工具扫描：SAST、依赖 CVE；必要时安装包抓包看外联", "扫描原始报告"],
            ["3", "对照技术附件消项：区分设计行为、误报与需整改项", "问题清单"],
            ["4", "销毁源码副本（现场删除/平台删除），只保留报告与哈希", "确认单「销毁」栏签字"],
        ],
        col_widths=[1.5, 8.5, 5.6],
    )

    add_h1(doc, "八、需要双方知悉的已知项")
    add_body(
        doc,
        "开发方 2026 年 7 月内部安全自评估结论为：未发现不可接受的安全阻断项，建议在满足部署要求前提下开展有限范围内部试点。"
        "该结论为开发方自评，不替代本次网信检测。代码默认模型地址指向公网 DeepSeek，试点与内网交付必须改为单位指定的内网或本机模型地址。"
        "脚本进程的网络隔离依赖操作系统级策略，无法仅靠应用层保证。详见技术附件，请检测时作为已知项核验，而非事后被动解释。",
    )

    add_h1(doc, "九、附则")
    add_body(doc, "单位名称、联系人、检测地点等要素由送审方在打印前手填。本稿不使用发文字号，不作为正式公文红头文件。")
    add_body(doc, "如检测部门对范围、场所或工具另有规定，以检测部门书面要求为准，可在确认单「备注」栏载明。")

    add_sign_line(doc, "送审方（签字）：____________", "检测方（签字）：____________")
    add_sign_line(doc, "日期：______年____月____日", "日期：______年____月____日")
    doc.save(out)


def build_confirmation(out: Path, sha256: str, example: bool) -> None:
    doc = new_doc()
    add_title(doc, f"{PRODUCT}源代码现场检测与销毁确认单")
    add_meta(doc, f"与工作方案配套　　版本 {VERSION}　　一式两份，双方各执一份")

    add_h1(doc, "一、交接信息")
    hash_note = sha256
    if example and not sha256.startswith("（"):
        hash_note = sha256
    add_table(
        doc,
        ["项目", "内容（手填或据实填写）"],
        [
            ["软件名称", PRODUCT],
            ["软件版本", VERSION],
            ["快照文件名", SNAPSHOT_NAME],
            ["SHA-256", hash_note],
            ["快照存放位置", "____________________（现场机路径 / 平台任务号）"],
            ["检测起止时间", "______年____月____日 至 ______年____月____日"],
            ["检测工具（如有）", "____________________"],
            ["送审部门 / 联系人", "____________________"],
            ["检测部门 / 联系人", "____________________"],
        ],
        col_widths=[4.0, 11.6],
    )
    if example and sha256 and not sha256.startswith("（"):
        add_text_colored(
            doc,
            "上表 SHA-256 为本次预打包填写示例，便于核对脚本产出。正式送审须在检测现场重新打包或核验同一文件后再签字，不得沿用过期示例。",
            first_indent=True,
        )
    else:
        add_text_colored(
            doc,
            "请先运行 scripts/pack-security-review-snapshot.sh 生成快照与 SHA256.txt，再重新生成本确认单以回填哈希；或在现场打包后手写填入。",
            first_indent=True,
        )

    add_h1(doc, "二、检测场所与权限")
    add_body(doc, "检测场所：□ 网信指定现场机　　□ 送审方专用机　　□ 部门扫描平台（限期存放）　　□ 其他：__________")
    add_body(doc, "源码副本是否允许带离现场：□ 否（默认）　　□ 是（须在备注说明批准人）")
    add_body(doc, "扫描平台是否禁止下载源码包：□ 是　　□ 否　　□ 不适用")

    add_h1(doc, "三、交接确认")
    add_body(
        doc,
        "送审方确认：所交快照与上表版本、文件名、哈希一致；快照中不含真实业务密钥、本单位公文原文及开发者云账号。"
        "检测方确认：已收到上述快照，用途仅限于本次源代码安全检测，不用于复制产品、二次分发或无关开发。",
    )
    add_blank_sign_block(doc, "送审方交接人")
    add_blank_sign_block(doc, "检测方接收人")

    add_h1(doc, "四、销毁确认")
    add_body(doc, "销毁方式：□ 现场安全删除并清空回收站　　□ 平台侧删除并出具记录　　□ 物理销毁介质　　□ 其他：__________")
    add_body(doc, "销毁日期：________年____月____日　　监销人：____________________")
    add_body(
        doc,
        "销毁后检测方仅保留：检测报告、本确认单、快照文件名与 SHA-256。不得继续持有可解压的源码树或安装有源码的检测机镜像（除非另有书面批准）。",
    )
    add_blank_sign_block(doc, "送审方监销人")
    add_blank_sign_block(doc, "检测方监销人")

    add_h1(doc, "五、备注")
    add_body(doc, "________________________________________________________________")
    add_body(doc, "________________________________________________________________")
    doc.save(out)


def build_nda(out: Path) -> None:
    doc = new_doc()
    add_title(doc, f"{PRODUCT}源代码安全检测保密与使用目的限定条款")
    add_meta(doc, "草稿，供网络信息安全部门改定或作为内部工作约定附件　　2026年8月19日")

    add_body(doc, "甲方（送审方）：____________________")
    add_body(doc, "乙方（检测方）：____________________（本单位网络信息安全部门）")
    add_body(
        doc,
        f"为配合对{PRODUCT}（版本{VERSION}）开展源代码安全检测，双方就源码、快照、扫描中间结果的使用与保密达成如下条款。本稿为工作草稿，最终文本以检测部门审定或单位合同管理部门意见为准。",
    )

    add_h1(doc, "一、使用目的")
    add_body(
        doc,
        "乙方接触甲方提供的源代码快照、技术附件及现场说明，仅用于本次源代码安全检测、漏洞与合规风险研判、出具检测意见。"
        "不得用于开发与本软件功能相同或实质相似的产品，不得向本单位检测任务无关人员提供可复制副本。",
    )

    add_h1(doc, "二、保密范围")
    add_body(doc, "保密信息包括但不限于：源代码快照、目录结构与实现细节、未公开技能与规则、扫描原始报告中的业务逻辑摘录、现场口头说明。")
    add_body(doc, "检测结论（通过 / 整改后复测 / 不通过）及不涉及实现细节的风险类型描述，可按单位内部管理要求上报，不在本条款禁止之列。")

    add_h1(doc, "三、副本控制")
    add_body(doc, "源码快照仅存放于双方书面确认的现场机或扫描平台。禁止外传、再分发；禁止通过即时通讯、个人邮箱、个人网盘或私人存储设备带走源码。")
    add_body(doc, "检测结束后，乙方应按确认单约定销毁源码副本，并签字确认。销毁后不得故意保留解压目录、虚拟机快照中的源码树。")

    add_h1(doc, "四、禁止事项")
    add_body(doc, "未经甲方书面同意，乙方不得：再编译后对外分发；将快照提供给单位以外的第三方（含外部厂商，除非本单位另有采购检测合同并同等约束）；在公开场合展示源码。")

    add_h1(doc, "五、期限")
    add_body(doc, "保密义务自接触源码之日起生效，至源码公开或甲方书面解除之日止；若单位另有保密期限规定，从其规定。检测任务结束后，使用目的即告完成，不得继续持有源码。")

    add_h1(doc, "六、其他")
    add_body(doc, "本条款与《现场检测与销毁确认单》一并使用。确认单中的版本、哈希与销毁记录是履行本条款的证据。")
    add_body(doc, "如与本单位已生效的保密规定冲突，以更严格者为准。")

    add_sign_line(doc, "甲方（签字）：____________", "乙方（签字）：____________")
    add_sign_line(doc, "日期：______年____月____日", "日期：______年____月____日")
    doc.save(out)


def build_technical(out: Path) -> None:
    doc = new_doc()
    add_title(doc, f"{PRODUCT}源代码安全检测技术附件")
    add_meta(doc, f"范围、安全路径导读、开源组件摘要与已知风险　　版本 {VERSION}")
    add_text_colored(
        doc,
        "本附件内容摘自开发方已有材料（安全自评估报告 2026-07-31、数据类型清单、隐私政策、仓库根 NOTICE），供检测对照。"
        "不替代网信部门检测结论。本稿不是等级保护测评、密码应用安全性评估或商用密码认证的结论。",
        first_indent=True,
    )

    add_h1(doc, "一、检测快照范围")
    add_h2(doc, "（一）纳入")
    add_table(
        doc,
        ["路径", "说明"],
        [
            ["runtime/src/office_agent/", "Python Runtime 应用源码（安全控制主要在此）"],
            ["runtime/pyproject.toml、requirements.txt", "Python 直接依赖声明"],
            ["apps/desktop/", "桌面壳（前端与 Tauri）；不含 node_modules 与 Rust target"],
            ["apps/desktop/package.json、package-lock.json", "前端依赖锁定"],
            ["apps/desktop/src-tauri/Cargo.toml、Cargo.lock", "Rust 壳依赖锁定"],
            ["bundled/skills/", "随安装包分发的技能（含脚本，属运行时能力）"],
            ["NOTICE", "第三方组件与许可证清单（随安装包分发）"],
            ["SECURITY_REVIEW_WATERMARK.txt", "本批次水印，标明仅供本次检测"],
        ],
        col_widths=[7.2, 8.4],
    )
    add_h2(doc, "（二）排除（有意不交）")
    add_table(
        doc,
        ["路径或类别", "原因"],
        [
            [".git 及完整历史", "可能含已删文件与历史调试信息；检测以发版快照为准"],
            ["runtime/.venv、packaging/.venv-pks 等", "第三方安装树，不是本产品源码；用锁文件做 SCA"],
            ["node_modules、src-tauri/target、dist", "体积大且为构建产物 / 依赖"],
            ["src-tauri/resources/runtime", "PyInstaller 打包的 sidecar，属第三方二进制而非源码"],
            ["src-tauri/embed 与 .provisionprofile", "应用商店签名描述文件，不属于源码检测范围"],
            [".env、真实 api_key、内网地址、测试公文", "避免检测过程引入新的泄密面"],
            ["optional-skills 下模型权重", "大文件且非本次源码审核对象"],
            ["产品规划、未发布文档、宣传材料", "与漏洞检测无关"],
        ],
        col_widths=[7.2, 8.4],
    )
    add_body(
        doc,
        f"现场请使用 {SNAPSHOT_NAME}，并以 SHA-256 核验完整性。不要用开发人员笔记本上的工作副本替代快照。",
    )

    add_h1(doc, "二、架构与数据流（检测时看边界）")
    add_body(
        doc,
        "用户工作区文件夹由 Runtime 在沙箱内读写；对话与按任务读取的文档片段经 Model Gateway 发往配置的 api_base（须在 allowed_hosts 内）；"
        "配置、会话、审计落在本机用户数据目录（默认 ~/.office-agent 或 OFFICE_AGENT_DATA），工作区文档不为此复制到开发者服务器。"
        "当前产品无开发者自建后端。",
    )
    add_body(
        doc,
        "会离开本机的数据：用户指令、多轮对话、为完成任务读取的文档或检索片段。不会由本应用主动上传至开发者分析或广告服务。",
    )

    add_h1(doc, "三、安全相关源码路径导读")
    add_body(doc, "建议工具全量扫描快照后，人工抽审优先阅读下列文件，无需通读技能文案与排版规则。")
    add_table(
        doc,
        ["关注点", "路径", "阅读提示"],
        [
            [
                "外联与白名单",
                "runtime/src/office_agent/gateway.py\nruntime/src/office_agent/config.py",
                "模型请求是否仅允许 allowed_hosts；白名单如何随 api_base 合并。",
            ],
            [
                "默认配置与监听",
                "runtime/src/office_agent/app.py\nruntime/src/office_agent/__main__.py",
                "DEFAULT_CONFIG 默认 api_base 为 https://api.deepseek.com；非回环绑定且无 token 时拒绝启动；CORS 与 /shutdown 本机约束。",
            ],
            [
                "本机鉴权",
                "runtime/src/office_agent/auth.py",
                "可选 OFFICE_AGENT_API_TOKEN；本地 HTTP 接口访问控制。",
            ],
            [
                "审计脱敏",
                "runtime/src/office_agent/audit.py",
                "content / api_key / token / password 等是否脱敏，避免审计库成为公文明文池。",
            ],
            [
                "工作区沙箱",
                "runtime/src/office_agent/workspace.py\nruntime/src/office_agent/tools.py",
                "路径是否限制在选定文件夹；越界写入是否被拦截。",
            ],
            [
                "脚本策略",
                "runtime/src/office_agent/script_policy.py",
                "脚本环境是否剥离 TOKEN/KEY 等凭据；网络隔离是否仅为软约束。",
            ],
            [
                "权限确认",
                "runtime/src/office_agent/permissions.py",
                "谨慎 / 标准 / 信任文件夹三档；高危工具是否需人工确认。",
            ],
            [
                "技能校验",
                "runtime/src/office_agent/skill_validate.py\nruntime/src/office_agent/skills.py",
                "技能包结构校验、Zip Slip、脚本 import 限制及其残留绕过面。",
            ],
            [
                "桌面能力",
                "apps/desktop/src-tauri/capabilities/default.json\napps/desktop/src-tauri/tauri.conf.json",
                "opener 路径范围、CSP 等壳层权限是否过宽。",
            ],
        ],
        col_widths=[3.2, 6.2, 6.2],
    )

    add_h1(doc, "四、开源组件摘要（SBOM）")
    add_body(
        doc,
        "完整第三方清单以快照内 NOTICE 为准（该文件随安装包分发）。NOTICE 现网副本生成时间为 2026-07-25，其中含开发依赖且可能未列入此后新增的直接依赖 pdfplumber。"
        "建议检测以锁文件做 SCA，并以 pyproject.toml / package.json / Cargo.toml 的直接依赖为准。送审前如需最新 NOTICE，可在开发环境重跑 scripts/generate_notice.sh。",
    )
    add_h2(doc, "（一）Python Runtime 直接依赖（runtime/pyproject.toml）")
    add_table(
        doc,
        ["组件", "声明", "NOTICE 中许可证（若有）"],
        [
            ["fastapi", ">=0.115.0", "MIT"],
            ["uvicorn[standard]", ">=0.30.0", "BSD-3-Clause"],
            ["openai", ">=1.40.0", "Apache Software License"],
            ["pydantic", ">=2.7.0", "MIT"],
            ["pydantic-settings", ">=2.3.0", "MIT"],
            ["pyyaml", ">=6.0.1", "MIT License"],
            ["httpx", ">=0.27.0", "BSD License"],
            ["python-docx", ">=1.1.0", "MIT License"],
            ["python-pptx", ">=1.0.0", "MIT License"],
            ["openpyxl", ">=3.1.0", "MIT License"],
            ["xlrd", ">=2.0.1", "BSD License"],
            ["pdfplumber", ">=0.11.0", "NOTICE 生成时可能未列入，请以锁文件/安装元数据为准"],
        ],
        col_widths=[4.0, 3.5, 8.1],
    )
    add_h2(doc, "（二）桌面前端生产直接依赖（apps/desktop/package.json）")
    add_table(
        doc,
        ["组件", "声明", "NOTICE 许可证"],
        [
            ["@tauri-apps/api", "^2", "Apache-2.0 OR MIT"],
            ["@tauri-apps/plugin-dialog", "^2.7.2", "MIT OR Apache-2.0"],
            ["@tauri-apps/plugin-opener", "^2", "MIT OR Apache-2.0"],
            ["react / react-dom", "^19.1.0", "MIT"],
            ["react-markdown", "^10.1.0", "MIT"],
            ["remark-gfm", "^4.0.1", "MIT"],
        ],
        col_widths=[5.5, 3.2, 6.9],
    )
    add_h2(doc, "（三）Rust 壳直接依赖（apps/desktop/src-tauri/Cargo.toml）")
    add_table(
        doc,
        ["组件", "声明", "说明"],
        [
            ["tauri", "2", "桌面壳"],
            ["tauri-plugin-opener", "2", "打开本机路径"],
            ["tauri-plugin-dialog", "2", "文件夹选择等"],
            ["serde / serde_json", "1", "序列化"],
            ["uuid", "1（v4）", "本地标识"],
            ["windows-sys", "0.59（仅 Windows）", "Job Object，壳退出时结束 sidecar"],
        ],
        col_widths=[4.5, 4.0, 7.1],
    )
    add_body(
        doc,
        "许可证门禁：仓库 scripts/check_licenses.sh 与 check_licenses_npm.sh 阻止 GPL/AGPL 进入运行时依赖。自评记载 pip-audit 当时为 0 已知 CVE；npm audit 高危均在开发依赖、不进运行时。请以检测当日锁文件复扫为准。",
    )

    add_h1(doc, "五、已知残留风险（主动披露）")
    add_body(
        doc,
        "以下摘自《文书通安全自评估报告》（2026-07-31）。状态以该报告为准。请检测时核验是否仍存在，勿将「未写进本表」理解为不存在其他问题。",
    )
    add_table(
        doc,
        ["编号", "事项", "状态（自评）", "检测时建议"],
        [
            [
                "M6",
                "DEFAULT_CONFIG.api_base 默认为 https://api.deepseek.com（公网），allowed_hosts 含 api.deepseek.com。",
                "残留，部署必改",
                "核验安装后是否改为内网/本机模型；内网交付不得保留公网默认值。",
            ],
            [
                "H1",
                "脚本网络隔离为软约束，Python socket 等仍可能出站；Skill 禁网 AST 可被绕过。",
                "残留，需 OS 级收敛",
                "核验试点机防火墙/网络命名空间是否限制 runtime 出站。",
            ],
            [
                "M4",
                "config.json 明文保存模型 api_key。",
                "残留，部署收敛",
                "核验文件权限（仅运行用户可读）及 GET /config 是否脱敏。",
            ],
            [
                "M13",
                "无 Prompt 注入专用检测；恶意文档可能诱导高危工具调用。",
                "残留，权限门缓解",
                "核验默认权限模式及写文件/跑脚本是否需确认。",
            ],
            [
                "L14",
                "Tauri opener:allow-open-path 范围为 /**。",
                "自评可接受",
                "核验是否需用户点击才打开路径。",
            ],
            [
                "已封堵",
                "脚本继承敏感环境变量、审计记录公文全文、非回环绑定无 token 仍可启动。",
                "自评已封堵",
                "对照 script_policy / audit / __main__ 回归，勿当作未修问题重复定级。",
            ],
        ],
        col_widths=[2.2, 5.4, 3.2, 4.8],
    )
    add_body(
        doc,
        "自评建议的试点准入还包括：权限模式试点期谨慎、固定 loopback 监听、首批 3–5 人且非涉密公文。文件指纹使用 SHA1（doc_io.py）被 bandit 报为 High，自评说明用于去重而非密码学，属误报口径，请检测工具按用途研判。",
    )

    add_h1(doc, "六、建议检测部门执行的核验（可与工具扫描并行）")
    add_table(
        doc,
        ["项", "方法要点", "预期"],
        [
            ["白名单", "将 api_base 改为非白名单主机并发起对话", "拒绝连接"],
            ["绑定安全", "不以 token 绑定 0.0.0.0", "进程拒绝启动"],
            ["审计脱敏", "执行一次写入后查看审计库", "content 无公文全文"],
            ["外联监测", "安装包运行后抓包（配置内网模型时）", "无未声明域名"],
            ["依赖 CVE", "对锁文件做 SCA", "记录检测当日结果"],
        ],
        col_widths=[3.0, 7.6, 5.0],
    )

    add_h1(doc, "七、声明")
    add_body(
        doc,
        f"本技术附件与{PRODUCT} {VERSION} 源码树对应关系以当场哈希为准。开发方自评使用过辅助分析工具，关键控制以源码与复现命令为准。"
        "本附件未完成、也不代替等级保护测评、密码应用安全性评估或商用密码认证。",
    )
    doc.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成网信送审 Word 套件")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "docs" / "网信送审物料",
    )
    parser.add_argument(
        "--hash-file",
        type=Path,
        default=ROOT / "packaging" / "dist" / "security-review" / "SHA256.txt",
    )
    args = parser.parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    sha = read_hash(args.hash_file)
    example = bool(sha) and not sha.startswith("（")

    build_plan(out_dir / "01-配合源代码安全检测工作方案.docx")
    build_confirmation(out_dir / "02-现场检测与销毁确认单.docx", sha, example)
    build_nda(out_dir / "03-保密与使用目的限定条款-草稿.docx")
    build_technical(out_dir / "04-技术附件-范围导读组件与已知风险.docx")
    print(f"wrote 4 docx → {out_dir}")
    print(f"snapshot sha256: {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
