"""API consistency: one name per concept, one unit per quantity.

The library's pitch includes "a better API than matplotlib", but it had
inherited matplotlib's worst naming collision and added one of its own:
``width`` meant a stroke width, a bar's thickness in data units, *and* a bar's
value, while marker size was an area on ``scatter`` and a diameter on
``line``. These tests pin the resolved vocabulary so it cannot drift back.
"""

from __future__ import annotations

import inspect

import pytest

import pyplotrs as plt
from pyplotrs.figure import Axes, Axes3D, PolarAxes, _AxesBase


# -- one name per concept ----------------------------------------------------

#: Methods that draw a stroke and must therefore spell its width `linewidth`.
_STROKE_METHODS = [
    "line", "errorbar", "step", "stairs", "hlines", "vlines",
    "axhline", "axvline", "axline", "contour",
    "rectangle", "circle", "ellipse", "polygon", "arrow",
]

#: Of those, the ones that have no data-space extent of their own - so a bare
#: `width` on them could only ever mean the stroke, and must be gone.
_STROKE_ONLY = [
    "line", "errorbar", "step", "stairs", "hlines", "vlines",
    "axhline", "axvline", "axline", "contour", "polygon", "arrow",
]


@pytest.mark.parametrize("name", _STROKE_METHODS)
def test_stroke_width_is_always_called_linewidth(name):
    params = inspect.signature(getattr(Axes, name)).parameters
    assert "linewidth" in params, f"Axes.{name} should spell its stroke `linewidth`"


@pytest.mark.parametrize("name", _STROKE_ONLY)
def test_bare_width_is_gone_where_it_could_only_mean_a_stroke(name):
    params = inspect.signature(getattr(Axes, name)).parameters
    assert "width" not in params, (
        f"Axes.{name} still takes `width`; that name is reserved for data-space extent"
    )


def test_shapes_carry_both_names_with_distinct_meanings():
    """`rectangle(xy, width, height, linewidth=...)` is the vocabulary working:
    `width` is the shape's extent in data units, `linewidth` is its outline."""
    for name in ("rectangle", "ellipse"):
        params = inspect.signature(getattr(Axes, name)).parameters
        assert "width" in params and "linewidth" in params


@pytest.mark.parametrize("cls,name", [
    (Axes3D, "plot"), (Axes3D, "plot_wireframe"), (Axes3D, "contour3d"),
    (Axes3D, "quiver3d"), (PolarAxes, "plot"),
])
def test_stroke_width_is_linewidth_on_3d_and_polar(cls, name):
    params = inspect.signature(getattr(cls, name)).parameters
    assert "linewidth" in params and "width" not in params


@pytest.mark.parametrize("name", ["bar", "barh", "rectangle", "ellipse"])
def test_width_survives_only_where_it_means_data_extent(name):
    """`width` is not banned - it is reserved. On a bar it is the bar's
    thickness in data units, which is the one thing it should ever mean."""
    assert "width" in inspect.signature(getattr(Axes, name)).parameters


# -- one unit per quantity ---------------------------------------------------

@pytest.mark.parametrize("cls", [Axes, Axes3D, PolarAxes])
def test_scatter_takes_markersize(cls):
    params = inspect.signature(cls.scatter).parameters
    assert "markersize" in params


def test_markersize_is_a_diameter_and_size_is_an_area():
    """matplotlib spells this two ways; pyplotrs settles on diameter but keeps
    accepting `size` as an area so ported code draws the right thing rather
    than 36 pt blobs."""
    fig, ax = plt.subplots()
    ax.scatter([0], [0], size=36.0)
    ax.scatter([0], [0], markersize=6.0)
    assert ax._marks[0]["markersize"] == pytest.approx(6.0)
    assert ax._marks[1]["markersize"] == pytest.approx(6.0)


def test_markersize_wins_when_both_are_given():
    fig, ax = plt.subplots()
    ax.scatter([0], [0], markersize=3.0, size=400.0)
    assert ax._marks[0]["markersize"] == pytest.approx(3.0)


def test_line_and_scatter_agree_on_marker_size():
    """The whole point of the change: the same number means the same size."""
    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1], marker="o", markersize=7.0)
    ax.scatter([0], [0], markersize=7.0)
    assert ax._marks[0]["markersize"] == ax._marks[1]["markersize"]


# -- alpha on every mark -----------------------------------------------------

_ALPHA_METHODS = [
    "line", "scatter", "bar", "barh", "hist", "errorbar", "fill_between",
    "fill_betweenx", "step", "stairs", "stem", "hlines", "vlines",
]


@pytest.mark.parametrize("name", _ALPHA_METHODS)
def test_alpha_is_accepted(name):
    assert "alpha" in inspect.signature(getattr(Axes, name)).parameters, (
        f"Axes.{name} should accept alpha"
    )


@pytest.mark.parametrize("name,call", [
    ("line", lambda ax, a: ax.line([0, 1], [0, 1], alpha=a)),
    ("bar", lambda ax, a: ax.bar([0], [1], alpha=a)),
    ("barh", lambda ax, a: ax.barh([0], [1], alpha=a)),
    ("hist", lambda ax, a: ax.hist([1, 2, 2, 3], alpha=a)),
    ("scatter", lambda ax, a: ax.scatter([0], [0], alpha=a)),
    ("step", lambda ax, a: ax.step([0, 1], [0, 1], alpha=a)),
    ("stem", lambda ax, a: ax.stem([0, 1], [0, 1], alpha=a)),
    ("hlines", lambda ax, a: ax.hlines([0], 0, 1, alpha=a)),
])
def test_alpha_reaches_the_marks_colour(name, call):
    """Opacity is folded into the mark's RGBA, so it needs no separate plumbing
    through the draw branches - but it does have to actually be folded in."""
    fig, ax = plt.subplots()
    call(ax, 0.4)
    colours = [m["color"] for m in ax._marks if "color" in m]
    assert colours, f"{name} recorded no colour"
    assert all(c[3] < 255 for c in colours), f"{name} ignored alpha: {colours}"


def test_alpha_of_one_leaves_the_colour_untouched():
    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1], alpha=1.0)
    assert ax._marks[0]["color"][3] == 255


def test_alpha_reaches_the_svg(tmp_path):
    fig, ax = plt.subplots(figsize=(200, 150))
    ax.line([0, 1], [0, 1], alpha=0.4, linewidth=6)
    out = tmp_path / "a.svg"
    fig.save(str(out))
    assert "stroke-opacity" in out.read_text()


# -- the shared axes base ----------------------------------------------------

@pytest.mark.parametrize("cls", [Axes, Axes3D, PolarAxes])
def test_every_axes_class_shares_the_base(cls):
    assert issubclass(cls, _AxesBase)


@pytest.mark.parametrize("cls", [Axes, Axes3D, PolarAxes])
def test_colour_cycle_is_defined_once(cls):
    """`_next_color` was written out three times byte-identically, which is how
    a fix to one copy could silently miss the others."""
    assert cls._next_color is _AxesBase._next_color


@pytest.mark.parametrize("cls", [Axes, Axes3D, PolarAxes])
def test_legend_is_defined_once(cls):
    assert cls.legend is _AxesBase.legend


def test_legend_default_position_is_per_class():
    """2D can search for a clear corner; 3D and polar fill their cell, so they
    pin one."""
    assert Axes._LEGEND_DEFAULT_LOC == "best"
    assert Axes3D._LEGEND_DEFAULT_LOC == "upper right"
    assert PolarAxes._LEGEND_DEFAULT_LOC == "upper right"

    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1], label="a")
    ax.legend()
    assert ax._legend["loc"] == "best"


def test_colour_cycle_advances_once_per_mark():
    fig, ax = plt.subplots()
    for _ in range(3):
        ax.line([0, 1], [0, 1])
    colours = [m["color"] for m in ax._marks]
    assert len(set(colours)) == 3, f"cycle did not advance: {colours}"


def test_explicit_colour_does_not_consume_the_cycle():
    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1], color="red")
    ax.line([0, 1], [0, 1])
    assert ax._marks[1]["color"] == plt.themes.default.palette[0]


def test_figure_legend_includes_every_projection(tmp_path):
    """The figure legend read `_marks` directly, so 3D panels - which keep their
    marks in `_marks3` - were silently skipped."""
    fig = plt.figure(figsize=(600, 240))
    gs = fig.add_gridspec(1, 3)
    fig.add_subplot(gs[0, 0]).line([0, 1], [0, 1], label="2D")
    fig.add_subplot(gs[0, 1], projection="3d").plot([0, 1], [0, 1], [0, 1], label="3D")
    fig.add_subplot(gs[0, 2], projection="polar").plot([0, 1], [1, 2], label="polar")
    fig.legend()
    labels = [e["label"] for e in fig._figure_legend_entries()]
    assert labels == ["2D", "3D", "polar"]
    fig.save(str(tmp_path / "leg.png"))


def test_2d_legend_entries_keep_their_kind():
    """`Axes` must not inherit the 3D/polar normalizer, which flattens every
    mark to a line and would turn bar swatches into rules."""
    fig, ax = plt.subplots()
    ax.bar(["a"], [1], label="bars")
    ax.line([0, 1], [0, 1], label="line")
    kinds = [e["kind"] for e in ax._legend_entries()]
    assert kinds == ["bar", "line"]


# -- legend(loc="best") ------------------------------------------------------

@pytest.mark.parametrize("name,ys,expect_left,expect_top", [
    # A rising line clears the upper left; a falling one clears the upper right.
    ("rising", [i / 20 for i in range(21)], True, True),
    ("falling", [1 - i / 20 for i in range(21)], False, True),
])
def test_best_picks_a_corner_clear_of_the_data(name, ys, expect_left, expect_top):
    """`best` used to be a plain alias for `upper right`, so it happily sat on
    top of a rising line."""
    xs = [i / 20 for i in range(21)]
    fig, ax = plt.subplots(figsize=(300, 220))
    ax.line(xs, ys, label=name)
    ax.legend()

    positions = {
        "upper right": (100.0, 0.0), "upper left": (0.0, 0.0),
        "lower right": (100.0, 100.0), "lower left": (0.0, 100.0),
        "upper center": (50.0, 0.0), "lower center": (50.0, 100.0),
    }

    class _P:
        sx = staticmethod(lambda v: v * 100.0)
        sy = staticmethod(lambda v: 100.0 - v * 100.0)

    bx, by = ax._best_legend_position(positions, 30.0, 20.0, _P())
    assert (bx < 50.0) is expect_left, f"{name}: horizontal choice {bx}"
    assert (by < 50.0) is expect_top, f"{name}: vertical choice {by}"


def test_best_falls_back_without_a_projection():
    """Callers that have no projection (a figure-level legend) must still get a
    sane answer rather than an error."""
    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1], label="a")
    positions = {"upper right": (9.0, 9.0), "upper left": (0.0, 0.0),
                 "lower right": (9.0, 0.0), "lower left": (0.0, 9.0),
                 "upper center": (4.0, 0.0), "lower center": (4.0, 9.0)}
    assert ax._best_legend_position(positions, 1.0, 1.0, None) == (9.0, 9.0)


def test_best_probe_is_bounded_regardless_of_data_size():
    """The search runs at draw time, so it must not become an O(n) pass."""
    fig, ax = plt.subplots()
    ax.line(list(range(100_000)), list(range(100_000)), label="big")

    class _P:
        sx = staticmethod(float)
        sy = staticmethod(float)

    from pyplotrs.figure import _LEGEND_PROBE_POINTS
    assert len(ax._sample_device_points(_P())) <= _LEGEND_PROBE_POINTS + 1


def test_explicit_loc_is_still_honoured(tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.line([0, 1], [0, 1], label="a")
    ax.legend(loc="lower right")
    assert ax._legend["loc"] == "lower right"
    fig.save(str(tmp_path / "l.png"))


# -- the theme is the only source of style ------------------------------------

@pytest.mark.parametrize("name", [
    "_BLACK", "_SPINE", "_WHITE", "_COLOR_CYCLE", "_LEGEND_BG", "_LEGEND_BORDER",
    "_LEGEND_SIZE", "_TICK_LABEL_SIZE", "_AXIS_LABEL_SIZE", "_TITLE_SIZE",
    "_SUPTITLE_SIZE",
])
def test_style_constants_do_not_shadow_the_theme(name):
    """`figure.py` used to carry its own copies of the theme's palette, colours
    and type scale, which draw methods shadowed with theme-derived locals. Any
    method that forgot to re-shadow silently drew the module default instead -
    that is how the hardcoded legend swatch size and the white histogram edges
    survived. The copies are gone, so forgetting now raises."""
    from pyplotrs import figure

    assert not hasattr(figure, name), (
        f"{name} duplicates theme.py and invites the shadowing bug it caused before"
    )


def test_polar_rim_follows_the_theme(tmp_path):
    """The outer spine circle read a module constant, so it ignored the theme."""
    theme = plt.themes.default.with_(spine_color=(200, 30, 30, 255), spine_width=3.0)
    fig, ax = plt.subplots(figsize=(240, 240), projection="polar", theme=theme)
    ax.plot([0, 1, 2, 3], [1, 2, 1, 2])
    out = tmp_path / "p.svg"
    fig.save(str(out))
    svg = out.read_text().lower()
    assert "#c81e1e" in svg, "polar rim ignored the theme's spine colour"


def test_colormapped_scatter_placeholder_follows_the_theme():
    """Its per-point colours replace this, but it is still the legend swatch."""
    theme = plt.themes.default.with_(text_color=(10, 20, 30, 255))
    fig, ax = plt.subplots(theme=theme)
    ax.scatter([0, 1], [0, 1], c=[0.0, 1.0])
    assert ax._marks[0]["color"] == (10, 20, 30, 255)


# -- zorder ------------------------------------------------------------------

_ZORDER_METHODS = [
    "line", "scatter", "bar", "barh", "hist", "errorbar", "fill_between",
    "fill_betweenx", "step", "stairs", "stem", "hlines", "vlines", "pie",
]


@pytest.mark.parametrize("name", _ZORDER_METHODS)
def test_zorder_is_accepted(name):
    """All or nothing: a styling knob on only some marks is the inconsistency
    this phase exists to remove."""
    assert "zorder" in inspect.signature(getattr(Axes, name)).parameters


def test_default_zorder_preserves_insertion_order():
    """Insertion order is the primary model - it is the one you can read off the
    code - so the sort must be stable and a no-op when nobody sets zorder."""
    fig, ax = plt.subplots()
    for i in range(5):
        ax.line([0, 1], [i, i])
    assert ax._ordered_marks() == ax._marks


def test_zorder_lifts_a_mark_above_later_ones():
    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1], zorder=2)          # added first, drawn last
    ax.fill_between([0, 1], [0, 1], 0, zorder=1)
    order = [m["kind"] for m in ax._ordered_marks()]
    assert order == ["fill", "line"]


def test_zorder_ties_keep_insertion_order():
    fig, ax = plt.subplots()
    ax.bar([0], [1], zorder=1)
    ax.line([0, 1], [0, 1], zorder=1)
    ax.scatter([0], [0], zorder=1)
    assert [m["kind"] for m in ax._ordered_marks()] == ["bar", "line", "scatter"]


def test_zorder_changes_the_rendered_output(tmp_path):
    def render(name, line_z, fill_z):
        fig, ax = plt.subplots(figsize=(240, 180))
        ax.line([0, 1, 2], [0, 2, 1], linewidth=6, zorder=line_z)
        ax.fill_between([0, 1, 2], [0, 2, 1], 0, alpha=1.0, color="C1", zorder=fill_z)
        out = tmp_path / f"{name}.png"
        fig.save(str(out))
        return out.read_bytes()

    assert render("line_on_top", 2, 1) != render("fill_on_top", 1, 2)
