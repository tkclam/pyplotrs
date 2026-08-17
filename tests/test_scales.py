"""Scales, tick location and formatters.

These are the numeric layer beneath every axis, they have no visual signature
when they go subtly wrong (a log axis with linear ticks still *looks* like a
plot), and none of the three modules - ``scales.py``, ``ticker.py``,
``norms.py`` - had a single test.
"""

from __future__ import annotations

import datetime as dt
import math

import pyplotrs as pp
import pytest
from pyplotrs import _pyplotrs_core as _core
from pyplotrs import norms, scales, ticker

# -- transform round-trips ---------------------------------------------------

@pytest.mark.parametrize("name,value", [
    ("linear", 3.5),
    ("log", 250.0),
    ("symlog", -17.0),
    ("symlog", 0.0),
    ("logit", 0.3),
])
def test_transform_inverse_roundtrips(name, value):
    s = scales.get(name)
    assert s.inverse(s.transform(value)) == pytest.approx(value, rel=1e-9, abs=1e-12)


def test_scale_codes_match_the_rust_fast_path():
    """``Scale.code`` selects a branch in Rust's ``apply_scale``. A typo here
    would silently fall back to a linear transform and misplace every point -
    exactly the failure mode behind the errorbar-on-log-axis bug."""
    expected = {"linear": "linear", "log": "log", "symlog": "symlog", "logit": "logit"}
    for name, code in expected.items():
        assert scales.get(name).code == code
    assert scales.get("linear").is_identity
    for name in ("log", "symlog", "logit"):
        assert not scales.get(name).is_identity


def test_log_scale_drops_nonpositive_data():
    s = scales.get("log")
    assert s.transform(-1.0) == -math.inf
    assert s.transform(0.0) == -math.inf


# -- tick location -----------------------------------------------------------

def test_log_ticks_are_decades():
    ticks = scales.get("log").ticks(1.0, 1000.0, 6)
    values = [v for v, _ in ticks]
    assert values == pytest.approx([1.0, 10.0, 100.0, 1000.0])


@pytest.mark.parametrize("lo,hi", [(0.0, 1.0), (-3.0, 7.0), (0.0, 1e6), (1.7, 1.9)])
def test_linear_ticks_are_nice_numbers(lo, hi):
    """Steps must come from the 1/2/2.5/5 x 10^n family (``NICE_STEPS`` in
    ``crates/pyplotrs-layout/src/ticks.rs``), be sorted, and be evenly spaced."""
    values = [v for v, _ in scales.get("linear").ticks(lo, hi, 6)]
    assert values == sorted(values)
    assert 2 <= len(values) <= 8, f"tick budget exceeded: {values}"

    step = values[1] - values[0]
    deltas = [b - a for a, b in zip(values, values[1:])]
    assert all(d == pytest.approx(step, rel=1e-6) for d in deltas), (
        f"ticks are not evenly spaced: {values}"
    )
    mantissa = step / 10.0 ** math.floor(math.log10(step))
    assert any(mantissa == pytest.approx(s, rel=1e-6) for s in (1.0, 2.0, 2.5, 5.0)), (
        f"step {step} has mantissa {mantissa}, not from the nice-number family"
    )


def test_ticks_lie_within_the_view():
    for name, lo, hi in [("linear", -3.0, 7.0), ("log", 1.0, 1e4), ("logit", 0.01, 0.99)]:
        for value, _ in scales.get(name).ticks(lo, hi, 6):
            assert lo - 1e-9 <= value <= hi + 1e-9, f"{name}: tick {value} outside view"


def test_categorical_scale_assigns_positions_in_first_seen_order():
    fig, ax = pp.subplots()
    ax.bar(["beta", "alpha", "beta", "gamma"], [1, 2, 3, 4])
    scale = ax._xscale
    assert isinstance(scale, scales.CategoricalScale)
    assert scale.categories == ["beta", "alpha", "gamma"]


def test_datetime_axis_switches_scale_and_orders_correctly():
    fig, ax = pp.subplots()
    days = [dt.date(2026, 1, 1), dt.date(2026, 6, 1), dt.date(2026, 12, 1)]
    ax.line(days, [1, 2, 3])
    assert isinstance(ax._xscale, scales.DateScale)
    # Coordinates are held as array("d") so they cross into Rust as a buffer;
    # compare as a list rather than relying on array/list equality.
    xs = list(ax._marks[0]["xs"])
    assert xs == sorted(xs), "date2num did not preserve chronological order"


def test_date2num_num2date_roundtrip():
    when = dt.datetime(2026, 8, 7, 13, 45, 30)
    assert scales.num2date(scales.date2num(when)) == pytest.approx(when, abs=dt.timedelta(seconds=1))


# -- formatters --------------------------------------------------------------

@pytest.mark.parametrize("formatter,value,expected", [
    (ticker.PercentFormatter(), 0.25, "25%"),
    (ticker.StrMethodFormatter("{x:.2f}"), math.pi, "3.14"),
    (ticker.FixedFormatter(["a", "b", "c"]), 1, "b"),
    (ticker.FuncFormatter(lambda v, pos=None: f"<{v:.0f}>"), 7.0, "<7>"),
])
def test_formatters_render_expected_strings(formatter, value, expected):
    out = formatter(value, 1) if not isinstance(formatter, ticker.FixedFormatter) else formatter(value, value)
    assert out == expected


def test_ticker_get_accepts_template_and_callable():
    assert isinstance(ticker.get("{x:.1f}"), ticker.Formatter)
    assert isinstance(ticker.get(lambda v, pos=None: "x"), ticker.Formatter)


# -- the minus sign ----------------------------------------------------------

@pytest.fixture
def unicode_minus():
    """Set the display flag per test and always put it back - it is process
    global, so a leak would flip labels in unrelated tests."""
    def apply(on: bool):
        pp.set_unicode_minus(on)
    yield apply
    pp.set_unicode_minus(True)


def test_negative_labels_use_a_real_minus_not_a_hyphen():
    """Negative tick labels must carry U+2212, not ASCII ``-``: the hyphen is a
    short, low word-joiner where the minus sits on the math axis at the width of
    a ``+``. Covers the Rust locator, which formats ASCII and is corrected by
    ``scales.nice_ticks`` on the way out."""
    labels = [lab for _, lab in scales.nice_ticks(-3.0, 3.0, 7)]
    assert "−3" in labels and "−1" in labels
    assert not any("-" in lab for lab in labels)


@pytest.mark.parametrize("scale,lo,hi", [
    ("linear", -3.0, 3.0),
    ("symlog", -100.0, 100.0),
])
def test_every_scale_signs_negative_ticks_the_same_way(scale, lo, hi):
    for _, lab in scales.get(scale).ticks(lo, hi, 7):
        assert "-" not in lab or lab.startswith("$"), f"ASCII hyphen in {lab!r}"


@pytest.mark.parametrize("formatter,value,expected", [
    (ticker.ScalarFormatter(), -2.0, "−2"),
    (ticker.ScalarFormatter(), -1.5, "−1.5"),
    (ticker.PercentFormatter(), -0.25, "−25%"),
    (ticker.EngFormatter(unit="V"), -0.0012, "−1.2 mV"),
    (ticker.LogFormatter(label_minor=True), 0.5, "0.5"),
])
def test_numeric_formatters_sign_with_u2212(formatter, value, expected):
    assert formatter(value) == expected


@pytest.mark.parametrize("formatter,value", [
    (ticker.DateFormatter("%Y-%m-%d"), 0.0),
    (ticker.StrMethodFormatter("{x:.0f}-{x:.0f}"), -1.0),
    (ticker.FuncFormatter(lambda v, pos=None: "a-b"), -1.0),
    (ticker.FixedFormatter(["a-b"]), 0.0),
])
def test_user_supplied_label_text_keeps_its_hyphens(formatter, value):
    """A hyphen in text the caller produced is a hyphen - a date separator, a
    range dash - and rewriting it would corrupt the label."""
    assert "-" in formatter(value, 0)
    assert ticker.MINUS not in formatter(value, 0)


def test_math_labels_are_left_for_the_math_engine():
    """Log-decade labels stay ASCII in the source string: the math engine maps
    ``-`` to U+2212 itself, and a pre-substituted glyph would lose the binary
    operator's spacing."""
    labels = [lab for _, lab in scales.get("log").ticks(1e-4, 1.0, 7)]
    assert "$10^{-4}$" in labels
    assert not any(ticker.MINUS in lab for lab in labels)


def test_unicode_minus_can_be_turned_off(unicode_minus):
    unicode_minus(False)
    assert pp.get_unicode_minus() is False
    assert [lab for _, lab in scales.nice_ticks(-2.0, 2.0, 5)][0] == "-2"
    assert ticker.ScalarFormatter()(-1.5) == "-1.5"
    unicode_minus(True)
    assert scales.nice_ticks(-2.0, 2.0, 5)[0][1] == "−2"


def test_minus_widens_the_reserved_tick_band(unicode_minus):
    """Labels reach the layout solver already signed, so the y band is measured
    from the wider glyph. If the substitution ever moved to after measurement,
    the labels would overrun the space reserved for them."""
    def y_tick_band(on: bool) -> float:
        unicode_minus(on)
        fig, ax = pp.subplots(figsize=(300, 200))
        ax.line([0, 1], [-100, -50])
        scene = _core.Scene(300, 200)
        bands, _xt, yt = ax._bands(scene, *ax._ranges())
        assert any(ticker.MINUS in lab for _, lab in yt) is on
        return bands[4]  # y_tick_h: tick length + gap + widest label

    assert y_tick_band(True) > y_tick_band(False)


# -- norms -------------------------------------------------------------------

def test_normalize_maps_endpoints_to_unit_interval():
    n = norms.get(None, 10.0, 20.0)
    assert n(10.0) == pytest.approx(0.0)
    assert n(20.0) == pytest.approx(1.0)
    assert n(15.0) == pytest.approx(0.5)


def test_lognorm_is_logarithmic():
    n = norms.get(norms.LogNorm(), 1.0, 100.0)
    assert n(1.0) == pytest.approx(0.0)
    assert n(100.0) == pytest.approx(1.0)
    assert n(10.0) == pytest.approx(0.5), "midpoint should be the geometric mean"


def test_twoslopenorm_pins_the_center():
    n = norms.get(norms.TwoSlopeNorm(vcenter=0.0), -1.0, 3.0)
    assert n(0.0) == pytest.approx(0.5), "vcenter must land at 0.5 regardless of range"


# -- end-to-end: the scale actually reaches the render ----------------------

@pytest.mark.parametrize("scale", ["log", "symlog", "logit"])
def test_nonlinear_scales_render_all_backends(scale, tmp_path):
    fig, ax = pp.subplots(figsize=(240, 180))
    if scale == "logit":
        xs, ys = [0.1, 0.5, 0.9], [0.2, 0.5, 0.8]
    else:
        xs, ys = [1.0, 10.0, 100.0], [1.0, 10.0, 100.0]
    ax.line(xs, ys, marker="o")
    ax.set(xscale=scale, yscale=scale)
    for fmt in ("pdf", "svg", "png"):
        out = tmp_path / f"{scale}.{fmt}"
        fig.save(str(out))
        assert out.stat().st_size > 200


def test_manual_ticks_and_labels_are_honoured(tmp_path):
    fig, ax = pp.subplots(figsize=(240, 180))
    ax.line([0, 1, 2], [0, 1, 2])
    ax.set(xticks=[0, 1, 2], xticklabels=["zero", "one", "two"])
    out = tmp_path / "ticks.svg"
    fig.save(str(out))
    svg = out.read_text()
    for label in ("zero", "one", "two"):
        assert label in svg, f"manual tick label {label!r} missing from output"
