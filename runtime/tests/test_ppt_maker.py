"""Contract tests for the bundled PPT制作 scripts.

Adapted from Nous Research powerpoint 1.1.0 (MIT). Page rendering is not
part of this skill.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from office_agent.skill_validate import validate_skill_dir

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = str(REPO / "bundled" / "skills" / "ppt-maker" / "scripts")
SKILL_DIR = REPO / "bundled" / "skills" / "ppt-maker"
SRC = str(REPO / "runtime" / "src")


def _env(**extra: str) -> dict[str, str]:
    env = dict(os.environ, LC_ALL="C", PYTHONIOENCODING="utf-8")
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = SRC if not prev else SRC + os.pathsep + prev
    env.update(extra)
    return env


def run(script, *args):
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script), *args],
        capture_output=True, text=True, encoding="utf-8", env=_env())
    assert proc.returncode == 0, f"{script} failed: {proc.stderr}"
    return json.loads(proc.stdout)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)


@pytest.fixture(scope="module")
def workdir(tmp_path_factory):
    return tmp_path_factory.mktemp("pptx")


@pytest.fixture(scope="module")
def sample_png(workdir):
    # 1x1 red PNG, hardcoded bytes -> no Pillow dependency.
    import base64
    data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4"
        "z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")
    path = workdir / "red.png"
    path.write_bytes(data)
    return str(path)


@pytest.fixture(scope="module")
def deck(workdir, sample_png):
    """Create a deck exercising every create feature."""
    spec = {
        "slide_size": "16:9",
        "slides": [
            {"layout": "title", "title": "Annual Review",
             "subtitle": "Fiscal year 2026",
             "notes": "Welcome the audience."},
            {"layout": "title_content", "title": "Agenda",
             "bullets": [
                 "Overview",
                 {"text": "Details", "level": 1, "bold": True,
                  "size": 20, "color": "CC0000", "font": "Arial"},
                 {"text": "Deep dive", "level": 2, "italic": True},
             ],
             "notes": "Keep this under two minutes."},
            {"layout": "blank", "title": None,
             "images": [{"path": sample_png, "left": 0.5, "top": 0.5,
                         "width": 2, "height": 2}],
             "tables": [{"left": 3, "top": 1, "width": 6, "height": 2,
                         "rows": [["Region", "Sales"],
                                  ["North", "120"], ["South", "80"]]}],
             "shapes": [{"type": "rounded_rectangle", "left": 10,
                         "top": 1, "width": 2.5, "height": 1,
                         "fill": "4472C4", "text": "Callout",
                         "text_color": "FFFFFF"}]},
            {"layout": "title_only", "title": "Charts",
             "charts": [
                 {"type": "bar", "left": 0.5, "top": 1.5, "width": 4,
                  "height": 3, "title": "Sales",
                  "categories": ["Q1", "Q2"],
                  "series": {"North": [10, 20], "South": [7, 13]}},
                 {"type": "line", "left": 4.7, "top": 1.5, "width": 4,
                  "height": 3, "categories": ["Jan", "Feb", "Mar"],
                  "series": {"Trend": [1, 3, 2]}},
                 {"type": "pie", "left": 8.9, "top": 1.5, "width": 4,
                  "height": 3, "categories": ["A", "B", "C"],
                  "series": {"Share": [50, 30, 20]}}]},
        ],
    }
    spec_path = workdir / "deck.json"
    write_json(spec_path, spec)
    out = workdir / "deck.pptx"
    result = run("pptx_create.py", str(spec_path), str(out))
    assert result["ok"] and result["slides"] == 4
    return str(out)


def test_create_and_outline(deck):
    outline = run("pptx_read.py", deck, "--outline")
    assert outline["slide_count"] == 4
    assert outline["slide_size_inches"][0] == pytest.approx(13.333, abs=0.01)
    s0, s1, s2, s3 = outline["slides"]
    assert "Annual Review" in s0["texts"]
    assert "Fiscal year 2026" in s0["texts"]
    assert s0["notes"] == "Welcome the audience."
    # bullets present on slide 1
    assert any("Deep dive" in t for t in s1["texts"])
    # table content
    assert s2["tables"][0][0] == ["Region", "Sales"]
    assert s2["tables"][0][2] == ["South", "80"]
    # image inventory + shape text
    assert len(s2["images"]) == 1 and s2["images"][0]["ext"] == "png"
    assert "Callout" in s2["texts"]
    # three charts with correct data
    assert len(s3["charts"]) == 3
    bar = s3["charts"][0]
    assert bar["categories"] == ["Q1", "Q2"]
    north = next(s for s in bar["series"] if s["name"] == "North")
    assert north["values"] == [10.0, 20.0]


def test_create_43_size(workdir):
    spec_path = workdir / "small.json"
    write_json(spec_path, {"slide_size": "4:3",
                           "slides": [{"layout": "title", "title": "T"}]})
    out = workdir / "small.pptx"
    run("pptx_create.py", str(spec_path), str(out))
    outline = run("pptx_read.py", str(out))
    assert outline["slide_size_inches"] == [10.0, 7.5]


def test_notes_mode(deck):
    result = run("pptx_read.py", deck, "--notes")
    assert result["notes"][1] == "Keep this under two minutes."


def test_image_export(deck, workdir):
    out_dir = workdir / "exported"
    result = run("pptx_read.py", deck, "--images", str(out_dir))
    assert len(result["exported"]) == 1
    exported = result["exported"][0]
    assert os.path.getsize(exported) > 0
    with open(exported, "rb") as fh:
        assert fh.read(8) == b"\x89PNG\r\n\x1a\n"


def test_template_fill_non_ascii(workdir):
    """Template token fill with non-ASCII values, forced under LC_ALL=C."""
    tpl_spec = workdir / "tpl.json"
    write_json(tpl_spec, {"slides": [
        {"layout": "title", "title": "{{city}} report",
         "subtitle": "Prepared by {{author}}",
         "notes": "Deck for {{city}}."},
        {"layout": "title_content", "title": "Data",
         "tables": [{"rows": [["Site", "{{city}}"]]}]},
    ]})
    template = workdir / "template.pptx"
    run("pptx_create.py", str(tpl_spec), str(template))

    values = workdir / "values.json"
    write_json(values, {"city": "Z\u00fcrich \u2014 \u2018Bericht\u2019",
                        "author": "Beispiel GmbH"})
    out = workdir / "filled.pptx"
    result = run("pptx_from_template.py", str(template), str(out),
                 "--values", str(values))
    assert result["tokens_filled"] == 4

    outline = run("pptx_read.py", str(out))
    expected = "Z\u00fcrich \u2014 \u2018Bericht\u2019"
    assert f"{expected} report" in outline["slides"][0]["texts"]
    assert outline["slides"][0]["notes"] == f"Deck for {expected}."
    assert outline["slides"][1]["tables"][0][0][1] == expected


def test_template_add_slides(workdir):
    template = workdir / "template.pptx"
    add_spec = workdir / "add.json"
    write_json(add_spec, {"slides": [
        {"layout": 1, "title": "Appended", "bullets": ["from layout"],
         "notes": "appended slide"}]})
    out = workdir / "appended.pptx"
    run("pptx_from_template.py", str(template), str(out),
        "--add-slides", str(add_spec))
    outline = run("pptx_read.py", str(out))
    assert outline["slide_count"] == 3
    assert "Appended" in outline["slides"][2]["texts"]


def test_edit_replace_text(deck, workdir):
    edited = workdir / "edited.pptx"
    result = run("pptx_edit.py", deck, "--output", str(edited),
                 "--replace-text", "Annual Review", "Semi-Annual Review",
                 "--replace-text", "South", "West")
    assert result["replacements"] == 2  # title + table cell
    outline = run("pptx_read.py", str(edited))
    assert "Semi-Annual Review" in outline["slides"][0]["texts"]
    assert outline["slides"][2]["tables"][0][2][0] == "West"
    # formatting survives a run-level replace: red bold bullet untouched
    assert any("Deep dive" in t for t in outline["slides"][1]["texts"])


def test_edit_chart_data(deck, workdir):
    spec = workdir / "chart_update.json"
    write_json(spec, {"slide": 3, "chart": 0,
                      "categories": ["Q3", "Q4"],
                      "series": {"North": [30, 40], "South": [21, 34]}})
    edited = workdir / "chart_edited.pptx"
    run("pptx_edit.py", deck, "--output", str(edited),
        "--chart-data", str(spec))
    outline = run("pptx_read.py", str(edited))
    bar = outline["slides"][3]["charts"][0]
    assert bar["categories"] == ["Q3", "Q4"]
    north = next(s for s in bar["series"] if s["name"] == "North")
    assert north["values"] == [30.0, 40.0]


def test_edit_remove_and_move_slide(deck, workdir):
    edited = workdir / "reordered.pptx"
    run("pptx_edit.py", deck, "--output", str(edited),
        "--remove-slide", "2", "--move-slide", "2", "0")
    outline = run("pptx_read.py", str(edited))
    assert outline["slide_count"] == 3
    # charts slide (was index 3, then 2 after removal) moved to front
    assert len(outline["slides"][0]["charts"]) == 3
    assert "Annual Review" in outline["slides"][1]["texts"]


def test_edit_swap_image(deck, workdir):
    import base64
    blue = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNg"
        "YPj/HwADAgH/p5UronAAAAAASUVORK5CYII=")
    blue_path = workdir / "blue.png"
    blue_path.write_bytes(blue)
    outline = run("pptx_read.py", deck)
    # find picture shape name via python-pptx directly
    sys.path.insert(0, SCRIPTS)
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    prs = Presentation(deck)
    name = next(s.name for s in prs.slides[2].shapes
                if s.shape_type == MSO_SHAPE_TYPE.PICTURE)
    edited = workdir / "swapped.pptx"
    run("pptx_edit.py", deck, "--output", str(edited),
        "--swap-image", "2", name, str(blue_path))
    out_dir = workdir / "swapped_images"
    result = run("pptx_read.py", str(edited), "--images", str(out_dir))
    with open(result["exported"][0], "rb") as fh:
        assert fh.read() == blue


def test_help_flags():
    for script in ("pptx_create.py", "pptx_read.py", "pptx_edit.py",
                   "pptx_from_template.py", "pptx_validate.py"):
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, script), "--help"],
            capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0 and "usage" in proc.stdout.lower()


# ---------------------------------------------------------------------------
# parity features: render, run-merge replace, chart ops, duplication,
# polish (background/hyperlink/slide-number/footer), notes editing
# ---------------------------------------------------------------------------

def run_raw(script, *args, env=None, cwd=None):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script), *args],
        capture_output=True, text=True, encoding="utf-8",
        env=env or _env(), cwd=cwd)


def test_replace_across_identically_formatted_runs(workdir):
    """A match split mid-word into equal-format runs keeps formatting."""
    import copy as cp
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1),
                                   Inches(6), Inches(1))
    para = box.text_frame.paragraphs[0]
    run_obj = para.add_run()
    run_obj.text = "Say TotalWord now"
    run_obj.font.bold = True
    run_obj.font.size = Pt(20)
    run_obj.font.color.rgb = RGBColor.from_string("CC0000")
    # simulate PowerPoint's spell-check split: same rPr, seam mid-match
    second = cp.deepcopy(run_obj._r)
    run_obj._r.addnext(second)
    run_obj.text = "Say Total"
    para.runs[1].text = "Word now"
    path = workdir / "split_runs.pptx"
    prs.save(str(path))

    edited = workdir / "split_runs_edited.pptx"
    result = run("pptx_edit.py", str(path), "--output", str(edited),
                 "--replace-text", "TotalWord", "MergedWord")
    assert result["replacements"] == 1

    prs2 = Presentation(str(edited))
    para2 = prs2.slides[0].shapes[0].text_frame.paragraphs[0]
    assert "".join(r.text for r in para2.runs) == "Say MergedWord now"
    for r in para2.runs:
        assert r.font.bold is True
        assert r.font.size == Pt(20)
        assert str(r.font.color.rgb) == "CC0000"


def test_chart_surgical_ops(deck, workdir):
    from pptx import Presentation
    spec = workdir / "chart_ops.json"
    write_json(spec, {"slide": 3, "chart": 0, "ops": [
        {"op": "update_series", "name": "North", "values": [99, 88]},
        {"op": "add_series", "name": "East", "values": [1, 2]},
        {"op": "remove_series", "name": "South"},
        {"op": "rename_category", "from": "Q1", "to": "Q1 FY26"},
        {"op": "set_title", "title": "Updated Sales"}]})
    edited = workdir / "chart_ops.pptx"
    run("pptx_edit.py", deck, "--output", str(edited),
        "--chart-data", str(spec))
    outline = run("pptx_read.py", str(edited))
    bar = outline["slides"][3]["charts"][0]
    assert bar["categories"] == ["Q1 FY26", "Q2"]
    names = [s["name"] for s in bar["series"]]
    assert "South" not in names and "East" in names
    north = next(s for s in bar["series"] if s["name"] == "North")
    assert north["values"] == [99.0, 88.0]
    east = next(s for s in bar["series"] if s["name"] == "East")
    assert east["values"] == [1.0, 2.0]
    chart = next(s.chart for s in Presentation(str(edited)).slides[3].shapes
                 if s.has_chart)
    assert chart.chart_title.text_frame.text == "Updated Sales"


def test_chart_op_unknown_series_fails(deck, workdir):
    spec = workdir / "chart_bad.json"
    write_json(spec, {"slide": 3, "chart": 0, "ops": [
        {"op": "update_series", "name": "Nowhere", "values": [1, 2]}]})
    proc = run_raw("pptx_edit.py", deck, "--output",
                   str(workdir / "never.pptx"), "--chart-data", str(spec))
    assert proc.returncode != 0
    assert "Nowhere" in proc.stderr


def test_duplicate_image_slide_is_independent(deck, workdir):
    import base64
    dup = workdir / "dup.pptx"
    result = run("pptx_edit.py", deck, "--output", str(dup),
                 "--duplicate-slide", "2")
    assert result["duplicated_to"] == 4
    outline = run("pptx_read.py", str(dup))  # re-opens cleanly
    assert outline["slide_count"] == 5
    s4 = outline["slides"][4]
    assert len(s4["images"]) == 1
    assert s4["tables"][0][0] == ["Region", "Sales"]
    assert "Callout" in s4["texts"]

    # independence: swap the image on the COPY, original stays red
    blue = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNg"
        "YPj/HwADAgH/p5UronAAAAAASUVORK5CYII=")
    blue_path = workdir / "blue2.png"
    blue_path.write_bytes(blue)
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    prs = Presentation(str(dup))
    name = next(s.name for s in prs.slides[4].shapes
                if s.shape_type == MSO_SHAPE_TYPE.PICTURE)
    run("pptx_edit.py", str(dup), "--swap-image", "4", name,
        str(blue_path))
    prs = Presentation(str(dup))
    orig = next(s for s in prs.slides[2].shapes
                if s.shape_type == MSO_SHAPE_TYPE.PICTURE)
    copy_pic = next(s for s in prs.slides[4].shapes
                    if s.shape_type == MSO_SHAPE_TYPE.PICTURE)
    assert copy_pic.image.blob == blue
    assert orig.image.blob != blue


def test_duplicate_chart_slide_refused(deck, workdir):
    proc = run_raw("pptx_edit.py", deck, "--output",
                   str(workdir / "never2.pptx"), "--duplicate-slide", "3")
    assert proc.returncode != 0
    assert "chart" in proc.stderr.lower()


def test_create_polish_features(workdir):
    from pptx import Presentation
    spec_path = workdir / "polish.json"
    write_json(spec_path, {"slides": [
        {"layout": "title_content", "title": "Polished",
         "background": "112233", "footer": "Confidential draft",
         "slide_number": True,
         "bullets": [{"text": "Visit example",
                      "link": "https://example.com/info"}]}]})
    out = workdir / "polish.pptx"
    run("pptx_create.py", str(spec_path), str(out))
    prs = Presentation(str(out))
    slide = prs.slides[0]
    assert str(slide.background.fill.fore_color.rgb) == "112233"
    ph_idx = [ph.placeholder_format.idx for ph in slide.placeholders]
    assert 12 in ph_idx  # slide number enabled
    footer = next(ph for ph in slide.placeholders
                  if ph.placeholder_format.idx == 11)
    assert footer.text_frame.text == "Confidential draft"
    link_runs = [r for sh in slide.shapes if sh.has_text_frame
                 for p in sh.text_frame.paragraphs for r in p.runs
                 if r.hyperlink.address]
    assert link_runs[0].hyperlink.address == "https://example.com/info"


def test_edit_polish_features(deck, workdir):
    from pptx import Presentation
    edited = workdir / "polish_edit.pptx"
    result = run("pptx_edit.py", deck, "--output", str(edited),
                 "--set-background", "0", "004400",
                 "--hyperlink", "1", "Overview", "https://example.com/x",
                 "--enable-slide-number", "1",
                 "--set-footer", "1", "Footer via edit")
    assert result["background_set"] and result["footer_set"]
    assert result["hyperlinked_runs"] == 1
    assert result["slide_number_enabled"] is True
    prs = Presentation(str(edited))
    assert str(prs.slides[0].background.fill.fore_color.rgb) == "004400"
    s1 = prs.slides[1]
    assert any(ph.placeholder_format.idx == 12 for ph in s1.placeholders)
    footer = next(ph for ph in s1.placeholders
                  if ph.placeholder_format.idx == 11)
    assert footer.text_frame.text == "Footer via edit"
    links = [r.hyperlink.address for sh in s1.shapes if sh.has_text_frame
             for p in sh.text_frame.paragraphs for r in p.runs
             if r.hyperlink.address]
    assert links == ["https://example.com/x"]


def test_set_and_append_notes(deck, workdir):
    edited = workdir / "notes_edit.pptx"
    result = run("pptx_edit.py", deck, "--output", str(edited),
                 "--set-notes", "0", "Fresh notes")
    assert result["notes_set"]
    run("pptx_edit.py", str(edited), "--append-notes", "0", "Second line")
    notes = run("pptx_read.py", str(edited), "--notes")
    assert notes["notes"][0] == "Fresh notes\nSecond line"


def test_skill_package_is_valid():
    result = validate_skill_dir(SKILL_DIR)
    assert result["ok"], result["errors"]
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "display_name: PPT制作" in text
    assert "name: ppt-maker" in text
    assert "pptx_render" not in text


def test_jail_rejects_output_outside_workspace(tmp_path: Path):
    work = tmp_path / "ws"
    work.mkdir()
    spec = work / "deck.json"
    spec.write_text(
        '{"slides":[{"layout":"title","title":"内网汇报"}]}',
        encoding="utf-8",
    )
    outside = tmp_path / "outside.pptx"
    proc = run_raw(
        "pptx_create.py",
        str(spec),
        str(outside),
        env=_env(OFFICE_AGENT_SCRIPT_JAIL="1"),
        cwd=work,
    )
    assert proc.returncode != 0
    assert "outside" in proc.stderr.lower() or "workspace" in proc.stderr.lower()
    assert not outside.exists()


def _semantic_all_types():
    return {
        "title": "试点汇报",
        "subtitle": "办公室 2026-10",
        "palette": "zhengwu-navy",
        "slides": [
            {"type": "title", "title": "试点汇报", "subtitle": "办公室",
             "notes": "开场"},
            {"type": "toc", "title": "汇报提纲",
             "bullets": ["背景", "进展", "问题", "建议"]},
            {"type": "section", "title": "第一部分 进展"},
            {"type": "bullets", "title": "主要进展",
             "bullets": ["完成摸底", "启动试点", "形成口径"]},
            {"type": "two_column", "title": "对照",
             "left": ["已完成"], "right": ["待推进"]},
            {"type": "kpi", "title": "指标",
             "kpis": [{"label": "覆盖率", "value": "92%"},
                      {"label": "办结", "value": "18"}]},
            {"type": "table", "title": "一览",
             "rows": [["事项", "进度"], ["摸底", "完成"], ["试点", "进行中"]]},
            {"type": "chart", "title": "对比",
             "chart": {"kind": "bar", "categories": ["一季度", "二季度"],
                       "series": {"本部": [10, 12], "分部": [7, 9]}}},
            {"type": "mixed_chart", "title": "解读",
             "chart": {"kind": "line", "categories": ["1月", "2月", "3月"],
                       "series": {"趋势": [1, 3, 2]}},
             "bullets": ["前低后高", "需核实口径"]},
            {"type": "process", "title": "步骤",
             "steps": ["摸底", "试点", "推广"]},
            {"type": "closing", "title": "请示事项",
             "bullets": ["请予支持"]},
        ],
    }


def test_semantic_all_types_create(workdir):
    spec_path = workdir / "semantic.json"
    write_json(spec_path, _semantic_all_types())
    report = run("pptx_validate.py", str(spec_path))
    assert report["ok"] is True
    out = workdir / "semantic.pptx"
    result = run("pptx_create.py", str(spec_path), str(out))
    assert result["ok"] and result["slides"] == 11
    assert result["palette"] == "zhengwu-navy"
    outline = run("pptx_read.py", str(out), "--outline")
    assert outline["slide_count"] == 11
    texts = [" ".join(s["texts"]) for s in outline["slides"]]
    assert "试点汇报" in texts[0]
    assert "汇报提纲" in texts[1]
    assert "第一部分 进展" in texts[2]
    assert "完成摸底" in texts[3]
    assert "已完成" in texts[4] and "待推进" in texts[4]
    assert "92%" in texts[5]
    assert outline["slides"][6]["tables"][0][1] == ["摸底", "完成"]
    assert outline["slides"][7]["charts"][0]["categories"] == ["一季度", "二季度"]
    assert "前低后高" in texts[8]
    assert "推广" in texts[9]
    assert "请予支持" in texts[10]
    assert outline["slides"][0]["notes"] == "开场"


def test_semantic_default_vs_variant_differs(workdir):
    from pptx import Presentation
    base = {
        "palette": "zhengwu-navy",
        "slides": [{"type": "bullets", "title": "要点",
                    "bullets": ["甲", "乙", "丙"]}],
    }
    cards = {
        "palette": "zhengwu-navy",
        "slides": [{"type": "bullets", "variant": "cards", "title": "要点",
                    "bullets": ["甲", "乙", "丙"]}],
    }
    write_json(workdir / "base.json", base)
    write_json(workdir / "cards.json", cards)
    run("pptx_create.py", str(workdir / "base.json"), str(workdir / "base.pptx"))
    run("pptx_create.py", str(workdir / "cards.json"), str(workdir / "cards.pptx"))
    n_base = len(Presentation(str(workdir / "base.pptx")).slides[0].shapes)
    n_cards = len(Presentation(str(workdir / "cards.pptx")).slides[0].shapes)
    assert n_cards > n_base
    outline = run("pptx_read.py", str(workdir / "cards.pptx"))
    blob = " ".join(outline["slides"][0]["texts"])
    assert "甲" in blob and "乙" in blob


def test_validate_rejects_bad_type_too_many_bullets_and_hex(workdir):
    bad_type = {"slides": [{"type": "magic", "title": "x"}]}
    write_json(workdir / "bad_type.json", bad_type)
    proc = run_raw("pptx_validate.py", str(workdir / "bad_type.json"))
    assert proc.returncode != 0
    report = json.loads(proc.stdout)
    assert report["ok"] is False
    assert any("type" in e for e in report["errors"])

    too_many = {"palette": "zhengwu-navy", "slides": [
        {"type": "bullets", "title": "x",
         "bullets": [f"要点{i}" for i in range(8)]}]}
    write_json(workdir / "too_many.json", too_many)
    proc = run_raw("pptx_validate.py", str(workdir / "too_many.json"))
    assert proc.returncode != 0
    assert "上限" in proc.stdout

    canvas_hex = {"palette": "zhengwu-navy", "slides": [{
        "type": "canvas", "title": "x",
        "shapes": [{"type": "rectangle", "left": 1, "top": 1,
                    "width": 2, "height": 1, "fill": "FF00FF"}],
    }]}
    write_json(workdir / "canvas_hex.json", canvas_hex)
    proc = run_raw("pptx_validate.py", str(workdir / "canvas_hex.json"))
    assert proc.returncode != 0
    assert "FF00FF" in proc.stdout or "token" in proc.stdout

    with_xy = {"palette": "zhengwu-navy", "slides": [
        {"type": "bullets", "title": "x", "bullets": ["a"], "left": 1}]}
    write_json(workdir / "xy.json", with_xy)
    proc = run_raw("pptx_validate.py", str(workdir / "xy.json"))
    assert proc.returncode != 0
    assert "left" in proc.stdout


def test_legacy_layout_spec_fails_validate_but_create_still_works(workdir):
    spec = {"slides": [{"layout": "title", "title": "旧稿"}]}
    write_json(workdir / "legacy.json", spec)
    proc = run_raw("pptx_validate.py", str(workdir / "legacy.json"))
    assert proc.returncode != 0
    assert "layout" in proc.stdout
    result = run("pptx_create.py", str(workdir / "legacy.json"),
                 str(workdir / "legacy.pptx"))
    assert result["ok"] and result["slides"] == 1


def test_brief_deck_content_alias_accepted(workdir):
    spec = {
        "title": "汇报演示",
        "slides": [
            {"type": "title", "title": "汇报演示", "subtitle": "场合"},
            {"type": "content", "title": "进展", "bullets": ["一项"]},
            {"type": "closing", "title": "完毕", "bullets": ["请示"]},
        ],
    }
    write_json(workdir / "brief.json", spec)
    report = run("pptx_validate.py", str(workdir / "brief.json"))
    assert report["ok"]
    result = run("pptx_create.py", str(workdir / "brief.json"),
                 str(workdir / "brief.pptx"))
    assert result["slides"] == 3
    outline = run("pptx_read.py", str(workdir / "brief.pptx"))
    blob = " ".join(t for s in outline["slides"] for t in s["texts"])
    assert "一项" in blob and "请示" in blob


def test_canvas_token_fill_allowed(workdir):
    spec = {
        "palette": "zhengwu-navy",
        "slides": [{
            "type": "canvas",
            "title": "标注",
            "shapes": [{
                "type": "rounded_rectangle",
                "left": 1, "top": 2, "width": 3, "height": 1,
                "fill": "primary", "text": "说明", "text_color": "on_primary",
            }],
        }],
    }
    write_json(workdir / "canvas.json", spec)
    assert run("pptx_validate.py", str(workdir / "canvas.json"))["ok"]
    run("pptx_create.py", str(workdir / "canvas.json"),
        str(workdir / "canvas.pptx"))
    outline = run("pptx_read.py", str(workdir / "canvas.pptx"))
    assert "说明" in " ".join(outline["slides"][0]["texts"])


def test_edit_palette_keeps_copy(workdir):
    from pptx import Presentation
    spec = {
        "palette": "zhengwu-navy",
        "title": "试点汇报",
        "slides": [
            {"type": "title", "title": "试点汇报", "subtitle": "办公室"},
            {"type": "bullets", "title": "进展", "bullets": ["完成摸底"]},
        ],
    }
    write_json(workdir / "navy.json", spec)
    src = workdir / "navy.pptx"
    run("pptx_create.py", str(workdir / "navy.json"), str(src))
    edited = workdir / "crimson.pptx"
    result = run("pptx_edit.py", str(src), "--output", str(edited),
                 "--palette", "dangjian-crimson")
    assert result["palette_applied"] and result["palette"] == "dangjian-crimson"
    before = run("pptx_read.py", str(src))
    after = run("pptx_read.py", str(edited))
    assert before["slides"][0]["texts"] == after["slides"][0]["texts"]
    assert before["slides"][1]["texts"] == after["slides"][1]["texts"]
    prs = Presentation(str(edited))
    fills = []
    for shape in prs.slides[0].shapes:
        try:
            if shape.fill.type is not None:
                fills.append(str(shape.fill.fore_color.rgb))
        except (AttributeError, TypeError, ValueError):
            continue
    assert "8B1E1E" in fills


def test_palette_from_primary_hex(workdir):
    spec = {
        "palette": {"primary": "003A70"},
        "slides": [{"type": "title", "title": "单位蓝"}],
    }
    write_json(workdir / "brand.json", spec)
    result = run("pptx_create.py", str(workdir / "brand.json"),
                 str(workdir / "brand.pptx"))
    assert result["ok"]
    outline = run("pptx_read.py", str(workdir / "brand.pptx"))
    assert "单位蓝" in outline["slides"][0]["texts"]


def test_skill_mentions_unified_entry_and_forbids_handwritten_pptx():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "pptx_validate.py" in text
    assert "brief-deck" not in text
    assert "office-visual-design" not in text
    assert "禁止当场重写 python-pptx" in text or "禁止在工作区重写 python-pptx" in text
