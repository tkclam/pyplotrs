"""Regression tests for specific defects.

Each test here corresponds to a bug that shipped and went unnoticed because
nothing exercised the path. Keep the reproduction minimal and name the symptom,
so a future failure reads as "this exact thing broke again".
"""

from __future__ import annotations

import re

import pytest

import pyplotrs as plt
from pyplotrs.theme import parse_color


# -- colour parsing ----------------------------------------------------------

def test_float_rgb_is_not_truncated_to_black():
    """``(0.2, 0.4, 0.6)`` is matplotlib's colour convention: floats in 0-1.

    pyplotrs took byte tuples and ran them through ``int()``, so every float
    colour silently collapsed to black with no error - the worst kind of bug for
    someone porting a script over.
    """
    palette = plt.themes.default.palette
    assert parse_color((0.2, 0.4, 0.6), palette) == (51, 102, 153, 255)
    assert parse_color((1.0, 0.0, 0.0), palette) == (255, 0, 0, 255)
    assert parse_color((0.5, 0.5, 0.5), palette) == (128, 128, 128, 255)
    assert parse_color((1.0, 1.0, 1.0), palette) == (255, 255, 255, 255)


def test_byte_rgb_still_works():
    """Byte tuples must keep their meaning; the two conventions have to coexist."""
    palette = plt.themes.default.palette
    assert parse_color((255, 0, 0), palette) == (255, 0, 0, 255)
    assert parse_color((0, 114, 178, 255), palette) == (0, 114, 178, 255)
    assert parse_color((12, 34, 56), palette) == (12, 34, 56, 255)


def test_hex_and_named_colors_are_accepted():
    palette = plt.themes.default.palette
    assert parse_color("#ff0000", palette) == (255, 0, 0, 255)
    assert parse_color("#f00", palette) == (255, 0, 0, 255)
    assert parse_color("#0072b280", palette) == (0, 114, 178, 128)
    assert parse_color("red", palette) == (255, 0, 0, 255)
    assert parse_color("steelblue", palette) == (70, 130, 180, 255)


def test_palette_indices_still_resolve_against_the_theme():
    assert parse_color("C0", plt.themes.default.palette) == (0, 114, 178, 255)
    assert parse_color("C0", plt.themes.grayscale.palette) == (0, 0, 0, 255)


def test_unknown_color_string_still_raises():
    with pytest.raises(ValueError):
        parse_color("not-a-color", plt.themes.default.palette)


# -- legend ------------------------------------------------------------------

def test_barh_with_label_and_legend(tmp_path):
    """``ax.barh(label=...)`` + ``ax.legend()`` raised ``KeyError: 'linestyle'``.

    The legend glyph dispatcher fell through to its line branch, which reads a
    key the barh mark never sets.
    """
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.barh([0, 1, 2], [3, 5, 2], label="values")
    ax.legend()
    fig.save(str(tmp_path / "barh.png"))


@pytest.mark.parametrize("theme", ["default", "nature", "grayscale", "presentation"])
def test_legend_swatch_matches_the_theme_type_size(theme, tmp_path):
    """The legend box was *measured* at ``theme.legend_size`` but its swatches
    were *drawn* at a hardcoded 9.0 pt, so any theme with a different legend
    size mismatched."""
    fig, ax = plt.subplots(figsize=(240, 180), theme=theme)
    ax.line([0, 1], [0, 1], label="a")
    ax.legend()
    fig.save(str(tmp_path / f"{theme}.png"))


# -- scales at draw time -----------------------------------------------------

def test_errorbar_draws_line_and_markers_on_a_log_axis(tmp_path):
    """On a log axis ``errorbar`` silently dropped its connecting line *and* its
    markers, leaving bare whiskers.

    Two causes: the affine coefficients were recovered by sampling the transform
    at 0.0, which is ``-inf`` under a log scale; and the draw call never passed
    the scale codes, so Rust applied a linear transform. Compared against the
    equivalent ``line`` call, which always worked.
    """
    def count_marks(scale):
        fig, ax = plt.subplots(figsize=(240, 180))
        ax.errorbar([1, 10, 100], [10, 100, 1000], yerr=[1, 10, 100])
        ax.set(yscale=scale, xscale=scale)
        out = tmp_path / f"err_{scale}.svg"
        fig.save(str(out))
        svg = out.read_text()
        return svg.count("<path"), svg.count("<use")

    lin_paths, lin_uses = count_marks("linear")
    log_paths, log_uses = count_marks("log")

    assert log_uses == lin_uses, (
        f"markers vanished on a log axis: {log_uses} vs {lin_uses} on linear"
    )
    assert log_paths >= lin_paths - 1, (
        f"geometry vanished on a log axis: {log_paths} paths vs {lin_paths} on linear"
    )


def test_errorbar_respects_log_positions(tmp_path):
    """The connecting line must be drawn through log-transformed positions, not
    linear ones. On a log axis with decade-spaced data the polyline is straight,
    so its midpoint sits at the vertical centre of the plot area."""
    fig, ax = plt.subplots(figsize=(300, 300))
    ax.errorbar([1, 10, 100], [1, 10, 100], yerr=[0.1, 1, 10])
    ax.set(xscale="log", yscale="log")
    out = tmp_path / "logpos.svg"
    fig.save(str(out))
    assert "<path" in out.read_text()


# -- theming leaks -----------------------------------------------------------

def test_hist_bar_edges_follow_the_theme(tmp_path):
    """``hist`` hardcoded white bar separators, which disappear against any
    theme with a light plot background of its own - and look wrong on dark."""
    dark = plt.themes.default.with_(axes_facecolor=(30, 30, 30, 255))
    fig, ax = plt.subplots(figsize=(240, 180), theme=dark)
    ax.hist([1, 2, 2, 3, 3, 3, 4], bins=4)
    out = tmp_path / "hist_dark.svg"
    fig.save(str(out))
    svg = out.read_text()
    assert "#ffffff" not in svg.lower(), (
        "hist still emits hardcoded white edges under a dark theme"
    )


# -- 3D methods that never worked -------------------------------------------

@pytest.mark.parametrize("method", ["bar3d", "voxels", "contour3d"])
def test_3d_methods_that_referenced_undefined_helpers(method, tmp_path):
    """``bar3d`` and ``voxels`` called ``_darker``; ``contour3d`` called
    ``_bilinear_grid``. Neither helper was ever defined in any commit, so all
    three raised ``NameError`` on every call since they were written."""
    fig, ax = plt.subplots(figsize=(240, 180), projection="3d")
    xs = [-1.0, 0.0, 1.0]
    if method == "bar3d":
        ax.bar3d([0, 1], [0, 1], [0, 0], 0.5, 0.5, [1, 2])
    elif method == "voxels":
        ax.voxels([[[True, False], [False, True]], [[False, True], [True, False]]])
    else:
        X = [xs[:] for _ in xs]
        Y = [[v] * 3 for v in xs]
        Z = [[x * x + y * y for x in xs] for y in xs]
        ax.contour3d(X, Y, Z)
    fig.save(str(tmp_path / f"{method}.png"))


# -- FFI boundary hardening --------------------------------------------------

def test_degenerate_figure_size_raises_valueerror(tmp_path):
    """A zero-size figure used to unwind out of Rust as ``PanicException``.

    That derives from ``BaseException``, so ``except Exception`` did not catch
    it and the user got a Rust panic dump instead of a diagnosis.
    """
    fig, ax = plt.subplots(figsize=(0, 0))
    ax.line([0, 1], [0, 1])
    with pytest.raises(ValueError, match="must be positive"):
        fig.save(str(tmp_path / "zero.pdf"))


def test_absurd_raster_size_raises_instead_of_aborting(tmp_path):
    """A units or dpi slip can ask for a terabyte-scale raster.

    Rust's allocator *aborts the process* on OOM rather than returning, so the
    size has to be rejected before allocation - ``Pixmap::new`` returning
    ``None`` is not a defence that can be relied on.
    """
    fig, ax = plt.subplots(figsize=(4000, 3000), units="in")
    ax.line([0, 1], [0, 1])
    with pytest.raises(ValueError, match="reduce the figure size"):
        fig.save(str(tmp_path / "huge.png"), dpi=2400)


def test_empty_animation_raises():
    """Caught in Python before it reaches Rust; the Rust-side empty-frames check
    is defence in depth for any other caller of the encoder."""
    with pytest.raises(ValueError, match="positive int"):
        plt.animate(lambda i: plt.subplots()[0], 0)


def _marker_xy(fig, tmp_path, name):
    """Device coordinates of each scatter marker, read back out of the SVG."""
    out = tmp_path / f"{name}.svg"
    fig.save(str(out))
    return [(float(x), float(y)) for x, y in
            re.findall(r'<use[^>]*x="([-\d.]+)"\s+y="([-\d.]+)"', out.read_text())]


def test_equal_aspect_does_not_mirror_an_inverted_axis(tmp_path):
    """`aspect="equal"` computed its scale from *signed* spans, so a descending
    limit - which is how an inverted axis is spelled - made the unit negative
    and `new_pw` a negative width, mirroring the *other* axis. Nothing combined
    the two until `spy`, which needs both (row 0 on top, square cells).

    Checked through the real draw path: the aspect adjustment lives in `_draw`,
    not in `_proj_for`, so it only shows up in rendered geometry.
    """
    fig, ax = plt.subplots(figsize=(240, 240))
    ax.scatter([0, 3], [1, 1], marker="s")
    ax.set(xlim=(-0.5, 3.5), ylim=(3.5, -0.5), aspect="equal")
    left, right = _marker_xy(fig, tmp_path, "aspect")[:2]
    assert left[0] < right[0], (
        f"ascending x was mirrored under equal aspect: {left[0]} !< {right[0]}"
    )


def test_equal_aspect_still_squares_the_cells(tmp_path):
    """The fix must not cost the property aspect="equal" exists for: one data
    unit spans the same device length on both axes."""
    fig, ax = plt.subplots(figsize=(300, 300))
    ax.scatter([0, 2, 0], [0, 0, 2], marker="s")
    ax.set(xlim=(-0.5, 2.5), ylim=(2.5, -0.5), aspect="equal")
    pts = _marker_xy(fig, tmp_path, "square")
    origin, dx2, dy2 = pts[0], pts[1], pts[2]
    assert abs((dx2[0] - origin[0]) - abs(dy2[1] - origin[1])) < 1.0


def test_spy_orientation_is_matrix_order(tmp_path):
    """Row 0 at the top, column 0 at the left."""
    fig, ax = plt.subplots(figsize=(240, 240))
    ax.spy([[1, 0], [0, 1]])
    (x0, x1), (y0, y1) = ax._ranges()
    assert x0 < x1, "columns must run left to right"
    assert y0 > y1, "rows must run top to bottom"
    fig.save(str(tmp_path / "spy.png"))


# -- the band fast path -------------------------------------------------------

def test_fill_between_matches_its_bounds(tmp_path):
    """`fill_between` moved from a Python per-point polygon build to the Rust
    affine path (`add_band_xform`), the same one `line`/`scatter` already used.
    A 50k band went 24.7 ms -> 6.6 ms; this pins that it still draws the right
    polygon."""
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.fill_between([0, 1, 2], [1, 3, 2], 0.0)
    (x0, x1), (y0, y1) = ax._ranges()
    assert x0 <= 0.0 and x1 >= 2.0
    assert y0 <= 0.0 and y1 >= 3.0
    fig.save(str(tmp_path / "band.png"))


def test_fill_betweenx_is_the_transpose(tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.fill_betweenx([0, 1, 2], [1, 3, 2], 0.0)
    (x0, x1), (y0, y1) = ax._ranges()
    assert y0 <= 0.0 and y1 >= 2.0
    assert x0 <= 0.0 and x1 >= 3.0
    fig.save(str(tmp_path / "bandx.png"))


def test_fill_between_on_a_log_axis(tmp_path):
    """The scale transform runs inside the Rust band builder, so a non-linear
    axis must stay on the fast path rather than silently mis-mapping."""
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.fill_between([1, 10, 100], [1, 10, 100], 1.0)
    ax.set(xscale="log", yscale="log")
    fig.save(str(tmp_path / "logband.png"))


def test_fill_between_survives_non_finite_points(tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.fill_between([0, 1, 2, 3], [1, float("nan"), 2, 1], 0.0)
    fig.save(str(tmp_path / "nanband.png"))


def test_degenerate_band_draws_nothing(tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.fill_between([0.0], [1.0], 0.0)
    fig.save(str(tmp_path / "tiny.png"))


def test_hexbin_output_is_reproducible(tmp_path):
    """`hexbin` binned into two `HashMap`s and emitted them in iteration order,
    which Rust randomizes per process. The same data therefore drew its
    hexagons in a different order on every run, and since neighbours share an
    edge, the pixels on that edge changed too - so a figure was not
    reproducible and could not be golden-tested.

    Checked across *processes*, since the randomization is per-process: a
    single-process loop would have passed the whole time.
    """
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent("""
        import hashlib, random, sys
        import pyplotrs as plt
        random.seed(7)
        xs = [random.uniform(0, 10) for _ in range(2000)]
        ys = [random.uniform(0, 10) for _ in range(2000)]
        fig, ax = plt.subplots(figsize=(240, 180))
        ax.hexbin(xs, ys, gridsize=14)
        out = sys.argv[1]
        fig.save(out)
        print(hashlib.sha256(open(out, "rb").read()).hexdigest())
    """)
    digests = set()
    for i in range(3):
        r = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / f"h{i}.png")],
            capture_output=True, text=True, check=True,
        )
        digests.add(r.stdout.strip())
    assert len(digests) == 1, f"hexbin differed across processes: {digests}"


def test_data_extent_defaults_match_matplotlib():
    """`bar(width=)`, `barh(height=)` and `boxplot(widths=)` are *data extents*
    in axis units, not stroke widths.

    Phase 6 renamed 36 internal `"width"` keys to `"linewidth"` to break exactly
    that collision, and in the sweep these three signature defaults drifted down
    with the stroke ones - 0.8/0.8/0.5 became 0.6/0.6/0.35. Nothing caught it:
    the values are legal, every plot still rendered, and the golden reference
    was regenerated over the top. Pin them to matplotlib's, which is what a
    ported script expects a bar chart to look like.
    """
    import inspect

    from pyplotrs.axes import Axes

    expected = {("bar", "width"): 0.8, ("barh", "height"): 0.8,
                ("boxplot", "widths"): 0.5, ("violinplot", "widths"): 0.5}
    for (method, arg), want in expected.items():
        got = inspect.signature(getattr(Axes, method)).parameters[arg].default
        assert got == want, f"Axes.{method}({arg}=) is {got}, expected {want}"


def test_bar_occupies_most_of_its_category_slot():
    """The default above, checked where it is visible rather than in a
    signature: three categories one unit apart, so a bar spans 0.8 of the gap
    between neighbours."""
    fig, ax = plt.subplots(figsize=(300, 200))
    ax.bar(["a", "b", "c"], [1.0, 2.0, 3.0])
    mark = ax._marks[0]
    assert mark["width"] == 0.8
    assert list(mark["xs"]) == [0.0, 1.0, 2.0]
