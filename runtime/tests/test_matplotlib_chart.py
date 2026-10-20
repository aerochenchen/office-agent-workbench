"""Smoke: bundled Runtime can render a static chart with matplotlib (Agg)."""

from __future__ import annotations

from pathlib import Path


def test_matplotlib_agg_saves_png(tmp_path: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = tmp_path / "smoke-chart.png"
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(["A", "B", "C"], [3, 7, 2])
    ax.set_title("smoke")
    fig.tight_layout()
    fig.savefig(out, dpi=100, bbox_inches="tight")
    plt.close(fig)

    assert out.is_file()
    assert out.stat().st_size > 500
