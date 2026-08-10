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
from pyplotrs.axes import Axes, _AxesBase
from pyplotrs.axes3d import Axes3D
from pyplotrs.polar import PolarAxes


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

    from pyplotrs._const import _LEGEND_PROBE_POINTS
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


# -- polar marks are 2D marks and take zorder too -----------------------------
#
# `PolarAxes.plot`/`scatter` took `label` and `alpha` but not `zorder`, and drew
# straight from `self._marks` in insertion order - the only 2D marks outside the
# contract, and undocumented as an exception. `_ordered_marks` was already
# inherited from `_AxesBase`; polar simply never called it.

@pytest.mark.parametrize("name", ["plot", "scatter"])
def test_polar_marks_take_zorder(name):
    assert "zorder" in inspect.signature(getattr(PolarAxes, name)).parameters


def test_polar_zorder_lifts_a_mark_above_later_ones():
    fig, ax = plt.subplots(projection="polar")
    ax.plot([0, 1], [1, 2], zorder=2)          # added first, drawn last
    ax.scatter([0, 1], [1, 2], zorder=1)
    assert [m["kind"] for m in ax._ordered_marks()] == ["scatter", "line"]


def test_polar_default_zorder_preserves_insertion_order():
    fig, ax = plt.subplots(projection="polar")
    for i in range(4):
        ax.plot([0, 1], [i, i + 1])
    assert ax._ordered_marks() == ax._marks


def test_polar_zorder_changes_the_rendered_output(tmp_path):
    def render(name, z):
        fig, ax = plt.subplots(figsize=(220, 170), projection="polar")
        ax.plot([0, 1, 2, 3], [1, 2, 3, 4], color="red", linewidth=8, zorder=z)
        ax.plot([0, 1, 2, 3], [4, 3, 2, 1], color="blue", linewidth=8)
        out = tmp_path / f"{name}.png"
        fig.save(str(out))
        return out.read_bytes()

    assert render("red_under", 0) != render("red_over", 5)


# -- the contract is universal, not just for the marks Phase 5 touched --------
#
# Phase 5 gave `zorder`/`alpha`/`label` to the eleven marks that existed at the
# time. Ten more were restored from the parked set in the same window and did
# not get them, so a boxplot could not carry a legend key and an `imshow` could
# not be made translucent. These tests pin the contract over *every* mark, so
# restoring or adding a plot type cannot quietly opt out of it again.

#: Every mark-producing method on `Axes`.
_ALL_MARKS = [
    "line", "scatter", "bar", "barh", "hist", "fill_between", "fill_betweenx",
    "hlines", "vlines", "errorbar", "boxplot", "violinplot", "pie", "imshow",
    "step", "stairs", "stem", "broken_barh", "eventplot", "hist2d", "hexbin",
    "pcolormesh", "contour", "contourf",
]


@pytest.mark.parametrize("name", _ALL_MARKS)
def test_every_mark_takes_zorder(name):
    assert "zorder" in inspect.signature(getattr(Axes, name)).parameters


@pytest.mark.parametrize("name", _ALL_MARKS)
def test_every_mark_takes_alpha(name):
    assert "alpha" in inspect.signature(getattr(Axes, name)).parameters


@pytest.mark.parametrize("name", [n for n in _ALL_MARKS if n != "pie"])
def test_every_mark_takes_label(name):
    """`pie` is the sole exception, and deliberately: its labels are per-wedge,
    so it spells them `labels` and those are what reach the legend."""
    assert "label" in inspect.signature(getattr(Axes, name)).parameters


_LABELLED = [
    ("boxplot", lambda ax: ax.boxplot([[1, 2, 3, 4, 9]], label="L")),
    ("violinplot", lambda ax: ax.violinplot([[1, 2, 2, 3, 4]], label="L")),
    ("imshow", lambda ax: ax.imshow([[1, 2], [3, 4]], label="L")),
    ("eventplot", lambda ax: ax.eventplot([[1, 2, 3]], label="L")),
    ("hist2d", lambda ax: ax.hist2d([1, 2, 3], [1, 2, 3], bins=2, label="L")),
    ("hexbin", lambda ax: ax.hexbin([1, 2, 3], [1, 2, 3], gridsize=3, label="L")),
    ("pcolormesh", lambda ax: ax.pcolormesh([[1, 2], [3, 9]], label="L")),
    ("contour", lambda ax: ax.contour([[1, 2], [3, 4]], label="L")),
    ("contourf", lambda ax: ax.contourf([[1, 2], [3, 4]], label="L")),
    ("broken_barh", lambda ax: ax.broken_barh([(0, 2)], (0, 1), label="L")),
]


@pytest.mark.parametrize("name,call", _LABELLED)
def test_a_labelled_mark_produces_a_legend_entry(name, call):
    fig, ax = plt.subplots()
    call(ax)
    assert len(ax._legend_entries()) == 1, f"{name} label did not reach the legend"


@pytest.mark.parametrize("name,call", _LABELLED)
@pytest.mark.parametrize("ext", ["png", "svg", "pdf"])
def test_a_labelled_mark_renders_its_legend(name, call, ext, tmp_path):
    """The legend glyph drawer has per-kind branches; a kind it does not know
    used to raise mid-render rather than degrade."""
    fig, ax = plt.subplots(figsize=(240, 180))
    call(ax)
    ax.legend()
    fig.save(str(tmp_path / f"{name}.{ext}"))


def test_pie_wedges_become_one_legend_entry_each():
    fig, ax = plt.subplots()
    ax.pie([1, 2, 3], labels=["a", "b", "c"])
    assert [e["label"] for e in ax._legend_entries()] == ["a", "b", "c"]


# -- the contract, checked by behaviour rather than by signature --------------
#
# Every audit so far has found the same bug: a contract that held for the marks
# it was written against and silently missed the ones added afterwards. Phase 5
# missed the ten restored beside it; Phase 6b missed the seven 3D marks; Phase
# 7a's six new 2D types were never folded into the lists above.
#
# `inspect.signature` cannot close that hole, because it is wrong in *both*
# directions. It reports a gap where there is none - `pcolor`/`matshow` forward
# `**kwargs`, and `stackplot` spells it `labels` - and it reports success where
# the value is accepted and then dropped, which is exactly how
# `Axes3D.plot(alpha=)` and the 3D `label=` + `legend()` crash both survived.
# So the tests below call every mark and look at what comes out, and
# `test_every_public_axes_method_is_classified` makes it impossible to add a
# thirty-first mark without deciding whether the contract applies to it.

#: How to call each mark with the smallest data that draws something.
_MARK_CALLS = {
    "bar": lambda ax, **k: ax.bar([0, 1, 2], [1, 2, 3], **k),
    "barh": lambda ax, **k: ax.barh([0, 1, 2], [1, 2, 3], **k),
    "boxplot": lambda ax, **k: ax.boxplot([[1, 2, 3, 4, 9]], **k),
    "broken_barh": lambda ax, **k: ax.broken_barh([(0, 2)], (0, 1), **k),
    "contour": lambda ax, **k: ax.contour([[1, 2], [3, 4]], **k),
    "contourf": lambda ax, **k: ax.contourf([[1, 2], [3, 4]], **k),
    "errorbar": lambda ax, **k: ax.errorbar([0, 1, 2], [1, 2, 3], yerr=[0.2] * 3, **k),
    "eventplot": lambda ax, **k: ax.eventplot([[1, 2, 3]], **k),
    "fill_between": lambda ax, **k: ax.fill_between([0, 1, 2], [1, 2, 3], 0, **k),
    "fill_betweenx": lambda ax, **k: ax.fill_betweenx([0, 1, 2], [1, 2, 3], 0, **k),
    "hexbin": lambda ax, **k: ax.hexbin([1, 2, 3], [1, 2, 3], gridsize=3, **k),
    "hist": lambda ax, **k: ax.hist([1, 2, 2, 3, 3, 3], **k),
    "hist2d": lambda ax, **k: ax.hist2d([1, 2, 3], [1, 2, 3], bins=2, **k),
    "hlines": lambda ax, **k: ax.hlines([1, 2], 0, 1, **k),
    "imshow": lambda ax, **k: ax.imshow([[1, 2], [3, 9]], **k),
    "line": lambda ax, **k: ax.line([0, 1, 2], [0, 2, 1], **k),
    "matshow": lambda ax, **k: ax.matshow([[1, 2], [3, 9]], **k),
    "pcolor": lambda ax, **k: ax.pcolor([[1, 2], [3, 9]], **k),
    "pcolormesh": lambda ax, **k: ax.pcolormesh([[1, 2], [3, 9]], **k),
    "pie": lambda ax, **k: ax.pie([1, 2, 3], **k),
    "quiver": lambda ax, **k: ax.quiver([0, 1], [0, 1], [1, 1], [1, 0], **k),
    "scatter": lambda ax, **k: ax.scatter([0, 1, 2], [0, 2, 1], **k),
    "spy": lambda ax, **k: ax.spy([[1, 0], [0, 1]], **k),
    "stackplot": lambda ax, **k: ax.stackplot([0, 1, 2], [1, 2, 3], **k),
    "stairs": lambda ax, **k: ax.stairs([1, 2, 3], [0, 1, 2, 3], **k),
    "stem": lambda ax, **k: ax.stem([0, 1, 2], [1, 2, 3], **k),
    "step": lambda ax, **k: ax.step([0, 1, 2], [1, 2, 3], **k),
    "streamplot": lambda ax, **k: ax.streamplot(
        [0, 1, 2], [0, 1, 2], [[1] * 3] * 3, [[1] * 3] * 3, **k),
    "violinplot": lambda ax, **k: ax.violinplot([[1, 2, 2, 3, 4]], **k),
    "vlines": lambda ax, **k: ax.vlines([1, 2], 0, 1, **k),
}

#: Public `Axes` methods that are deliberately *not* marks, and so sit outside
#: the zorder/alpha/label contract. Grouped by why.
_NOT_MARKS = frozenset({
    # Patches: drawn over the data, documented as outside the contract.
    "polygon", "rectangle", "circle", "ellipse", "fill",
    # Annotations and reference lines.
    "text", "annotate", "arrow",
    "axhline", "axvline", "axline", "axhspan", "axvspan",
    # Axis and figure plumbing.
    "axis", "set", "legend", "inset_axes", "twinx", "twiny",
    "secondary_xaxis", "secondary_yaxis",
    # Scale wrappers over `set(xscale=)` + `line()`.
    "loglog", "semilogx", "semilogy",
    # Readers.
    "get_aspect", "get_legend_handles_labels", "get_title", "get_xlabel",
    "get_xlim", "get_xscale", "get_xticklabels", "get_xticks", "get_ylabel",
    "get_ylim", "get_yscale", "get_yticklabels", "get_yticks",
})

#: `pie` spells its labels per-wedge and `stackplot` per-series; both have their
#: own legend tests below. Every other mark takes a singular `label`.
_NO_SINGULAR_LABEL = {"pie", "stackplot"}


def test_every_public_axes_method_is_classified():
    """Adding a mark must be a decision, not an omission.

    Each audit found new marks that had quietly skipped the contract because
    nothing forced anyone to look. A new public method now fails here until it
    is either registered in `_MARK_CALLS` - which subjects it to every test
    below - or listed in `_NOT_MARKS` with a reason.
    """
    public = {n for n in dir(Axes)
              if not n.startswith("_") and callable(getattr(Axes, n))}

    unclassified = public - set(_MARK_CALLS) - _NOT_MARKS
    assert not unclassified, (
        f"unclassified public Axes method(s): {sorted(unclassified)}. If this is "
        f"a mark, add it to _MARK_CALLS so the alpha/label/zorder contract is "
        f"enforced on it; if not, add it to _NOT_MARKS with a reason."
    )
    stale = (set(_MARK_CALLS) | _NOT_MARKS) - public
    assert not stale, f"these no longer exist on Axes: {sorted(stale)}"


@pytest.mark.parametrize("name", sorted(_MARK_CALLS))
def test_every_mark_records_a_mark(name):
    """Grounds the classification: a `_MARK_CALLS` entry that draws nothing
    would make every other test in this section vacuous."""
    fig, ax = plt.subplots()
    _MARK_CALLS[name](ax)
    assert ax._marks, f"{name} recorded no mark"


@pytest.mark.parametrize("name", sorted(_MARK_CALLS))
def test_alpha_is_applied_not_merely_accepted(name, tmp_path):
    """Render at two alphas and compare bytes.

    Accepting the keyword proves nothing: the colormapped kinds have no single
    colour to fold it into, so it has to ride their LUT or their colour list,
    and a mark that takes `alpha` and drops it looks identical to one that
    honours it until you actually rasterize both.
    """
    def render(a):
        fig, ax = plt.subplots(figsize=(180, 140))
        _MARK_CALLS[name](ax, alpha=a)
        out = tmp_path / f"{name}_{a}.png"
        fig.save(str(out))
        return out.read_bytes()

    assert render(1.0) != render(0.25), f"{name} accepted alpha but ignored it"


@pytest.mark.parametrize("name", sorted(set(_MARK_CALLS) - _NO_SINGULAR_LABEL))
def test_every_mark_label_reaches_the_legend(name):
    fig, ax = plt.subplots()
    _MARK_CALLS[name](ax, label="L")
    assert "L" in ax.get_legend_handles_labels()[1], (
        f"{name} accepted label= but it never reached the legend"
    )


@pytest.mark.parametrize("name", sorted(set(_MARK_CALLS) - _NO_SINGULAR_LABEL))
def test_every_labelled_mark_renders_its_legend(name, tmp_path):
    """`surface(label=...)` + `legend()` raised `KeyError: 'color'` for a whole
    release because no test drew the legend it had just asked for."""
    fig, ax = plt.subplots(figsize=(180, 140))
    _MARK_CALLS[name](ax, label="L")
    ax.legend()
    fig.save(str(tmp_path / f"{name}.png"))


@pytest.mark.parametrize("name", sorted(_MARK_CALLS))
def test_every_mark_honours_zorder(name):
    fig, ax = plt.subplots()
    _MARK_CALLS[name](ax, zorder=3)
    assert all(m["zorder"] == 3 for m in ax._marks), f"{name} dropped zorder"


def test_stackplot_labels_each_series():
    fig, ax = plt.subplots()
    ax.stackplot([0, 1, 2], [1, 2, 3], [2, 1, 2], labels=["a", "b"])
    assert ax.get_legend_handles_labels()[1] == ["a", "b"]


# -- one key per concept, inside the mark dict too ----------------------------

def test_the_mark_dict_never_stores_a_stroke_under_width():
    """The public signatures split `linewidth` from `width`, but the internal
    mark contract kept both under `"width"` - the same collision, one layer
    down, disambiguated only by `kind`. `width` is now the data-space extent
    everywhere and the stroke is always `linewidth`."""
    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1], linewidth=3.0)
    ax.errorbar([0, 1], [0, 1], yerr=0.1, linewidth=3.0)
    ax.eventplot([[1, 2]], linewidth=3.0)
    ax.contour([[1, 2], [3, 4]], linewidth=3.0)
    for m in ax._marks:
        assert m.get("linewidth") == pytest.approx(3.0), m["kind"]
        assert "width" not in m, f"{m['kind']} still stores a stroke as `width`"


def test_width_in_the_mark_dict_is_always_a_data_extent():
    fig, ax = plt.subplots()
    ax.bar([0], [1], width=0.5)
    ax.boxplot([[1, 2, 3]], widths=0.4)
    ax.violinplot([[1, 2, 3]], widths=0.4)
    extents = [m["width"] for m in ax._marks]
    assert extents == [0.5, 0.4, 0.4]
    assert all(e < 1.0 for e in extents)  # data units here, never points


# -- the theme reaches every stroke -------------------------------------------

@pytest.mark.parametrize("name,call", [
    ("line", lambda ax: ax.line([0, 1], [0, 1])),
    ("errorbar", lambda ax: ax.errorbar([0, 1], [0, 1], yerr=0.1)),
    ("eventplot", lambda ax: ax.eventplot([[1, 2]])),
    ("contour", lambda ax: ax.contour([[1, 2], [3, 4]])),
    ("step", lambda ax: ax.step([0, 1], [0, 1])),
    ("stairs", lambda ax: ax.stairs([1, 2])),
    ("hlines", lambda ax: ax.hlines([0], 0, 1)),
])
def test_theme_line_width_reaches_every_stroke_mark(name, call):
    """`errorbar`, `eventplot` and `contour` hardcoded their stroke, so a theme
    could not restyle them - the same leak Phase 5 found in the style
    constants, in the marks it did not touch."""
    fig, ax = plt.subplots(theme=plt.Theme(line_width=6.0))
    call(ax)
    assert ax._marks[0]["linewidth"] == pytest.approx(6.0), (
        f"{name} ignored theme.line_width"
    )


# -- one idiom for writing ----------------------------------------------------

def test_polar_has_no_individual_setters():
    """`PolarAxes` used to carry seven matplotlib-style `set_*` wrappers while
    `Axes` and `Axes3D` had none, so polar code read differently from every
    other panel. Writing is `set(**kwargs)` everywhere now."""
    leftovers = [n for n in dir(PolarAxes)
                 if n.startswith("set_") and not n.startswith("set__")]
    assert leftovers == [], f"PolarAxes regrew individual setters: {leftovers}"


@pytest.mark.parametrize("cls", [Axes, Axes3D, PolarAxes])
def test_every_axes_class_writes_through_set(cls):
    assert callable(getattr(cls, "set"))


def test_polar_set_still_covers_everything_the_wrappers_did():
    fig, ax = plt.subplots(projection="polar")
    ax.set(title="t", rmin=0.0, rmax=2.0, rticks=[1, 2], thetagrids=[0, 90],
           theta_zero_location="N", theta_direction=-1, rlabel_position=45.0)
    assert ax._rmax == pytest.approx(2.0)
    assert ax._rticks == [1.0, 2.0]
    assert ax._theta_dir == -1
