"""Text rotation, legend layout, and colorbar placement.

Three option sets that were each a single knob: `text` could not be rotated at
all, `legend` took only `loc`, and `colorbar` took only `label`. Rotated tick
and annotation labels are near-universal in real figures, a tall legend crowds
the data it sits on, and a horizontal colorbar is the standard choice under a
wide panel.

The rotation is worth a note: it is applied as a *group transform* in the IR,
not by baking glyphs into paths, so rotated text stays selectable in PDF and
SVG. That is the whole premise of the library, so it is asserted here.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pyplotrs as pp
import pytest

# -- text rotation ------------------------------------------------------------

def test_rotation_changes_the_output(tmp_path):
    def render(name, rot):
        fig, ax = pp.subplots(figsize=(220, 160))
        ax.line([0, 1], [0, 1])
        ax.text(0.5, 0.5, "hello", rotation=rot)
        out = tmp_path / f"{name}.png"
        fig.save(str(out))
        return out.read_bytes()

    assert render("flat", 0) != render("turned", 45)


def test_unrotated_text_emits_no_transform(tmp_path):
    """Rotation must cost nothing when it is not used: `rotation=0` has to take
    the same path as before, or every existing figure changes."""
    fig, ax = pp.subplots(figsize=(220, 160))
    ax.line([0, 1], [0, 1])
    ax.text(0.5, 0.5, "hello")
    out = tmp_path / "flat.svg"
    fig.save(str(out))
    svg = out.read_text()
    assert "hello" in svg
    assert 'transform="matrix(1,0,0,1' not in svg


def test_rotated_text_is_a_group_transform_in_svg(tmp_path):
    fig, ax = pp.subplots(figsize=(220, 160))
    ax.line([0, 1], [0, 1])
    ax.text(0.5, 0.5, "hello", rotation=90)
    svg = (tmp_path / "r.svg")
    fig.save(str(svg))
    assert re.search(r'transform="matrix\(', svg.read_text())


def test_rotated_text_stays_selectable_in_pdf(tmp_path):
    """The point of the group-transform approach rather than outlining."""
    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext not available")
    fig, ax = pp.subplots(figsize=(300, 220))
    ax.line([0, 1], [0, 1])
    ax.text(0.5, 0.5, "ROTATED", rotation=90)
    out = tmp_path / "r.pdf"
    fig.save(str(out))
    text = subprocess.run(["pdftotext", str(out), "-"],
                          capture_output=True, text=True).stdout
    assert "ROTATED" in text.replace("\n", "")


@pytest.mark.parametrize("rot", [0, 30, 90, -45, 180])
def test_rotation_renders_at_any_angle(rot, tmp_path):
    fig, ax = pp.subplots(figsize=(220, 160))
    ax.line([0, 1], [0, 1])
    ax.text(0.5, 0.5, "x", rotation=rot)
    ax.annotate("a", (0.5, 0.5), xytext=(0.2, 0.8), rotation=rot)
    fig.save(str(tmp_path / f"r{rot}.png"))


# -- legend layout ------------------------------------------------------------

def _multi(ax, n=6):
    for i in range(n):
        ax.line([0, 1, 2], [i, i + 1, i * 0.5], label=f"series {i}")


def test_ncol_makes_the_box_wider_and_shorter():
    from pyplotrs import _pyplotrs_core as _core
    from pyplotrs._draw import _measure_legend
    scene = _core.Scene(400.0, 300.0)
    entries = [{"kind": "line", "label": f"series {i}", "color": (0, 0, 0, 255)}
               for i in range(6)]
    w1, h1, _ = _measure_legend(scene, entries, None, {"ncol": 1})
    w2, h2, _ = _measure_legend(scene, entries, None, {"ncol": 2})
    assert w2 > w1 and h2 < h1


def test_ncol_renders(tmp_path):
    fig, ax = pp.subplots(figsize=(320, 240))
    _multi(ax)
    ax.legend(ncol=3)
    fig.save(str(tmp_path / "ncol.png"))


def test_legend_title_grows_the_box():
    from pyplotrs import _pyplotrs_core as _core
    from pyplotrs._draw import _measure_legend
    scene = _core.Scene(400.0, 300.0)
    entries = [{"kind": "line", "label": "a", "color": (0, 0, 0, 255)}]
    _, h1, _ = _measure_legend(scene, entries, None, {})
    _, h2, _ = _measure_legend(scene, entries, None, {"title": "Runs"})
    assert h2 > h1


def test_frameon_false_drops_the_box(tmp_path):
    def render(name, frameon):
        fig, ax = pp.subplots(figsize=(280, 200))
        _multi(ax, 3)
        ax.legend(frameon=frameon)
        out = tmp_path / f"{name}.svg"
        fig.save(str(out))
        return out.read_text()

    framed, bare = render("framed", True), render("bare", False)
    assert framed != bare
    assert bare.count("<path") < framed.count("<path")


def test_legend_fontsize_overrides_the_theme():
    from pyplotrs import _pyplotrs_core as _core
    from pyplotrs._draw import _measure_legend
    scene = _core.Scene(400.0, 300.0)
    entries = [{"kind": "line", "label": "abc", "color": (0, 0, 0, 255)}]
    _, _, m1 = _measure_legend(scene, entries, None, {})
    _, _, m2 = _measure_legend(scene, entries, None, {"fontsize": 20.0})
    assert m2["size"] == 20.0 and m2["size"] != m1["size"]


def test_figure_legend_takes_the_same_options(tmp_path):
    fig, axes = pp.subplots(ncols=2, figsize=(420, 200))
    for ax in axes:
        _multi(ax, 3)
    fig.legend(ncol=2, title="All", frameon=False)
    fig.save(str(tmp_path / "figleg.png"))


# -- colorbar -----------------------------------------------------------------

_GRID = [[i * j for j in range(8)] for i in range(6)]


def test_horizontal_colorbar_renders(tmp_path):
    fig, ax = pp.subplots(figsize=(320, 260))
    m = ax.imshow(_GRID)
    fig.colorbar(m, label="v", orientation="horizontal")
    fig.save(str(tmp_path / "h.png"))


def test_horizontal_colorbar_reserves_a_bottom_band():
    """It gets its own band beneath the x-axis label, so the plot area has to
    shrink vertically rather than horizontally."""
    from pyplotrs import _pyplotrs_core as _core
    fig, ax = pp.subplots(figsize=(320, 260))
    m = ax.imshow(_GRID)
    fig.colorbar(m, orientation="horizontal")
    scene = _core.Scene(320.0, 260.0)
    bands, _, _ = ax._bands(scene, (0.0, 8.0), (0.0, 6.0))
    assert bands[6] > 0.0, "horizontal colorbar reserved no height"
    assert bands[5] == 0.0, "and must not also reserve width"


def test_vertical_colorbar_still_reserves_width():
    from pyplotrs import _pyplotrs_core as _core
    fig, ax = pp.subplots(figsize=(320, 260))
    m = ax.imshow(_GRID)
    fig.colorbar(m)
    scene = _core.Scene(320.0, 260.0)
    bands, _, _ = ax._bands(scene, (0.0, 8.0), (0.0, 6.0))
    assert bands[5] > 0.0 and bands[6] == 0.0


def test_shrink_changes_the_output(tmp_path):
    def render(name, **kw):
        fig, ax = pp.subplots(figsize=(300, 240))
        m = ax.imshow(_GRID)
        fig.colorbar(m, **kw)
        out = tmp_path / f"{name}.svg"
        fig.save(str(out))
        return out.read_text()

    assert render("full") != render("short", shrink=0.5)


def test_explicit_colorbar_ticks():
    from pyplotrs._draw import _colorbar_ticks
    cb = {"vmin": 0.0, "vmax": 100.0, "norm": None, "ticks": [0, 50, 100],
          "format": None, "label": None}
    assert [v for v, _ in _colorbar_ticks(cb)] == [0.0, 50.0, 100.0]


def test_colorbar_format_applies():
    from pyplotrs._draw import _colorbar_ticks
    cb = {"vmin": 0.0, "vmax": 100.0, "norm": None, "ticks": [0, 50],
          "format": "{x:.2f}", "label": None}
    assert [s for _, s in _colorbar_ticks(cb)] == ["0.00", "50.00"]


def test_colorbar_rejects_a_bad_orientation():
    fig, ax = pp.subplots()
    m = ax.imshow(_GRID)
    with pytest.raises(ValueError, match="orientation"):
        fig.colorbar(m, orientation="diagonal")
