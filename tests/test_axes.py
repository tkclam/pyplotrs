"""Axes configuration: limits, scales, ticks, getters, and helpful errors."""

import datetime as dt
import math

import pytest

import pyplotrs as pp
from tests.conftest import decode_png, pixel


def test_autoscale_adds_margin():
    _, ax = pp.subplots()
    ax.line([0, 10], [0, 1])
    lo, hi = ax.get_xlim()
    assert lo == pytest.approx(-0.5) and hi == pytest.approx(10.5)


def test_bars_take_one_color_each():
    fig, ax = pp.subplots()
    bars = ax.bar(["a", "b"], [1, 1], color=["red", (0, 0, 255)])
    assert bars.color == (255, 0, 0, 255)  # the legend shows the first
    rows = decode_png(fig.to_bytes("png", dpi=72))[2]
    tf, y = ax._last_view.tf, ax._last_view.tf.y(0.5)
    assert pixel(rows, round(tf.x(0)), round(y))[:3] == (255, 0, 0)
    assert pixel(rows, round(tf.x(1)), round(y))[:3] == (0, 0, 255)
    ax.barh([0, 1], [1, 2], color=("C0", "C1"))
    ax.bar([0], [1], color=(0.2, 0.4, 0.6))  # one RGB color, not three
    with pytest.raises(ValueError, match="2 colors for 3 bars"):
        ax.bar([0, 1, 2], [1, 1, 1], color=["r", "b"])


def test_bars_rest_on_zero():
    _, ax = pp.subplots()
    ax.bar([1, 2], [3, 4])
    assert ax.get_ylim()[0] == 0.0


def test_margin_and_partial_limits():
    _, ax = pp.subplots()
    ax.line([0, 10], [0, 1])
    ax.set(margin=0, ylim=(None, 2))
    assert ax.get_xlim() == (0.0, 10.0)
    assert ax.get_ylim() == (0.0, 2.0)
    ax.set(ylim=None)
    assert ax.get_ylim() == (0.0, 1.0)


def test_inverted_axis_keeps_autoscaling():
    _, ax = pp.subplots()
    ax.line([0, 1], [0, 5])
    ax.set(yinverted=True, margin=0)
    assert ax.get_ylim() == (5.0, 0.0)


def test_image_runs_y_downward_by_default():
    _, ax = pp.subplots()
    ax.imshow([[1, 2], [3, 4]])
    assert ax.get_ylim() == (1.5, -0.5)
    _, ax = pp.subplots()
    ax.imshow([[1, 2], [3, 4]], origin="lower")
    assert ax.get_ylim() == (-0.5, 1.5)


def test_log_scale_ignores_nonpositive_data():
    _, ax = pp.subplots()
    ax.line([0, 1, 10, 100], [1, 2, 3, 4])
    ax.set(xscale="log")
    lo, hi = ax.get_xlim()
    assert 0 < lo < 1 < 100 < hi
    assert ax.get_xticklabels()[0].startswith("$10^")


def test_ticks_and_labels():
    _, ax = pp.subplots()
    ax.line([0, 1], [-1, 1])
    assert ax.get_xticks() == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    assert "−1.0" in ax.get_yticklabels()  # real minus sign
    ax.set(xticks=[0, 0.5, 1], xticklabels=["lo", "mid", "hi"])
    assert ax.get_xticklabels() == ["lo", "mid", "hi"]
    ax.set(yformatter="{x:+.1f} V")
    assert ax.get_yticklabels()[0] == "-1.0 V"
    ax.set(yformatter=pp.ticker.Percent())
    assert ax.get_yticklabels()[-1] == "100%"


def test_unicode_minus_can_be_turned_off():
    pp.set_theme(font_family=("Liberation Sans",), unicode_minus=False)
    _, ax = pp.subplots()
    ax.line([0, 1], [-1, 1])
    assert "-1.0" in ax.get_yticklabels()


def test_offset_is_factored_out_of_crowded_ticks():
    fig, ax = pp.subplots()
    ax.line([1e6 + 0.01 * i for i in range(10)], [0] * 10)
    labels = ax.get_xticklabels()
    assert all(len(s) <= 5 for s in labels)
    fig.to_bytes("svg")


def test_categorical_axis_from_strings():
    _, ax = pp.subplots()
    ax.bar(["a", "b", "c"], [1, 2, 3])
    ax.line(["b", "c"], [1, 1])
    assert ax.get_xscale() == "categorical"
    assert ax.get_xticklabels() == ["a", "b", "c"]
    assert ax.get_xlim() == (-0.5, 2.5)


def test_date_axis_from_datetimes():
    _, ax = pp.subplots()
    ax.line([dt.date(2024, m, 1) for m in range(1, 13)], list(range(12)))
    assert ax.get_xscale() == "date"
    assert "2024" in ax.get_xticklabels()[0]


def test_symlog_and_logit():
    _, ax = pp.subplots()
    ax.line([-100, 100], [0.01, 0.99])
    ax.set(xscale=pp.scales.Symlog(linthresh=1), yscale="logit")
    assert 0.0 in ax.get_xticks()
    assert 0.5 in ax.get_yticks()


def test_shared_axes_have_equal_limits():
    _, (a, b) = pp.subplots(1, 2, sharey=True)
    a.line([0, 1], [0, 1])
    b.line([0, 1], [0, 10])
    assert a.get_ylim() == b.get_ylim()
    assert a.get_xlim() == b.get_xlim()  # x is not shared, but data are equal


def test_twin_axes_and_insets_render():
    fig, ax = pp.subplots()
    ax.line([0, 1], [0, 1], label="a")
    twin = ax.twinx()
    twin.line([0, 1], [10, 0], label="b")
    twin.set(ylabel="right")
    ax.inset_axes((0.6, 0.6, 0.3, 0.3)).line([0, 1], [1, 0])
    ax.legend()
    assert twin.get_ylim()[1] > 9
    fig.to_bytes("png", dpi=72)


def test_set_is_chainable_and_validates():
    _, ax = pp.subplots()
    assert ax.set(title="t") is ax
    assert ax.get_title() == "t"
    with pytest.raises(ValueError, match="scale"):
        ax.set(xscale="cubic")
    with pytest.raises(ValueError, match="margin"):
        ax.set(margin=-1)
    with pytest.raises(ValueError, match="aspect"):
        ax.set(aspect="square")


def test_input_validation():
    _, ax = pp.subplots()
    with pytest.raises(ValueError, match="equal length"):
        ax.line([1, 2, 3], [1, 2])
    with pytest.raises(ValueError, match="linestyle"):
        ax.line([1], [1], linestyle="wavy")
    with pytest.raises(ValueError, match="marker"):
        ax.scatter([1], [1], marker="*?")
    with pytest.raises(ValueError, match="color"):
        ax.line([1], [1], color="notacolor")
    with pytest.raises(ValueError, match="rows"):
        ax.imshow([[1, 2], [3]])
    with pytest.raises(ValueError, match="loc"):
        ax.legend("somewhere")


def test_matplotlib_names_explain_themselves():
    fig, ax = pp.subplots()
    with pytest.raises(AttributeError, match=r"line\(\)"):
        ax.plot([1], [1])
    with pytest.raises(AttributeError, match="set\\(xlabel"):
        ax.set_xlabel("x")
    with pytest.raises(AttributeError, match="save"):
        fig.savefig("x.png")
    with pytest.raises(AttributeError, match="no attribute"):
        ax.definitely_not_a_method  # noqa: B018


def test_color_cycle_and_palette_references():
    _, ax = pp.subplots()
    a, b = ax.line([0], [0]), ax.line([0], [0])
    palette = ax.theme.palette
    assert (a.color, b.color) == (palette[0], palette[1])
    assert ax.line([0], [0], color="C5").color == palette[5]


def test_nan_breaks_lines_and_is_ignored_by_autoscale():
    fig, ax = pp.subplots()
    ax.line([0, 1, 2, 3], [0, math.nan, 2, 3])
    ax.set(margin=0)
    assert ax.get_ylim() == (0.0, 3.0)
    fig.to_bytes("svg")


def test_repr():
    fig, ax = pp.subplots()
    ax.line([0], [0])
    ax.set(title="T")
    assert repr(ax) == "<Axes 'T' with 1 mark>"
    assert "1 axes" in repr(fig)
