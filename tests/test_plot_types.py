"""The plot types restored in Phase 4, plus the new line/band helpers.

Ten of these were removed by the "refocus" commit while their Rust kernels and
draw handlers were left in the tree - roughly 250 lines of live-but-unreachable
Python and two compiled-in Rust entry points with no caller. Re-exposing them is
mostly re-adding signatures, but nothing had ever exercised them end to end, so
this file does: every type renders to every backend, survives a legend, and
autoscales to the data it actually draws.
"""

from __future__ import annotations

import math
import random

import pytest

import pyplotrs as plt

FORMATS = ("pdf", "svg", "png")


def _grid(k: int = 12):
    return [[math.sin(i / 3) * math.cos(j / 3) for j in range(k)] for i in range(k)]


def _cloud(n: int = 800):
    rng = random.Random(0)
    return ([rng.gauss(0, 1) for _ in range(n)], [rng.gauss(0, 1) for _ in range(n)])


_XS = [i / 6 for i in range(20)]
_YS = [math.sin(x) for x in _XS]

#: name -> (builder, labelable). Labelable types are also run through a legend,
#: which is a separate dispatch with a per-kind glyph branch.
CASES = {
    "step": (lambda ax: ax.step(_XS, _YS, label="s"), True),
    "step_post": (lambda ax: ax.step(_XS, _YS, where="post"), False),
    "step_mid": (lambda ax: ax.step(_XS, _YS, where="mid"), False),
    "stairs": (lambda ax: ax.stairs([1, 3, 2, 4], label="s"), True),
    "stairs_fill": (lambda ax: ax.stairs([1, 3, 2, 4], fill=True, label="s"), True),
    "stairs_edges": (lambda ax: ax.stairs([1, 3, 2], edges=[0, 1, 4, 5]), False),
    "stem": (lambda ax: ax.stem(_XS[:8], _YS[:8], label="s"), True),
    "broken_barh": (lambda ax: ax.broken_barh([(0, 1), (2, 1.5)], (0.5, 0.4)), False),
    "eventplot": (lambda ax: ax.eventplot([[1, 2, 3], [1.5, 2.5]]), False),
    "eventplot_1d": (lambda ax: ax.eventplot([1.0, 2.0, 3.0]), False),
    "eventplot_vertical": (
        lambda ax: ax.eventplot([[1, 2]], orientation="vertical"), False),
    "hist2d": (lambda ax: ax.hist2d(*_cloud(), bins=12), False),
    "hexbin": (lambda ax: ax.hexbin(*_cloud(), gridsize=10), False),
    "pcolormesh": (lambda ax: ax.pcolormesh(_grid()), False),
    "contour": (lambda ax: ax.contour(_grid()), False),
    "contourf": (lambda ax: ax.contourf(_grid()), False),
    "hlines": (lambda ax: ax.hlines([1, 2], 0, 5, label="h"), True),
    "vlines": (lambda ax: ax.vlines([1, 2], 0, 5, label="v"), True),
    "fill_betweenx": (
        lambda ax: ax.fill_betweenx([0, 1, 2], [0, 1, 2], [1, 2, 3], label="f"), True),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_renders_to_every_backend(name, tmp_path):
    build, _ = CASES[name]
    fig, ax = plt.subplots(figsize=(240, 180))
    build(ax)
    ax.set(title=name, xlabel="x", ylabel="y")
    for fmt in FORMATS:
        out = tmp_path / f"{name}.{fmt}"
        fig.save(str(out))
        assert out.stat().st_size > 200, f"{fmt}: suspiciously small"


@pytest.mark.parametrize("name", sorted(n for n, (_, lab) in CASES.items() if lab))
def test_labelled_types_survive_a_legend(name, tmp_path):
    build, _ = CASES[name]
    fig, ax = plt.subplots(figsize=(240, 180))
    build(ax)
    ax.legend()
    fig.save(str(tmp_path / f"{name}.png"))


# -- autoscaling -------------------------------------------------------------

def test_hlines_and_vlines_autoscale_to_data():
    """Unlike axhline/axvline, which are axes-fraction guides, these are data."""
    fig, ax = plt.subplots()
    ax.hlines([1.0, 3.0], 0.0, 5.0)
    (xlo, xhi), (ylo, yhi) = ax._ranges()
    assert xlo <= 0.0 and xhi >= 5.0
    assert ylo <= 1.0 and yhi >= 3.0


def test_axhline_still_does_not_autoscale():
    """The distinction matters: a guide must not stretch the view."""
    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1])
    ax.axhline(500.0)
    _, (ylo, yhi) = ax._ranges()
    assert yhi < 100.0, "axhline should not have pulled the y range to 500"


def test_fill_betweenx_is_the_transpose_of_fill_between():
    """Swapping the roles of x and y must swap the ranges, not produce the same
    figure - the two share a mark kind and are told apart by an orientation."""
    fig, ax = plt.subplots()
    ax.fill_between([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])
    (bx, by) = ax._ranges()

    fig2, ax2 = plt.subplots()
    ax2.fill_betweenx([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])
    (bx2, by2) = ax2._ranges()

    assert by2[1] < bx2[1], "fill_betweenx should span x, not y"
    assert by[1] > bx[1], "fill_between should span y, not x"


def test_broadcasting_scalars():
    """A scalar position or bound broadcasts against the other arguments."""
    fig, ax = plt.subplots()
    ax.hlines(1.0, 0.0, 5.0)
    ax.vlines([1.0, 2.0, 3.0], 0.0, 4.0)
    (xlo, xhi), (ylo, yhi) = ax._ranges()
    assert xhi >= 5.0 and yhi >= 4.0


# -- the field family --------------------------------------------------------

def test_pcolormesh_regular_grid_uses_the_image_path(tmp_path):
    """A uniform grid should route to the Rust image path, which produces one
    image node rather than one quad per cell."""
    fig, ax = plt.subplots(figsize=(200, 160))
    ax.pcolormesh(_grid())
    kinds = [m["kind"] for m in ax._marks]
    assert kinds == ["image"], f"expected the image fast path, got {kinds}"


def test_pcolormesh_irregular_grid_falls_back_to_quads():
    xc = [0.0, 1.0, 4.0]           # deliberately non-uniform
    yc = [0.0, 1.0, 2.0]
    Z = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]
    fig, ax = plt.subplots()
    ax.pcolormesh(xc, yc, Z)
    assert [m["kind"] for m in ax._marks] == ["quadmesh"]


def test_contour_levels_are_honoured():
    fig, ax = plt.subplots()
    ax.contour(_grid(), levels=[-0.5, 0.0, 0.5])
    mark = ax._marks[0]
    assert mark["kind"] == "contour"
    assert len(mark["colors"]) == 3


def test_hist2d_returns_a_mappable_for_the_colorbar(tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180))
    mappable = ax.hist2d(*_cloud(), bins=10)
    fig.colorbar(mappable, label="count")
    fig.save(str(tmp_path / "cb.png"))


def test_hexbin_returns_a_mappable_for_the_colorbar(tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180))
    mappable = ax.hexbin(*_cloud(), gridsize=8)
    fig.colorbar(mappable, label="count")
    fig.save(str(tmp_path / "cb.png"))


def test_step_where_variants_differ():
    """`pre`/`post`/`mid` must actually produce different geometry."""
    seen = set()
    for where in ("pre", "post", "mid"):
        fig, ax = plt.subplots()
        ax.step([0.0, 1.0, 2.0], [0.0, 1.0, 0.0], where=where)
        seen.add(tuple(ax._marks[0]["ys"]))
    assert len(seen) == 3, "step `where` variants produced identical geometry"


def test_removed_helpers_are_gone():
    """`_streamlines`/`_bilerp` served only `streamplot`, which is not coming
    back, and `_resolve_color` duplicated the theme. Keeping dead code around is
    what let three 3D methods stay broken for a month unnoticed."""
    from pyplotrs import figure

    for name in ("_streamlines", "_bilerp", "_resolve_color"):
        assert not hasattr(figure, name), f"{name} is dead code and should be removed"
