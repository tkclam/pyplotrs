"""Figures: construction, layout and output."""

import re
import shutil
import subprocess

import pytest

import pyplotrs as pp
from tests.conftest import decode_png, pixel


def test_subplots_shapes():
    _, ax = pp.subplots()
    assert isinstance(ax, pp.Axes)
    _, row = pp.subplots(1, 3)
    assert len(row) == 3
    fig, grid = pp.subplots(2, 3)
    assert len(grid) == 2 and len(grid[0]) == 3
    assert len(fig.axes) == 6


def test_mosaic_spans_cells():
    fig, axd = pp.subplot_mosaic("""
        AAB
        CDB
    """)
    assert set(axd) == {"A", "B", "C", "D"}
    assert fig.nrows == 2 and fig.ncols == 3
    _, axd = pp.subplot_mosaic("AB;CC")
    assert set(axd) == {"A", "B", "C"}
    with pytest.raises(ValueError, match="rectangle"):
        pp.subplot_mosaic("AB;BA")


def test_figure_add_axes_checks_the_grid():
    fig = pp.figure(nrows=2, ncols=2)
    fig.add_axes(0, 0, colspan=2)
    with pytest.raises(ValueError, match="outside"):
        fig.add_axes(1, 1, colspan=2)


def test_sizes_and_units():
    fig, _ = pp.subplots(figsize=(3, 2), units="in")
    assert fig.size == (216.0, 144.0)
    w, h, _ = decode_png(fig.to_bytes("png", dpi=100))
    assert (w, h) == (300, 200)
    with pytest.raises(ValueError, match="units"):
        pp.subplots(units="furlong")
    with pytest.raises(ValueError, match="positive"):
        pp.subplots(figsize=(0, 100))
    with pytest.raises(ValueError, match="dpi"):
        fig.to_bytes("png", dpi=0)


def _plot_rects(fig):
    fig.to_bytes("png", dpi=50)
    return [(v.x, v.y, v.w, v.h) for v in (ax._last_view for ax in fig.axes)]


def test_grid_plots_align_and_respect_ratios():
    fig, grid = pp.subplots(2, 2, width_ratios=[2, 1])
    for row in grid:
        for i, ax in enumerate(row):
            ax.line([0, 1], [0, 10 ** (3 * i)])  # very different label widths
    (a, b), (c, d) = (r[:2] for r in [_plot_rects(fig)[:2], _plot_rects(fig)[2:]])
    assert a[0] == pytest.approx(c[0]) and b[0] == pytest.approx(d[0])  # columns align
    assert a[1] == pytest.approx(b[1]) and c[1] == pytest.approx(d[1])  # rows align
    assert a[2] == pytest.approx(2 * b[2])


def test_everything_stays_on_the_page():
    fig, grid = pp.subplots(2, 2, figsize=(300, 240))
    for row in grid:
        for ax in row:
            ax.line([0, 1e5], [0, 1e5])
            ax.set(title="Title", xlabel="x label", ylabel="y label")
    fig.set(suptitle="Suptitle")
    w, h = fig.size
    for x, y, pw, ph in _plot_rects(fig):
        assert x > 20 and x + pw < w and y > 30 and y + ph < h - 20


def test_figure_legend_and_colorbar_reserve_space():
    fig, ax = pp.subplots()
    ax.line([0, 1], [0, 1], label="a")
    plain = _plot_rects(fig)[0]
    fig.legend()
    with_legend = _plot_rects(fig)[0]
    assert with_legend[2] < plain[2]
    fig2, ax2 = pp.subplots()
    fig2.colorbar(ax2.imshow([[1, 2], [3, 4]]), label="z", orientation="horizontal")
    assert _plot_rects(fig2)[0][3] < plain[3]
    with pytest.raises(TypeError, match="colormapped"):
        fig.colorbar(ax.line([0], [0]))


def test_png_background_and_transparency():
    fig, _ = pp.subplots(figsize=(50, 40), theme="dark")
    _, _, rows = decode_png(fig.to_bytes("png", dpi=72))
    assert pixel(rows, 1, 1)[:3] == (18, 18, 18)
    _, _, rows = decode_png(fig.to_bytes("png", dpi=72, transparent=True))
    assert pixel(rows, 1, 1)[3] == 0


def test_svg_is_sized_in_points_with_real_text():
    fig, ax = pp.subplots()
    ax.set(title="Temperature")
    svg = fig.to_bytes("svg").decode()
    assert re.search(r'width="250(\.0+)?pt"', svg)
    assert "Temperature" in svg and "@font-face" in svg


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="needs pdftotext")
def test_pdf_text_is_selectable(tmp_path):
    fig, ax = pp.subplots()
    ax.line([0, 1], [0, 1])
    ax.set(title="Membrane potential", xlabel="time (s)")
    fig.save(tmp_path / "f.pdf")
    text = subprocess.run(
        ["pdftotext", str(tmp_path / "f.pdf"), "-"], capture_output=True, text=True
    ).stdout
    assert "Membrane potential" in text and "time (s)" in text


def test_tagged_pdf_and_html(tmp_path):
    fig, ax = pp.subplots()
    ax.set(title="Growth", xlabel="day", ylabel="size")
    pdf = fig.to_bytes("pdf", tagged=True)
    assert b"/StructTreeRoot" in pdf
    fig.save(tmp_path / "f.html")
    page = (tmp_path / "f.html").read_text()
    assert page.startswith("<!DOCTYPE html>") and 'aria-label="Growth; size versus day"' in page


def test_save_picks_format_from_extension(tmp_path):
    fig, _ = pp.subplots()
    for ext, magic in (("png", b"\x89PNG"), ("pdf", b"%PDF"), ("svg", b"<"), ("htm", b"<!DOCTYPE")):
        fig.save(tmp_path / f"f.{ext}")
        assert (tmp_path / f"f.{ext}").read_bytes().startswith(magic)
    with pytest.raises(ValueError, match="format"):
        fig.save(tmp_path / "f.jpeg")


def test_notebook_display():
    fig, _ = pp.subplots()
    assert fig._repr_png_()[:4] == b"\x89PNG"


def test_theme_selection():
    fig, ax = pp.subplots(theme="grayscale")
    assert ax.theme is fig.theme
    assert ax.line([0], [0]).color == (0, 0, 0, 255)
    with pytest.raises(ValueError, match="theme"):
        pp.subplots(theme="neon")
    custom = pp.themes.default.replace(grid=True, spines=("left", "bottom", "top", "right"))
    fig, _ = pp.subplots(theme=custom)
    assert fig.theme.grid
    with pytest.raises(ValueError, match="spines"):
        pp.Theme(spines=("middle",))


def test_set_theme_changes_the_default():
    pp.set_theme("dark")
    assert pp.subplots()[0].theme == pp.themes.dark
    pp.set_theme()
    assert pp.get_theme() == pp.themes.default


def test_threads_render_independently():
    from concurrent.futures import ThreadPoolExecutor

    def render(i):
        fig, ax = pp.subplots()
        ax.line(list(range(1000)), [v * i for v in range(1000)])
        return fig.to_bytes("png", dpi=72)

    with ThreadPoolExecutor(4) as pool:
        outputs = list(pool.map(render, range(8)))
    assert outputs[1] == render(1)
