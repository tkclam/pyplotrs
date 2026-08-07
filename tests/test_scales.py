"""Scales, tick location and formatters.

These are the numeric layer beneath every axis, they have no visual signature
when they go subtly wrong (a log axis with linear ticks still *looks* like a
plot), and none of the three modules - ``scales.py``, ``ticker.py``,
``norms.py`` - had a single test.
"""

from __future__ import annotations

import datetime as dt
import math

import pytest

import pyplotrs as plt
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
    fig, ax = plt.subplots()
    ax.bar(["beta", "alpha", "beta", "gamma"], [1, 2, 3, 4])
    scale = ax._xscale
    assert isinstance(scale, scales.CategoricalScale)
    assert scale.categories == ["beta", "alpha", "gamma"]


def test_datetime_axis_switches_scale_and_orders_correctly():
    fig, ax = plt.subplots()
    days = [dt.date(2026, 1, 1), dt.date(2026, 6, 1), dt.date(2026, 12, 1)]
    ax.line(days, [1, 2, 3])
    assert isinstance(ax._xscale, scales.DateScale)
    xs = ax._marks[0]["xs"]
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
    fig, ax = plt.subplots(figsize=(240, 180))
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
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.line([0, 1, 2], [0, 1, 2])
    ax.set(xticks=[0, 1, 2], xticklabels=["zero", "one", "two"])
    out = tmp_path / "ticks.svg"
    fig.save(str(out))
    svg = out.read_text()
    for label in ("zero", "one", "two"):
        assert label in svg, f"manual tick label {label!r} missing from output"
