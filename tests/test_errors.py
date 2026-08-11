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

import pyplotrs as plt
import pytest

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


# -- degenerate numbers that used to be accepted silently --------------------

@pytest.mark.parametrize("dpi", [0, -5, -0.1, float("nan"), float("inf")])
def test_non_positive_dpi_raises(tmp_path, dpi):
    """`dpi=-5` rendered at 72 dpi and said nothing, so you got a small figure
    with no indication the argument had been discarded. The *upper* bound was
    already guarded with a good message, so only the bottom was open."""
    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1])
    with pytest.raises(ValueError, match="positive, finite"):
        fig.save(str(tmp_path / "f.png"), dpi=dpi)


def test_a_sane_dpi_still_works(tmp_path):
    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1])
    for dpi in (72, 100.0, 300, 600):
        out = tmp_path / f"d{dpi}.png"
        fig.save(str(out), dpi=dpi)
        assert out.stat().st_size > 0


@pytest.mark.parametrize("linestyle", ["dashdotted", "densely dashed", "- -", "Solid", ""])
def test_unknown_linestyle_raises(linestyle):
    """An unrecognized name drew a solid line. `"dashdotted"` is a real
    matplotlib spelling, so this was silently wrong rather than merely
    unsupported."""
    _fig, ax = plt.subplots()
    with pytest.raises(ValueError, match="unknown linestyle"):
        ax.line([0, 1], [0, 1], linestyle=linestyle)
        _render(ax)


def _render(ax):
    """Force the draw pass, where style lookups happen."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        ax._figure.save(str(Path(d) / "f.png"))


@pytest.mark.parametrize("style", ["solid", "-", "dashed", "--", "dotted", ":",
                                   "dashdot", "-.", "none", None])
def test_known_linestyles_are_all_accepted(style):
    _fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1], linestyle=style)
    _render(ax)


@pytest.mark.parametrize("marker", ["*", ".", ",", "p", "h", "circle", "O"])
def test_unknown_marker_raises(marker):
    """An unrecognized shape fell through to the circle branch, so `marker="*"`
    - which matplotlib draws as a star - silently drew a dot."""
    _fig, ax = plt.subplots()
    with pytest.raises(ValueError, match="unknown marker"):
        ax.scatter([0, 1], [0, 1], marker=marker)


@pytest.mark.parametrize("marker", ["o", "s", "^", "v", "D", "+", "x"])
def test_known_markers_are_all_accepted(marker):
    _fig, ax = plt.subplots()
    ax.scatter([0, 1], [0, 1], marker=marker)
    _render(ax)


@pytest.mark.parametrize("bins", [0, -3])
def test_hist_rejects_a_non_positive_bin_count(bins):
    _fig, ax = plt.subplots()
    with pytest.raises(ValueError, match="bins"):
        ax.hist([1.0, 2.0, 3.0], bins=bins)


# -- reprs -------------------------------------------------------------------
#
# Not cosmetic: pyplotrs asks you to hold objects rather than call into a state
# machine, so the notebook and the REPL are the primary surface, and every one
# of these printed `<pyplotrs.scales.LogScale object at 0x7f...>`.

def test_no_public_object_reprs_as_a_bare_address():
    from pyplotrs import norms, scales, ticker

    fig, ax = plt.subplots(2, 2)
    objects = [
        fig, ax[0][0], fig.add_gridspec(2, 2),
        plt.subplots(projection="3d")[1], plt.subplots(projection="polar")[1],
        plt.themes.default, plt.themes.default.with_(title_size=14),
        plt.get_cmap("viridis"),
        scales.LinearScale(), scales.LogScale(), scales.SymlogScale(),
        scales.LogitScale(), scales.CategoricalScale(["a", "b"]), scales.DateScale(),
        norms.Normalize(0, 1), norms.LogNorm(), norms.TwoSlopeNorm(0.0),
        norms.BoundaryNorm([0, 1, 2]),
        ticker.ScalarFormatter(), ticker.PercentFormatter(), ticker.EngFormatter(),
        ticker.LogFormatter(), ticker.DateFormatter("%Y"),
        ticker.FixedFormatter(["a"]), ticker.StrMethodFormatter("{x}"),
        ticker.FuncFormatter(str),
    ]
    bare = [type(o).__name__ for o in objects if " object at 0x" in repr(o)]
    assert not bare, f"these still repr as a bare address: {bare}"


def test_the_theme_repr_names_a_builtin_and_stays_short():
    """The dataclass-generated repr was ~1000 characters of raw RGBA tuples."""
    assert repr(plt.themes.nature) == "<Theme 'nature'>"
    derived = repr(plt.themes.default.with_(title_size=14))
    assert "derived" in derived and len(derived) < 100, derived


def test_the_figure_repr_reports_its_shape():
    fig, axs = plt.subplots(2, 3, figsize=(400, 300))
    axs[0][0].line([1, 2], [1, 2])
    text = repr(fig)
    assert "2x3" in text and "6 axes" in text and "1 mark" in text, text


def test_the_axes_repr_reports_its_title_and_marks():
    _fig, ax = plt.subplots()
    ax.set(title="Damped sinusoids")
    ax.line([1, 2], [1, 2])
    ax.scatter([1], [1])
    text = repr(ax)
    assert "Damped sinusoids" in text and "2 marks" in text, text


# -- arriving from matplotlib ------------------------------------------------
#
# pyplotrs renames deliberately: `plot` is `line`, and the whole `set_*` family
# folds into one `set()`. Those are the API's argument, so the names are *not*
# aliased. But `AttributeError: 'Axes' object has no attribute 'plot'` tells a
# matplotlib user nothing, and that is the first thing most of them type.

@pytest.mark.parametrize("name,expected", [
    ("plot", "ax.line"),
    ("set_xlabel", "ax.set(xlabel"),
    ("set_title", "ax.set(title"),
    ("set_xlim", "ax.set(xlim"),
    ("set_xscale", "ax.set(xscale"),
    ("grid", "ax.set(grid"),
])
def test_matplotlib_axes_names_explain_themselves(name, expected):
    _fig, ax = plt.subplots()
    with pytest.raises(AttributeError) as excinfo:
        getattr(ax, name)
    message = str(excinfo.value)
    assert expected in message, message
    assert "migrating-from-matplotlib" in message


@pytest.mark.parametrize("name,expected", [
    ("savefig", "fig.save"),
    ("tight_layout", "layout is solved once"),
    ("show", "pyplotrs makes files, not windows"),
    ("gca", "there is no current figure"),
])
def test_matplotlib_figure_names_explain_themselves(name, expected):
    fig, _ax = plt.subplots()
    with pytest.raises(AttributeError) as excinfo:
        getattr(fig, name)
    assert expected in str(excinfo.value)


def test_the_names_are_not_silently_aliased():
    """The point is to explain the rename, not undo it. If `ax.plot` started
    working, the one-name-per-concept rule would be decorative."""
    _fig, ax = plt.subplots()
    for name in ("plot", "set_xlabel", "set_title"):
        assert not hasattr(ax, name), f"{name} should not exist, only explain"


def test_an_ordinary_typo_still_gets_an_ordinary_error():
    """The hook must not swallow every failed lookup into a matplotlib lecture."""
    _fig, ax = plt.subplots()
    missing = "definitely_not_a_method"  # via a variable: `ax.<literal>` is a
    with pytest.raises(AttributeError) as excinfo:  # "useless expression" to
        getattr(ax, missing)                        # the linter, and B009 to
    assert "matplotlib" not in str(excinfo.value)   # the other spelling.


def test_the_hint_table_names_only_absent_methods():
    """A name that pyplotrs actually implements must not be listed as missing -
    the hint would be unreachable, and wrong if it ever were reached."""
    from pyplotrs._util import _MATPLOTLIB_EQUIVALENTS

    _fig, ax = plt.subplots()
    wrong = [
        name for name in _MATPLOTLIB_EQUIVALENTS
        if hasattr(ax, name) or hasattr(_fig, name)
    ]
    assert not wrong, (
        f"{wrong} are implemented, so their hint can never fire - drop them "
        f"from the table rather than leaving a message that contradicts the API"
    )
