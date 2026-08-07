"""The data-ingest seam: buffers in, identical figures out.

Coordinates are held as ``array.array("d")`` so they reach Rust through the
buffer protocol instead of one ``__float__`` call per element. These tests pin
the two things that migration must not break: **every input form produces the
same figure**, and the Rust reductions that replaced the Python scans agree with
the semantics they replaced (non-finite values ignored, one-sided bar extents).

NumPy is exercised where available but never required - it is a test-only
convenience, and the buffer path exists precisely so pyplotrs needs no runtime
dependency on it.
"""

from __future__ import annotations

import math
from array import array

import pytest

import pyplotrs as plt
from pyplotrs import _pyplotrs_core as _core
from pyplotrs.figure import _RangeAcc, _to_f64

np = pytest.importorskip("numpy", reason="numpy is a test-only convenience")


# -- _to_f64 -----------------------------------------------------------------

@pytest.mark.parametrize("make", [
    pytest.param(lambda v: v, id="list"),
    pytest.param(tuple, id="tuple"),
    pytest.param(iter, id="iterator"),
    pytest.param(lambda v: array("d", v), id="array-d"),
    pytest.param(lambda v: array("f", v), id="array-f32"),
    pytest.param(lambda v: array("q", [int(x) for x in v]), id="array-int64"),
    pytest.param(lambda v: np.asarray(v, dtype=np.float64), id="numpy-f64"),
    pytest.param(lambda v: np.asarray(v, dtype=np.float32), id="numpy-f32"),
    pytest.param(lambda v: np.asarray(v, dtype=np.int64), id="numpy-int64"),
    # A non-contiguous view: the buffer fast path must decline it and fall back
    # rather than reading the underlying memory in the wrong order.
    pytest.param(lambda v: np.repeat(np.asarray(v, dtype=np.float64), 2)[::2],
                 id="numpy-strided"),
])
def test_to_f64_accepts_every_sequence_form(make):
    values = [1.0, 2.0, 3.0, 4.0]
    out = _to_f64(make(list(values)))
    assert isinstance(out, array) and out.typecode == "d"
    assert list(out) == values


def test_to_f64_passes_through_an_existing_double_array():
    src = array("d", [1.0, 2.0])
    assert _to_f64(src) is src, "an array('d') should not be copied"


def test_to_f64_preserves_non_finite_values():
    """Filtering happens in the range reduction, not at ingest - a NaN has to
    survive to the draw call, where it becomes a gap in the polyline."""
    out = _to_f64([1.0, float("nan"), float("inf"), -float("inf"), 2.0])
    assert math.isnan(out[1]) and out[2] == math.inf and out[3] == -math.inf


def test_to_f64_rejects_non_numeric():
    with pytest.raises((TypeError, ValueError)):
        _to_f64([1.0, object(), 3.0])


# -- the Rust reductions -----------------------------------------------------

def test_data_range_ignores_non_finite():
    nan, inf = float("nan"), float("inf")
    assert _core.data_range(array("d", [3.0, nan, 1.0, inf, 2.0, -inf])) == (1.0, 3.0)


def test_data_range_is_none_when_nothing_is_finite():
    assert _core.data_range(array("d", [float("nan"), float("inf")])) is None
    assert _core.data_range(array("d", [])) is None


def test_positive_range_excludes_zero_and_negatives():
    assert _core.positive_range(array("d", [-5.0, 0.0, 2.0, 8.0])) == (2.0, 8.0)
    assert _core.positive_range(array("d", [-1.0, 0.0])) is None


def test_offset_range_two_sided_vs_one_sided():
    """The distinction that autoscaling depends on: an errorbar extends both
    ways from its datum, a bar only upward from its base."""
    values, offsets = array("d", [10.0]), array("d", [3.0])
    assert _core.offset_range(values, offsets, True) == (7.0, 13.0)
    assert _core.offset_range(values, offsets, False) == (13.0, 13.0)


def test_histogram_matches_the_reference_binning():
    """Rust binning must reproduce the Python loop it replaced, including the
    inclusive top edge landing in the last bin."""
    import random
    rng = random.Random(0)
    data = [rng.gauss(0, 1) for _ in range(500)]
    bins = 16
    lo, hi = min(data), max(data)
    width = (hi - lo) / bins
    expected = [0.0] * bins
    for v in data:
        expected[min(int((v - lo) / width), bins - 1)] += 1.0

    edges, counts = _core.histogram(array("d", data), bins, None, False)
    assert list(counts) == expected
    assert len(edges) == bins + 1
    assert edges[0] == pytest.approx(lo) and edges[-1] == pytest.approx(hi)


def test_histogram_density_normalizes_to_unit_area():
    data = array("d", [0.0, 1.0, 1.0, 2.0, 3.0, 4.0])
    edges, counts = _core.histogram(data, 4, None, True)
    width = edges[1] - edges[0]
    assert sum(counts) * width == pytest.approx(1.0)


def test_histogram_handles_a_degenerate_range():
    edges, counts = _core.histogram(array("d", [5.0] * 10), 4, None, False)
    assert sum(counts) == 10.0
    assert edges[-1] > edges[0]


# -- _RangeAcc ---------------------------------------------------------------

def test_range_acc_folds_without_concatenating():
    acc = _RangeAcc()
    assert acc.empty and acc.bounds() is None
    acc.add_array(array("d", [3.0, 7.0]))
    acc.add_array(array("d", [-2.0, 1.0]))
    acc.add(11.0)
    assert acc.bounds() == (-2.0, 11.0)


def test_range_acc_empty_arrays_do_not_register():
    acc = _RangeAcc()
    acc.add_array(array("d", []))
    assert acc.empty


def test_range_acc_padding_expands_a_degenerate_span():
    acc = _RangeAcc()
    acc.add_array(array("d", [5.0, 5.0]))
    lo, hi = acc.padded()
    assert lo < 5.0 < hi


# -- end to end: input form must not change the output -----------------------

def _render(xs, ys, tmp_path, name):
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.line(xs, ys, marker="o")
    ax.set(title="ingest", xlabel="x", ylabel="y")
    out = tmp_path / f"{name}.png"
    fig.save(str(out))
    return out.read_bytes()


def test_list_numpy_and_array_render_identically(tmp_path):
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [0.0, 1.0, 4.0, 9.0]
    reference = _render(xs, ys, tmp_path, "list")
    for name, conv in [
        ("numpy", lambda v: np.asarray(v, dtype=np.float64)),
        ("numpy32", lambda v: np.asarray(v, dtype=np.float32)),
        ("array", lambda v: array("d", v)),
        ("tuple", tuple),
    ]:
        assert _render(conv(xs), conv(ys), tmp_path, name) == reference, (
            f"{name} input produced a different figure than a plain list"
        )


def test_integer_input_renders_like_float(tmp_path):
    ints = _render(np.asarray([0, 1, 2, 3]), np.asarray([0, 1, 4, 9]), tmp_path, "int")
    floats = _render([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0], tmp_path, "flt")
    assert ints == floats


def test_nan_still_breaks_the_line_into_a_gap(tmp_path):
    """Non-finite points must survive ingest and become a subpath break; a NaN
    that reached autoscaling instead would collapse the axis."""
    import re

    fig, ax = plt.subplots(figsize=(240, 180))
    ax.line([0, 1, 2, 3, 4], [0, 1, float("nan"), 3, 4])
    out = tmp_path / "gap.svg"
    fig.save(str(out))

    # Inspect the path geometry only. Searching the whole document would match
    # the base64-encoded embedded font.
    paths = re.findall(r'<path[^>]*\sd="([^"]*)"', out.read_text())
    data = " ".join(paths)
    assert "nan" not in data.lower(), "a non-finite coordinate reached the geometry"
    assert any(p.count("M") >= 2 for p in paths), (
        "the NaN did not split the polyline into two subpaths"
    )

    lo, hi = ax._ranges()[1]
    assert math.isfinite(lo) and math.isfinite(hi)


def test_bar_autoscale_stays_one_sided(tmp_path):
    """A bar from 0 to 5 must not pull the axis down to -5. Caught by the golden
    suite when the shared offset reduction was first wired up two-sided."""
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.bar(["a", "b"], [3.0, 5.0])
    _, (ylo, yhi) = ax._ranges()
    assert ylo == 0.0, f"bar baseline moved to {ylo}"
    assert yhi >= 5.0


def test_errorbar_autoscale_stays_two_sided():
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.errorbar([0, 1], [10.0, 10.0], yerr=[2.0, 2.0])
    _, (ylo, yhi) = ax._ranges()
    assert ylo <= 8.0 and yhi >= 12.0, "whiskers were not included in the y range"
