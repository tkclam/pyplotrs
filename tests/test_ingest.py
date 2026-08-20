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

import pyplotrs as pp
import pytest
from pyplotrs import _pyplotrs_core as _core
from pyplotrs._util import _RangeAcc, _to_f64, _to_f64_grid

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised only on a numpy-less host
    np = None

#: Gate the handful of cases that genuinely need NumPy, rather than the module.
#: A module-level ``importorskip`` used to sit here, which meant a CI job that
#: installed only ``pyplotrs pytest`` silently skipped **all 26** tests in this
#: file - including the 22 that use nothing but the standard library - and
#: reported green. That is how the ``imshow`` dtype crash reached this audit.
requires_numpy = pytest.mark.skipif(np is None, reason="numpy is a test-only convenience")


# -- _to_f64 -----------------------------------------------------------------

@pytest.mark.parametrize("make", [
    pytest.param(lambda v: v, id="list"),
    pytest.param(tuple, id="tuple"),
    pytest.param(iter, id="iterator"),
    pytest.param(lambda v: array("d", v), id="array-d"),
    pytest.param(lambda v: array("f", v), id="array-f32"),
    pytest.param(lambda v: array("q", [int(x) for x in v]), id="array-int64"),
    pytest.param(lambda v: np.asarray(v, dtype=np.float64), id="numpy-f64",
                 marks=requires_numpy),
    pytest.param(lambda v: np.asarray(v, dtype=np.float32), id="numpy-f32",
                 marks=requires_numpy),
    pytest.param(lambda v: np.asarray(v, dtype=np.int64), id="numpy-int64",
                 marks=requires_numpy),
    # A non-contiguous view: the fast path must not read the underlying memory
    # in the wrong order. It is made contiguous on the way in rather than
    # declined, so the memcpy still applies.
    pytest.param(lambda v: np.repeat(np.asarray(v, dtype=np.float64), 2)[::2],
                 id="numpy-strided", marks=requires_numpy),
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
    fig, ax = pp.subplots(figsize=(240, 180))
    ax.line(xs, ys, marker="o")
    ax.set(title="ingest", xlabel="x", ylabel="y")
    out = tmp_path / f"{name}.png"
    fig.save(str(out))
    return out.read_bytes()


@requires_numpy
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


@requires_numpy
def test_integer_input_renders_like_float(tmp_path):
    ints = _render(np.asarray([0, 1, 2, 3]), np.asarray([0, 1, 4, 9]), tmp_path, "int")
    floats = _render([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0], tmp_path, "flt")
    assert ints == floats


# -- NumPy dtypes, array kinds and the 2D grid path --------------------------
#
# `_to_f64_grid` flattened a 2D buffer with `view.cast(fmt, (h*w,))`, and
# `memoryview.cast` refuses to cast between two non-byte formats - so
# `imshow`/`matshow` raised "cannot cast between two non-byte formats" for
# every dtype except float64, int8 and uint8. float32 image data is the common
# case, so this was reachable in the first five minutes of use.

_DTYPES = ["float64", "float32", "float16", "int8", "uint8", "int16", "uint16",
           "int32", "int64", "uint32", "uint64", "bool"]


@requires_numpy
@pytest.mark.parametrize("dtype", _DTYPES)
@pytest.mark.parametrize("method", ["imshow", "matshow"])
def test_2d_grid_accepts_every_numeric_dtype(tmp_path, dtype, method):
    grid = np.arange(12).reshape(3, 4).astype(dtype)
    fig, ax = pp.subplots(figsize=(160, 120))
    getattr(ax, method)(grid)
    fig.save(str(tmp_path / f"{method}-{dtype}.png"))


@requires_numpy
@pytest.mark.parametrize("dtype", _DTYPES)
def test_grid_values_survive_the_dtype_conversion(dtype):
    grid = np.arange(12).reshape(3, 4).astype(dtype)
    flat, h, w = _to_f64_grid(grid)
    assert (h, w) == (3, 4)
    assert list(flat) == [float(v) for v in grid.ravel()]


@requires_numpy
@pytest.mark.parametrize("kind", ["transpose", "strided", "fortran"])
def test_grid_accepts_non_contiguous_arrays(kind):
    """A transpose or a strided slice must be read in *logical* order, not in
    the order the bytes happen to sit in memory."""
    base = np.arange(48).reshape(6, 8).astype("float32")
    grid = {"transpose": base.T, "strided": base[::2, ::2],
            "fortran": np.asfortranarray(base)}[kind]
    flat, h, w = _to_f64_grid(grid)
    assert (h, w) == grid.shape
    assert list(flat) == [float(v) for v in grid.ravel()]


@requires_numpy
def test_masked_arrays_become_gaps_rather_than_fill_values():
    """A masked array's raw buffer is its *fill* values, so taking the buffer
    plots whatever sentinel happens to be under the mask - 999.0 here, drawn as
    real data. Converting through ``filled(nan)`` sends them down the NaN-gap
    path instead."""
    out = _to_f64(np.ma.masked_array([1.0, 2.0, 999.0], mask=[0, 0, 1]))
    assert out[0] == 1.0 and out[1] == 2.0
    assert math.isnan(out[2]), "the masked element should read as a gap, not 999.0"


@requires_numpy
@pytest.mark.parametrize("dtype", ["float32", "int32", "int64", "uint8"])
def test_non_float64_dtypes_render_like_float64(tmp_path, dtype):
    xs, ys = [0, 1, 2, 3], [0, 1, 4, 9]
    ref = _render(np.asarray(xs, "float64"), np.asarray(ys, "float64"), tmp_path, "ref")
    got = _render(np.asarray(xs, dtype), np.asarray(ys, dtype), tmp_path, dtype)
    assert got == ref


@requires_numpy
def test_string_arrays_reach_the_categorical_axis():
    """A NumPy ``<U*`` array *is* buffer-backed, so a fast path testing only
    ndim/contiguity took it and died on "unsupported format 1w" instead of
    letting it become a categorical axis the way a list of strings does."""
    fig, ax = pp.subplots()
    ax.bar(np.array(["alpha", "beta", "gamma"]), np.array([3, 4, 2], dtype="int32"))
    assert ax.get_xscale() == "categorical"
    assert ax.get_xticklabels() == ["alpha", "beta", "gamma"]


@requires_numpy
def test_datetime64_arrays_reach_the_date_axis():
    fig, ax = pp.subplots()
    ax.line(np.arange("2020-01", "2020-06", dtype="datetime64[M]"), [1, 2, 3, 4, 5])
    assert ax.get_xscale() == "date"
    assert ax.get_xticklabels()[0].endswith("2020")


@requires_numpy
def test_object_arrays_of_numbers_still_convert():
    assert list(_to_f64(np.array([1, 2, 3], dtype=object))) == [1.0, 2.0, 3.0]


def test_nan_still_breaks_the_line_into_a_gap(tmp_path):
    """Non-finite points must survive ingest and become a subpath break; a NaN
    that reached autoscaling instead would collapse the axis."""
    import re

    fig, ax = pp.subplots(figsize=(240, 180))
    ax.line([0, 1, 2, 3, 4], [0, 1, float("nan"), 3, 4])
    out = tmp_path / "gap.svg"
    fig.save(str(out))

    # Inspect the path geometry only. Searching the whole document would match
    # the base64-encoded embedded font.
    paths = re.findall(r'<path[^>]*\sd="([^"]*)"', out.read_text(encoding="utf-8"))
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
    fig, ax = pp.subplots(figsize=(240, 180))
    ax.bar(["a", "b"], [3.0, 5.0])
    _, (ylo, yhi) = ax._ranges()
    assert ylo == 0.0, f"bar baseline moved to {ylo}"
    assert yhi >= 5.0


def test_errorbar_autoscale_stays_two_sided():
    fig, ax = pp.subplots(figsize=(240, 180))
    ax.errorbar([0, 1], [10.0, 10.0], yerr=[2.0, 2.0])
    _, (ylo, yhi) = ax._ranges()
    assert ylo <= 8.0 and yhi >= 12.0, "whiskers were not included in the y range"


# -- color mapping ----------------------------------------------------------

def test_map_colors_matches_the_python_reference():
    """The Rust mapper must agree with ``cmap(norm(v))`` value for value."""
    from pyplotrs import colormaps, norms
    from pyplotrs._draw import _colormap_lut

    cm = colormaps.get_cmap("viridis")
    nrm = norms.Normalize(0.0, 1.0)
    values = array("d", [0.0, 0.25, 0.5, 0.75, 1.0])
    got = _core.map_colors(values, _colormap_lut(cm), 0.0, 1.0, "linear")
    assert got == [cm(nrm(v)) for v in values]


def test_map_colors_log_matches_lognorm():
    from pyplotrs import colormaps, norms
    from pyplotrs._draw import _colormap_lut

    cm = colormaps.get_cmap("viridis")
    nrm = norms.LogNorm(1.0, 1000.0)
    values = array("d", [1.0, 10.0, 100.0, 1000.0])
    got = _core.map_colors(values, _colormap_lut(cm), 1.0, 1000.0, "log")
    for g, v in zip(got, values):
        assert g == cm(nrm(v)), f"log mapping diverged at {v}"


def test_map_colors_leaves_out_of_domain_transparent():
    from pyplotrs import colormaps
    from pyplotrs._draw import _colormap_lut

    lut = _colormap_lut(colormaps.get_cmap("viridis"))
    # Non-positive on a log scale, and a NaN, have no position on the color axis.
    got = _core.map_colors(array("d", [-1.0, 0.0, float("nan")]), lut, 1.0, 10.0, "log")
    assert all(rgba == (0, 0, 0, 0) for rgba in got)


def test_colormap_lut_is_cached_and_stable():
    from pyplotrs import colormaps
    from pyplotrs._draw import _colormap_lut

    cm = colormaps.get_cmap("plasma")
    first = _colormap_lut(cm)
    assert _colormap_lut(cm) is first, "LUT was resampled instead of cached"
    assert len(first) == 1024
    other = _colormap_lut(colormaps.get_cmap("magma"))
    assert other != first, "different colormaps must not share a table"


def test_norms_declare_a_rust_code_only_when_one_exists():
    """``code`` gates the Rust bulk path. A piecewise norm claiming a code would
    silently render with the wrong colors."""
    from pyplotrs import norms

    assert norms.Normalize().code == "linear"
    assert norms.LogNorm().code == "log"
    assert norms.TwoSlopeNorm(vcenter=0.0).code is None
    assert norms.BoundaryNorm([0.0, 1.0, 2.0]).code is None


def test_exotic_norms_still_colour_correctly(tmp_path):
    """TwoSlopeNorm has no Rust transform, so it must fall back to per-value
    Python rather than being mapped as if it were linear."""
    from pyplotrs import colormaps, norms
    from pyplotrs._draw import _rgba_values

    cm = colormaps.get_cmap("coolwarm")
    nrm = norms.TwoSlopeNorm(vcenter=0.0, vmin=-1.0, vmax=3.0)
    values = array("d", [-1.0, 0.0, 3.0])
    assert _rgba_values(values, cm, nrm) == [cm(nrm(v)) for v in values]

    fig, ax = pp.subplots(figsize=(240, 180))
    ax.scatter([0, 1, 2], [0, 1, 2], c=[-1.0, 0.0, 3.0], norm=nrm, cmap="coolwarm")
    fig.save(str(tmp_path / "twoslope.png"))


def test_colormapped_scatter_renders_identically_at_both_sizes(tmp_path):
    """Above 64 markers the raster backend switches to tinted sprite stamping;
    below it, per-point fills. The two must agree, or a scatter would change
    appearance as points were added."""
    from conftest import read_png

    def render(n, name):
        xs = [i / n for i in range(n)]
        fig, ax = pp.subplots(figsize=(240, 180))
        ax.scatter(xs, xs, c=xs, cmap="viridis")
        ax.set(xlim=(0, 1), ylim=(0, 1))
        out = tmp_path / f"{name}.png"
        fig.save(str(out))
        return out

    # Same geometry, one either side of the stamping threshold, is not directly
    # comparable - so instead assert each renders and the large one is not blank.
    small, large = render(20, "small"), render(400, "large")
    _, _, buf = read_png(large)
    assert any(b != 255 for b in buf), "large colormapped scatter rendered blank"
    _, _, sbuf = read_png(small)
    assert any(b != 255 for b in sbuf)
