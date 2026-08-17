"""Where the data stops and the frame begins.

Autoscaling pads the data range by 5% so marks don't collide with the spines.
But some marks don't merely *reach* a value, they *rest on* one: a stacked area
has a floor, a bar has a base, an image has an edge. Padding past those invents
whitespace that reads as "there could be data here", which is false — the
stackplot in the gallery floated 0.6 units above the x spine with a strip of
background beneath it, and the total looked like it started somewhere other
than where it did.

So each mark records the values it rests on and the margin is clamped there
(`_util._clamp_sticky`). These tests pin both halves of that rule: the clamp
happens where a mark has a boundary, and — just as important — it does *not*
happen where the mark merely stopped. The reference numbers were taken from
matplotlib 3.11, which arrives at the same answers by a different route
(per-artist `Artist.sticky_edges`).
"""

from __future__ import annotations

import math

import pyplotrs as pp
import pytest


def _y(ax):
    return ax._ranges()[1]


def _x(ax):
    return ax._ranges()[0]


# -- marks that rest on a baseline -------------------------------------------

def test_stackplot_sits_on_its_floor():
    """The bug this file exists for: no gap under a stacked area."""
    x = list(range(12))
    a = [3, 4, 5, 6, 7, 8, 7, 6, 5, 4, 3, 2]
    b = [2, 2, 3, 3, 4, 4, 5, 5, 4, 4, 3, 3]
    fig, ax = pp.subplots()
    ax.stackplot(x, a, b)
    lo, hi = _y(ax)
    assert lo == 0.0, "the stack must sit flush on the x spine"
    assert hi > sum(v[-1] for v in (a, b)), "the top still gets its margin"


def test_stackplot_sticks_to_its_own_baseline_not_to_zero():
    """matplotlib hardcodes a sticky at literal 0 here (stackplot.py:135), which
    is wrong for any stack that doesn't start there. pyplotrs takes `baseline`
    as a value, so that value is the floor."""
    fig, ax = pp.subplots()
    ax.stackplot(range(5), [1, 2, 3, 2, 1], baseline=100.0)
    assert _y(ax)[0] == 100.0


def test_a_negative_stack_hangs_from_its_floor():
    fig, ax = pp.subplots()
    ax.stackplot(range(5), [-1, -2, -3, -2, -1])
    lo, hi = _y(ax)
    assert hi == 0.0
    assert lo < -3.0


@pytest.mark.parametrize("bottom", [0.0, 10.0, -4.0])
def test_bars_rest_on_their_own_base(bottom):
    """Not on zero: `bar(bottom=10)` used to be forced down to a 0 baseline,
    which squeezed the bars into the top third of an otherwise empty panel."""
    fig, ax = pp.subplots()
    ax.bar([0, 1, 2], [3, 4, 5], bottom=bottom)
    assert _y(ax)[0] == pytest.approx(bottom)


def test_barh_rests_on_its_base_along_x():
    """The value axis of a horizontal bar is x. The old zero-forcing only ever
    looked at y, so barh floated off its baseline in every case."""
    fig, ax = pp.subplots()
    ax.barh([0, 1, 2], [3, 4, 5], left=10.0)
    assert _x(ax)[0] == pytest.approx(10.0)


def test_all_negative_bars_hang_from_the_baseline():
    fig, ax = pp.subplots()
    ax.bar([0, 1, 2], [-3, -4, -5])
    lo, hi = _y(ax)
    assert hi == 0.0
    assert lo < -5.0


def test_mixed_sign_bars_keep_a_margin_at_both_ends():
    """A sticky binds only on the side whose data limit reaches it. Bars that
    straddle their base reach it from neither, so both ends still breathe."""
    fig, ax = pp.subplots()
    ax.bar([0, 1, 2], [-3, 4, -5])
    lo, hi = _y(ax)
    assert lo < -5.0 and hi > 4.0


def test_histogram_counts_rest_on_zero():
    fig, ax = pp.subplots()
    ax.hist([1, 2, 2, 3, 3, 3, 4], bins=4)
    assert _y(ax)[0] == 0.0


@pytest.mark.parametrize("fill", [True, False])
def test_stairs_rests_on_its_baseline(fill):
    fig, ax = pp.subplots()
    ax.stairs([3, 1, 4, 2], baseline=1.0, fill=fill)
    assert _y(ax)[0] == pytest.approx(1.0)


def test_plain_fill_between_is_not_a_baseline():
    """The counter-case, and the reason this can't just special-case `y2`.
    `fill_between(x, y, 0)` has no floor — 0 is just another curve — so it keeps
    its margin. matplotlib sets no sticky here either."""
    fig, ax = pp.subplots()
    ax.fill_between([0, 1, 2], [1.0, 2.0, 3.0], 0.0)
    assert _y(ax)[0] < 0.0


def test_stem_keeps_its_margin():
    """A stem's baseline is drawn but not rested on; matplotlib agrees."""
    fig, ax = pp.subplots()
    ax.stem([0, 1, 2], [3, 4, 5])
    assert _y(ax)[0] < 0.0


# -- marks that cover an extent ----------------------------------------------

def test_an_image_fits_its_extent_exactly():
    fig, ax = pp.subplots()
    ax.imshow([[1, 2], [3, 4]], extent=(0.0, 1.0, 0.0, 1.0))
    assert _x(ax) == (0.0, 1.0)
    assert _y(ax) == (0.0, 1.0)


def test_an_image_does_not_flatten_the_margin_of_other_marks():
    """The old `has_image` was one switch for the whole axes and both
    directions, so a single image stripped the margin from every other mark on
    it. A line running past the image should still get its own 5%."""
    fig, ax = pp.subplots()
    ax.imshow([[1, 2], [3, 4]], extent=(0.0, 1.0, 0.0, 1.0))
    ax.line([-1.0, 3.0], [0.0, 1.0])
    lo, hi = _x(ax)
    assert lo < -1.0 and hi > 3.0


def test_an_image_still_pins_the_axis_it_alone_occupies():
    """Per-axis, not just per-mark: the line above widened x but not y, so y
    stays pinned to the image."""
    fig, ax = pp.subplots()
    ax.imshow([[1, 2], [3, 4]], extent=(0.0, 1.0, 0.0, 4.0))
    ax.line([-1.0, 3.0], [0.0, 4.0])
    assert _y(ax) == (0.0, 4.0)


def test_contour_pins_to_its_grid():
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [0.0, 1.0, 2.0]
    z = [[c * r for c in xs] for r in ys]
    fig, ax = pp.subplots()
    ax.contour(xs, ys, z)
    assert _x(ax) == (0.0, 3.0)
    assert _y(ax) == (0.0, 2.0)


# -- guides ------------------------------------------------------------------

def test_a_guide_is_drawn_inside_the_frame():
    fig, ax = pp.subplots()
    ax.line([0, 1], [0, 1])
    ax.axhline(500.0)
    assert _y(ax)[1] >= 500.0


def test_a_guide_does_not_stretch_the_axis_it_spans():
    """`xmin`/`xmax` on `axhline` are axes fractions, not data."""
    fig, ax = pp.subplots()
    ax.line([0, 1], [0, 1])
    ax.axhline(500.0, xmin=0.2, xmax=0.9)
    assert _x(ax)[1] < 2.0


def test_an_axes_holding_only_a_guide_still_has_both_axes():
    """y comes from the guide; x has nothing to go on and falls back."""
    fig, ax = pp.subplots()
    ax.axhline(5.0)
    (xlo, xhi), (ylo, yhi) = ax._ranges()
    assert xlo < xhi
    assert ylo <= 5.0 <= yhi


# -- margins on every scale --------------------------------------------------

def test_margin_applies_on_a_log_axis():
    """Each scale used to pad itself with a hardcoded 0.05, so `ymargin` was
    silently ignored everywhere except linear: both of these used to return the
    same range."""
    fig, ax = pp.subplots()
    ax.line([1, 2, 3], [1, 10, 100])
    ax.set(yscale="log", ymargin=0)
    assert _y(ax) == pytest.approx((1.0, 100.0))

    fig2, ax2 = pp.subplots()
    ax2.line([1, 2, 3], [1, 10, 100])
    ax2.set(yscale="log", ymargin=0.5)
    assert _y(ax2) == pytest.approx((0.1, 1000.0))


def test_the_log_margin_is_multiplicative():
    """5% of the *decade* span, not of the raw numeric range — the latter would
    be swallowed whole at the low end of a wide log axis."""
    fig, ax = pp.subplots()
    ax.line([1, 2], [1.0, 100.0])
    ax.set(yscale="log")
    lo, hi = _y(ax)
    assert math.log10(1.0 / lo) == pytest.approx(math.log10(hi / 100.0))


def test_an_image_keeps_its_extent_on_a_log_axis():
    """The non-linear path used to re-derive the range from a flat value scan,
    which discarded every mark-aware bound the moment the axis went log."""
    fig, ax = pp.subplots()
    ax.imshow([[1, 2], [3, 4]], extent=(1.0, 100.0, 1.0, 100.0))
    ax.set(xscale="log")
    assert _x(ax) == pytest.approx((1.0, 100.0))


# -- statistical marks -------------------------------------------------------

def test_hidden_fliers_do_not_scale_the_axis():
    """`showfliers=False` hides the outliers; scaling to them anyway squeezed
    the visible box into an eighth of the panel."""
    data = [[1, 2, 3, 4, 5, 6, 7, 8, 9, 40, -20]]
    fig, ax = pp.subplots()
    ax.boxplot(data, showfliers=False)
    lo, hi = _y(ax)
    assert lo > -5.0 and hi < 15.0


def test_shown_fliers_still_scale_the_axis():
    data = [[1, 2, 3, 4, 5, 6, 7, 8, 9, 40, -20]]
    fig, ax = pp.subplots()
    ax.boxplot(data, showfliers=True)
    lo, hi = _y(ax)
    assert lo <= -20.0 and hi >= 40.0


@pytest.mark.parametrize("widths", [0.2, 0.5, 0.9])
def test_the_boxplot_category_axis_does_not_follow_the_box_width(widths):
    """Narrowing the boxes should thin the glyphs, not zoom the axis in on
    them: every width used to fill ~91% of the axis."""
    fig, ax = pp.subplots()
    ax.boxplot([[1, 2, 3, 4, 5]], widths=widths)
    assert _x(ax) == pytest.approx((0.5, 1.5))


def test_a_violin_is_bounded_by_its_data():
    """The KDE was evaluated 15% past each end and the whole grid fed
    autoscaling, then took another 5% on top."""
    sample = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    fig, ax = pp.subplots()
    ax.violinplot([sample])
    lo, hi = _y(ax)
    span = 5.0
    assert lo >= -0.05 * span * 1.01 and hi <= 5.0 + 0.05 * span * 1.01


# -- the margin arithmetic ---------------------------------------------------

@pytest.mark.parametrize("value,half", [(1.0, 0.055), (1000.0, 55.0)])
def test_a_constant_series_expands_relative_to_its_value(value, half):
    """An absolute half-unit gave a constant series at 1000 the ticks
    999.5 / 1000 / 1000.5 — three near-identical numbers instead of a scale.

    The expansion is |v| * 5%, and the ordinary margin then adds 5% of that
    *full* span to each end, so the half-width lands at |v| * 0.055 —
    (945, 1055) for 1000, which is what matplotlib gives.
    """
    fig, ax = pp.subplots()
    ax.scatter([5.0], [value])
    lo, hi = _y(ax)
    assert (hi - lo) / 2.0 == pytest.approx(half)
    assert (lo + hi) / 2.0 == pytest.approx(value), "and stays centered"


def test_a_constant_zero_falls_back_to_an_absolute_width():
    """Zero has no magnitude to scale from, so the relative rule cannot help."""
    fig, ax = pp.subplots()
    ax.scatter([5.0], [0.0])
    lo, hi = _y(ax)
    assert lo < 0.0 < hi


def test_a_tiny_constant_value_does_not_collapse_the_axis():
    fig, ax = pp.subplots()
    ax.scatter([5.0], [1e-9])
    lo, hi = _y(ax)
    assert lo < hi, "a subnormal-ish value must still get a usable range"


def test_a_huge_span_does_not_pad_to_infinity():
    """`(hi - lo) * pad` overflows here; an infinite pad leaves an axis with no
    ticks and nothing drawn."""
    fig, ax = pp.subplots()
    ax.line([0, 1], [-1e308, 1e308])
    lo, hi = _y(ax)
    assert math.isfinite(lo) and math.isfinite(hi)


def test_a_vertex_with_a_non_finite_coordinate_moves_neither_axis():
    """Folding x and y separately let a point that is never drawn still stretch
    an axis: (100, NaN) has no y to plot, but an independent x scan saw the
    100."""
    fig, ax = pp.subplots()
    ax.line([1.0, 2.0, 100.0], [1.0, 2.0, float("nan")])
    lo, hi = _x(ax)
    assert hi < 3.0


@pytest.mark.parametrize("bad", [-0.5, -0.6, -1.0])
def test_a_margin_that_would_invert_the_axis_is_rejected(bad):
    """At -0.5 the ends meet and the axis has zero width; below it they cross
    and the chart silently reads backwards."""
    fig, ax = pp.subplots()
    ax.line([0, 1], [0, 1])
    with pytest.raises(ValueError, match="greater than -0.5"):
        ax.set(ymargin=bad)


def test_a_negative_margin_above_the_limit_still_works():
    """It crops into the data, which is a legitimate thing to ask for."""
    fig, ax = pp.subplots()
    ax.line([0, 1], [0.0, 10.0])
    ax.set(ymargin=-0.1)
    lo, hi = _y(ax)
    assert lo == pytest.approx(1.0) and hi == pytest.approx(9.0)


# -- shared axes -------------------------------------------------------------

def test_sharing_an_axis_preserves_an_inverted_panel():
    """The union was taken with a plain min/max over the endpoints, which threw
    the direction away: the panel asked to descend came back ascending and its
    data was drawn against a frame nobody asked for."""
    fig, axs = pp.subplots(1, 2, sharey=True)
    axs[0].line([0, 1], [0, 10])
    axs[1].line([0, 1], [0, 5])
    axs[1].set(yinverted=True)
    left = axs[0]._effective_ranges()[1]
    right = axs[1]._effective_ranges()[1]
    assert left[0] < left[1], "the un-inverted panel still ascends"
    assert right[0] > right[1], "the inverted panel still descends"
    assert sorted(left) == sorted(right), "both cover the same union"
