"""Colored lines, scale bars, significance brackets and broken axes."""

import pytest

import pyplotrs as pp
from pyplotrs.artists import stars
from tests.conftest import decode_png, pixel


def render(fig):
    """Draw at 72 dpi (one pixel per point) and return the PNG rows."""
    return decode_png(fig.to_bytes("png", dpi=72))[2]


# -- colored lines -------------------------------------------------------------------


def test_line_colored_by_value_follows_the_colormap():
    fig, ax = pp.subplots()
    xs = [i / 10 for i in range(11)]
    ln = ax.line(xs, [0] * 11, c=xs, cmap="gray", linewidth=6)
    fig.colorbar(ln)
    rows = render(fig)
    v = ax._last_view
    y = round(v.tf.y(0))
    dark = pixel(rows, round(v.tf.x(0.1)), y)
    light = pixel(rows, round(v.tf.x(0.9)), y)
    assert dark[0] < 100 < light[0]


def test_colored_line_checks_lengths_and_draws_markers():
    _, ax = pp.subplots()
    with pytest.raises(ValueError, match="equal length"):
        ax.line([0, 1, 2], [0, 1, 2], c=[0, 1])
    ax.line([0, 1, 2], [0, 1, 0], c=[0, 1, 2], marker="o", linestyle="none")
    assert ax.figure is not None
    ax.figure.to_bytes("pdf")


# -- scale bars ------------------------------------------------------------------------


def test_scalebar_labels_default_to_lengths_and_do_not_autoscale():
    _, ax = pp.subplots()
    ax.line([0, 10], [0, 1])
    before = ax.get_xlim(), ax.get_ylim()
    bar = ax.scalebar(x=2, y=0.5, ylabel="0.5 mV")
    assert (bar.xlabel, bar.ylabel) == ("2", "0.5 mV")
    assert (ax.get_xlim(), ax.get_ylim()) == before
    with pytest.raises(ValueError, match="needs a length"):
        ax.scalebar()


def test_scalebar_sits_in_its_corner():
    fig, ax = pp.subplots()
    ax.line([0, 10], [0, 10], color="w")
    ax.scalebar(x=5, xlabel="", loc="lower right", linewidth=4, pad=10)
    ax.set(frame=False)
    rows = render(fig)
    v = ax._last_view
    y = round(v.y + v.h - 10)
    assert pixel(rows, round(v.x + v.w - 20), y)[0] < 50  # on the bar
    assert pixel(rows, round(v.x + 20), y)[0] > 200  # left of it: background


def test_scalebar_rejects_unknown_corners():
    fig, ax = pp.subplots()
    ax.scalebar(x=1, loc="middle")
    with pytest.raises(ValueError, match="scalebar loc"):
        fig.to_bytes("png")


# -- brackets --------------------------------------------------------------------------


def test_p_values_become_stars():
    assert [stars(p) for p in (0.5, 0.04, 0.009, 0.0009, 0.00009)] == [
        "n.s.",
        "*",
        "**",
        "***",
        "****",
    ]


def test_brackets_sit_above_the_data_and_stack():
    _, ax = pp.subplots()
    ax.bar(["a", "b", "c"], [1, 2, 1])
    ab = ax.bracket("a", "b", 0.005)
    bc = ax.bracket("b", "c", "n.s.")
    ac = ax.bracket("a", "c", 0.2)
    assert ab.text == "**" and ac.text == "n.s."
    assert ab.y > 2
    assert bc.y > ab.y  # shares x = "b" with the first bracket
    assert ac.y > bc.y
    assert ax.get_ylim()[1] > ac.y + ac.headroom * 0.99  # room for the text


def test_brackets_side_by_side_share_a_height():
    _, ax = pp.subplots()
    ax.bar([0, 1, 3, 4], [2, 2, 2, 2], width=0.5)
    left = ax.bracket(0, 1)
    right = ax.bracket(3, 4)
    assert left.y == pytest.approx(right.y)


def test_bracket_clears_error_bars_and_accepts_a_height():
    _, ax = pp.subplots()
    ax.errorbar([0, 1], [1, 1], yerr=[0.5, 2])
    assert ax.bracket(0, 1).y > 3
    assert ax.bracket(0, 1, y=10).y == 10


# -- broken axes -------------------------------------------------------------------------


def test_break_splits_the_view_into_pieces():
    _, ax = pp.subplots()
    ax.line([0, 100], [0, 1])
    ax.set(xbreak=(10, 90), margin=0)
    assert ax.xaxis.pieces(ax.get_xlim()) == [(0, 10), (90, 100)]
    ticks = ax.get_xticks()
    assert ticks and not any(10 < t < 90 for t in ticks)
    ax.set(xinverted=True)
    assert ax.xaxis.pieces(ax.get_xlim()) == [(100, 90), (10, 0)]


def test_break_margin_is_a_fraction_of_what_is_shown():
    _, ax = pp.subplots()
    ax.line([0, 100], [0, 1])
    ax.set(xbreak=(10, 90))
    assert ax.get_xlim() == pytest.approx((-1.0, 101.0))


def test_break_settings_are_validated_and_clearable():
    _, ax = pp.subplots()
    ax.set(ybreak=[(5, 6), (1, 2)])
    assert ax.yaxis.breaks == [(1.0, 2.0), (5.0, 6.0)]
    with pytest.raises(ValueError, match="lo < hi"):
        ax.set(ybreak=(3, 3))
    ax.set(ybreak=None)
    assert ax.yaxis.breaks == []


def test_broken_axis_leaves_a_gap():
    fig, ax = pp.subplots()
    ax.axhspan(-1000, 1000, color="k")  # fill the whole plot
    ax.line([0, 100], [0, 1], color="k")
    ax.set(xbreak=(40, 60), margin=0)
    rows = render(fig)
    v = ax._last_view
    mid_x, mid_y = round(v.x + v.w / 2), round(v.y + v.h / 2)
    assert pixel(rows, mid_x, mid_y)[0] > 200  # the gap shows the background
    assert pixel(rows, round(v.x + v.w / 4), mid_y)[0] < 150  # the translucent span


def test_broken_axes_render_with_marks_outside_the_plot():
    fig, axs = pp.subplots(1, 2)
    for ax in axs:
        ax.bar(["a", "b"], [1, 50])
        ax.bracket("a", "b", 0.001)
        ax.text(0, 25, "label")
        ax.scalebar(y=10)
    axs[0].set(ybreak=(5, 45), grid=True)
    axs[1].set(xbreak=(0.2, 0.8), ybreak=(5, 45))
    for fmt in ("png", "pdf", "svg"):
        fig.to_bytes(fmt, dpi=72)


def test_broken_axis_and_twins_do_not_mix():
    fig, ax = pp.subplots()
    ax.line([0, 10], [0, 10])
    ax.twinx().line([0, 10], [5, 6])
    ax.set(ybreak=(2, 8))
    with pytest.raises(ValueError, match="twin"):
        fig.to_bytes("png")
