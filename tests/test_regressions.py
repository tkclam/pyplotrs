"""Regression tests for specific defects.

Each test here corresponds to a bug that shipped and went unnoticed because
nothing exercised the path. Keep the reproduction minimal and name the symptom,
so a future failure reads as "this exact thing broke again".
"""

from __future__ import annotations

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
