"""Input handling: NumPy arrays, plain sequences, masked and missing values."""

import array

import pytest

import pyplotrs as pp
from pyplotrs import _data

np = pytest.importorskip("numpy")


@pytest.mark.parametrize("dtype", ["float64", "float32", "int32", "int64", "bool"])
def test_numpy_dtypes(dtype):
    out = _data.f64(np.arange(4).astype(dtype))
    assert list(out) == [float(v) for v in np.arange(4).astype(dtype)]


def test_float64_arrays_pass_through_without_copy():
    a = np.arange(5.0)
    assert _data.f64(a) is a
    b = array.array("d", [1.0])
    assert _data.f64(b) is b


def test_strided_and_masked_arrays():
    assert list(_data.f64(np.arange(10.0)[::3])) == [0.0, 3.0, 6.0, 9.0]
    m = np.ma.masked_array([1.0, 2.0, 3.0], mask=[False, True, False])
    vals = list(_data.f64(m))
    assert vals[0] == 1.0 and vals[1] != vals[1]


def test_grids():
    flat, w, h = _data.grid(np.arange(6.0).reshape(2, 3))
    assert (w, h) == (3, 2) and list(flat) == [0, 1, 2, 3, 4, 5]
    flat, w, h = _data.grid([[1, 2, 3], [4, 5, 6]])
    assert (w, h) == (3, 2)


def test_plotting_numpy_end_to_end():
    fig, ax = pp.subplots()
    x = np.linspace(0, 1, 1000)
    ax.line(x, np.sin(x))
    ax.scatter(x[::10], np.cos(x[::10]), c=x[::10])
    ax.imshow(np.random.default_rng(0).random((20, 30)))
    ax.line(np.array(["a", "b"]), [0, 1])
    fig.to_bytes("png", dpi=50)


def test_numpy_datetimes():
    _, ax = pp.subplots()
    ax.line(np.array(["2024-01-01", "2024-02-01"], dtype="datetime64[D]"), [0, 1])
    assert ax.get_xscale() == "date"


def test_helpers():
    assert _data.steps([0, 1, 2], [1, 2, 3], "post") == ([0, 1, 1, 2, 2], [1, 1, 2, 2, 3])
    assert _data.edges_from_centers([0, 1, 2]) == [-0.5, 0.5, 1.5, 2.5]
    stats = _data.boxstats([1, 2, 3, 4, 100])
    assert stats["med"] == 3 and stats["fliers"] == [100.0]
    lv = _data.levels(_data.f64([0.0, 1.0]), 4, filled=False)
    assert all(0 < v < 1 for v in lv) and lv == sorted(lv)
