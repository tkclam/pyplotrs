"""What the library does when the caller is wrong.

The rest of the suite proves that correct input renders correctly. This file
proves the complementary thing, which is the one a publication-quality library
cannot get wrong: **incorrect input must fail loudly rather than produce a
figure that looks deliberate.**

Two failure modes are covered:

* *silently wrong* - the call returns, a figure is written, and the numbers in
  it are not the numbers that were passed. Mismatched array lengths were the
  worst of these: the shorter array was truncated but the axis limits were
  still folded from the longer one, so the figure carried a visible, wrong
  claim about its own domain.
* *unreadably wrong* - the call raises, but with an internal message
  (``memoryview: unsupported format 1w``) or with a ``PanicException``, which
  derives from ``BaseException`` and so escapes ``except Exception``.
"""

from __future__ import annotations

import pytest

import pyplotrs as plt


# -- mismatched array lengths ------------------------------------------------
#
# Every mark taking parallel arrays. `ax.line([1,2,3,4,5], [10,20])` used to
# draw a two-point line on an axis running to 5, and `get_xlim()` reported
# `(0.8, 5.2)` - the padded range of the data that was thrown away.

_MISMATCHED = [
    ("line", lambda ax: ax.line([1, 2, 3, 4, 5], [10, 20])),
    ("scatter", lambda ax: ax.scatter([1, 2, 3], [1, 2])),
    ("bar", lambda ax: ax.bar([1, 2, 3], [1, 2])),
    ("barh", lambda ax: ax.barh([1, 2, 3], [1, 2])),
    ("step", lambda ax: ax.step([1, 2, 3], [1, 2])),
    ("stem", lambda ax: ax.stem([1, 2, 3], [1, 2])),
    ("fill_between", lambda ax: ax.fill_between([1, 2, 3], [1, 2])),
    ("fill_betweenx", lambda ax: ax.fill_betweenx([1, 2, 3], [1, 2])),
    ("errorbar", lambda ax: ax.errorbar([1, 2, 3], [1, 2])),
    ("stackplot", lambda ax: ax.stackplot([1, 2, 3], [1, 2], [1, 2, 3])),
    ("fill", lambda ax: ax.fill([1, 2, 3], [1, 2])),
]


@pytest.mark.parametrize("name,call", _MISMATCHED, ids=[n for n, _ in _MISMATCHED])
def test_mismatched_lengths_raise(name, call):
    _fig, ax = plt.subplots()
    with pytest.raises(ValueError, match="equal length"):
        call(ax)


@pytest.mark.parametrize("name,call", _MISMATCHED, ids=[n for n, _ in _MISMATCHED])
def test_the_length_error_names_the_mark_and_both_lengths(name, call):
    """A message has to say which call was wrong and by how much - the caller
    has usually just built both arrays and needs to know which one is short."""
    _fig, ax = plt.subplots()
    with pytest.raises(ValueError) as excinfo:
        call(ax)
    message = str(excinfo.value)
    assert name in message, f"{message!r} does not name the mark"
    # Both offending lengths, so the caller can tell which array is short.
    assert sum(c.isdigit() for c in message) >= 2, f"{message!r} omits the lengths"


def test_equal_lengths_are_still_accepted():
    """The guard must not reject the shapes that were always legal, including
    the scalar-broadcast forms (`fill_between`'s `y2`, `errorbar`'s `yerr`)."""
    _fig, ax = plt.subplots()
    ax.line([1, 2, 3], [1, 2, 3])
    ax.bar(["a", "b"], [1, 2])
    ax.fill_between([1, 2, 3], [1, 2, 3], 0.0)
    ax.errorbar([1, 2], [3, 4], yerr=0.5)
    ax.stackplot([1, 2, 3], [1, 2, 3], [2, 3, 4])
    assert len(ax._marks) >= 5


def test_truncation_no_longer_corrupts_the_axis_limits():
    """The specific figure the old behavior produced: two drawn points, an axis
    running to five."""
    _fig, ax = plt.subplots()
    with pytest.raises(ValueError):
        ax.line([1, 2, 3, 4, 5], [10, 20])
    assert ax._marks == [], "a rejected call must not leave a partial mark behind"


# -- input that used to panic across the FFI boundary ------------------------
#
# A Rust panic reaches Python as `pyo3_runtime.PanicException`, which derives
# from BaseException. `except Exception` does not catch it, and the message
# names a source file inside the extension rather than anything the caller did.

def _ragged_grid():
    return [[1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0, 5.0]]


@pytest.mark.parametrize("method", ["contour", "contourf"])
def test_ragged_grid_raises_valueerror_not_panic(method):
    _fig, ax = plt.subplots()
    with pytest.raises(ValueError, match="same length"):
        getattr(ax, method)(_ragged_grid())


def test_ragged_grid_raises_for_contour3d():
    _fig, ax = plt.subplots(projection="3d")
    with pytest.raises(ValueError, match="same length"):
        ax.contour3d([0, 1, 2, 3, 4], [0, 1, 2], _ragged_grid())


@pytest.mark.parametrize("bins", [0, -1])
def test_hist2d_rejects_a_non_positive_bin_count(bins):
    """`bins=0` reached the kernel and computed `nx - 1` in `usize`, which wraps
    to 18446744073709551615 and indexes an empty buffer."""
    _fig, ax = plt.subplots()
    with pytest.raises(ValueError, match="bins"):
        ax.hist2d([0.1, 0.5], [0.2, 0.6], bins=bins)


def test_colormap_rejects_a_non_finite_stop():
    """Sorting the stops used `partial_cmp().unwrap()`, and NaN compares to
    nothing, so a NaN position unwrapped a None."""
    with pytest.raises(ValueError, match="finite"):
        plt.Colormap("bad", stops=[(float("nan"), (0, 0, 0)), (1.0, (255, 255, 255))])


def test_no_public_call_raises_baseexception_only():
    """A blanket guard: whatever these calls do, `except Exception` must see it.

    Written as a loop rather than a parametrize so that a new panic anywhere in
    this set fails one obvious test rather than being read as an unrelated
    parametrized case.
    """
    calls = [
        lambda ax: ax.contour(_ragged_grid()),
        lambda ax: ax.contourf(_ragged_grid()),
        lambda ax: ax.hist2d([0.1, 0.5], [0.2, 0.6], bins=0),
        lambda ax: ax.line([1, 2, 3], [1, 2]),
    ]
    for call in calls:
        _fig, ax = plt.subplots()
        try:
            call(ax)
        except Exception:
            pass  # a normal, catchable error is the point
        except BaseException as exc:  # pragma: no cover - the regression itself
            pytest.fail(
                f"{type(exc).__module__}.{type(exc).__name__} escapes "
                f"`except Exception`: {exc}"
            )
