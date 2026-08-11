"""Every public mark, rendered to every backend.

This is the broad, shallow tier: it asserts only that a figure builds and saves
without raising, and that each backend produced a plausible file. It is the tier
that catches "this method has been broken for a month and nobody noticed",
which is exactly what happened to ``barh`` + ``legend`` (see
``test_regressions.py``).
"""

from __future__ import annotations

import math
import random

import pytest

import pyplotrs as plt

FORMATS = ["pdf", "svg", "png", "html"]

# Minimal file sizes that still mean "the backend wrote a real document".
_MIN_BYTES = {"pdf": 400, "svg": 200, "png": 200, "html": 400}


def _save_all(fig, tmp_path, stem: str) -> None:
    """Save ``fig`` in every format and assert each output is non-trivial."""
    for fmt in FORMATS:
        out = tmp_path / f"{stem}.{fmt}"
        fig.save(str(out))
        assert out.exists(), f"{fmt}: nothing written"
        size = out.stat().st_size
        assert size >= _MIN_BYTES[fmt], f"{fmt}: suspiciously small ({size} bytes)"


# -- 2D marks ----------------------------------------------------------------

def _line(ax):
    ax.line([0, 1, 2, 3], [0, 1, 4, 9], label="line")


def _line_markers(ax):
    ax.line([0, 1, 2], [0, 1, 4], marker="o", linestyle="dashed", label="lm")


def _scatter(ax):
    ax.scatter([0, 1, 2], [0, 1, 4], label="scatter")


def _scatter_cmapped(ax):
    ax.scatter([0, 1, 2], [0, 1, 4], c=[0.0, 0.5, 1.0], cmap="viridis")


def _bar(ax):
    ax.bar(["a", "b", "c"], [3, 5, 2], label="bar")


def _barh(ax):
    ax.barh([0, 1, 2], [3, 5, 2], label="barh")


def _hist(ax):
    rng = random.Random(0)
    ax.hist([rng.gauss(0, 1) for _ in range(200)], bins=12, label="hist")


def _fill_between(ax):
    xs = [i / 10 for i in range(20)]
    ax.fill_between(xs, [x * x for x in xs], 0.0, label="fill")


def _fill(ax):
    ax.fill([0.1, 0.4, 0.4, 0.1], [0.1, 0.1, 0.4, 0.4], alpha=0.5)


def _loglog(ax):
    ax.loglog([1, 10, 100], [1, 100, 10000], label="loglog")


def _semilogx(ax):
    ax.semilogx([1, 10, 100], [1, 2, 3], label="semilogx")


def _semilogy(ax):
    ax.semilogy([1, 2, 3], [1, 10, 100], label="semilogy")


def _errorbar(ax):
    ax.errorbar([0, 1, 2], [1, 2, 3], yerr=[0.1, 0.2, 0.3], label="err")


def _boxplot(ax):
    rng = random.Random(1)
    ax.boxplot([[rng.gauss(0, 1) for _ in range(50)] for _ in range(3)])


def _violinplot(ax):
    rng = random.Random(2)
    ax.violinplot([[rng.gauss(0, 1) for _ in range(50)] for _ in range(3)])


def _pie(ax):
    ax.pie([3, 5, 2], labels=["a", "b", "c"])


def _imshow(ax):
    ax.imshow([[1.0, 2.0], [3.0, 4.0]])


def _reference_lines(ax):
    ax.line([0, 1], [0, 1])
    ax.axhline(0.5)
    ax.axvline(0.5)
    ax.axhspan(0.1, 0.2)
    ax.axvspan(0.1, 0.2)
    ax.axline((0, 0), slope=1.0)


def _patches(ax):
    ax.rectangle((0.1, 0.1), 0.3, 0.2)
    ax.circle((0.5, 0.5), 0.1)
    ax.ellipse((0.7, 0.3), 0.2, 0.1, angle=30.0)
    ax.polygon([(0.2, 0.7), (0.4, 0.9), (0.1, 0.9)])
    ax.arrow(0.6, 0.6, 0.2, 0.2)


def _annotations(ax):
    ax.line([0, 1], [0, 1])
    ax.text(0.2, 0.8, "plain text")
    ax.annotate("callout", (0.5, 0.5), xytext=(0.7, 0.2))


def _math(ax):
    ax.line([0, 1], [0, 1], label=r"$\alpha_i^2$")
    ax.set(title=r"$\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt{\pi}}{2}$",
           xlabel=r"$\theta$")


MARKS_2D = {
    "line": _line,
    "line_markers": _line_markers,
    "scatter": _scatter,
    "scatter_cmapped": _scatter_cmapped,
    "bar": _bar,
    "barh": _barh,
    "hist": _hist,
    "fill_between": _fill_between,
    "fill": _fill,
    "loglog": _loglog,
    "semilogx": _semilogx,
    "semilogy": _semilogy,
    "errorbar": _errorbar,
    "boxplot": _boxplot,
    "violinplot": _violinplot,
    "pie": _pie,
    "imshow": _imshow,
    "reference_lines": _reference_lines,
    "patches": _patches,
    "annotations": _annotations,
    "math": _math,
}


@pytest.mark.parametrize("name", sorted(MARKS_2D))
def test_2d_mark_renders(name, tmp_path, figure_factory):
    fig, ax = figure_factory()
    MARKS_2D[name](ax)
    ax.set(title=name, xlabel="x", ylabel="y")
    _save_all(fig, tmp_path, name)


@pytest.mark.parametrize("name", sorted(MARKS_2D))
def test_2d_mark_renders_with_legend(name, tmp_path, figure_factory):
    """Legend drawing has a per-kind glyph branch, so every labelable mark must
    survive it. This is what caught ``barh`` raising ``KeyError: 'linestyle'``."""
    fig, ax = figure_factory()
    MARKS_2D[name](ax)
    ax.legend()
    _save_all(fig, tmp_path, f"{name}_legend")


def test_transparent_png_drops_the_white_page_fill(tmp_path, figure_factory):
    """``save(path, transparent=True)`` should leave the page background at
    alpha 0 rather than opaque white, while an opaque save keeps it white -
    and colors drawn over either must come out identical (the transparent
    path demultiplies tiny-skia's premultiplied buffer before PNG-encoding)."""
    from conftest import read_png

    fig, ax = figure_factory()
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    ax.fill([0.3, 0.7, 0.7, 0.3], [0.3, 0.3, 0.7, 0.7], facecolor=(200, 30, 30, 255))

    opaque = tmp_path / "opaque.png"
    transparent = tmp_path / "transparent.png"
    fig.save(str(opaque))
    fig.save(str(transparent), transparent=True)

    ow, oh, obuf = read_png(opaque)
    tw, th, tbuf = read_png(transparent)
    assert (ow, oh) == (tw, th)

    corner = 0  # top-left pixel, outside the filled square
    assert tuple(obuf[corner:corner + 4]) == (255, 255, 255, 255)
    assert tuple(tbuf[corner:corner + 4]) == (0, 0, 0, 0)

    center = (oh // 2 * ow + ow // 2) * 4
    assert tuple(obuf[center:center + 4]) == tuple(tbuf[center:center + 4]) == (200, 30, 30, 255)


# -- 3D ----------------------------------------------------------------------

def _grid():
    xs = [-1.0, 0.0, 1.0]
    X = [xs[:] for _ in xs]
    Y = [[v] * 3 for v in xs]
    Z = [[x * x + y * y for x in xs] for y in xs]
    return X, Y, Z


MARKS_3D = {
    "scatter": lambda ax: ax.scatter([0, 1], [0, 1], [0, 1], label="s"),
    "plot": lambda ax: ax.plot([0, 1, 2], [0, 1, 0], [0, 1, 2], label="p"),
    "surface": lambda ax: ax.surface(*_grid()),
    "bar3d": lambda ax: ax.bar3d([0, 1], [0, 1], [0, 0], 0.5, 0.5, [1, 2]),
    "plot_wireframe": lambda ax: ax.plot_wireframe(*_grid()),
    "contour3d": lambda ax: ax.contour3d(*_grid()),
    "plot_trisurf": lambda ax: ax.plot_trisurf(
        [0.0, 1.0, 0.5, 1.5], [0.0, 0.0, 1.0, 1.0], [0.0, 1.0, 0.5, 1.0]),
    "quiver3d": lambda ax: ax.quiver3d([0], [0], [0], [1], [1], [1]),
    "voxels": lambda ax: ax.voxels([[[True, False], [False, True]],
                                    [[False, True], [True, False]]]),
}


@pytest.mark.parametrize("name", sorted(MARKS_3D))
def test_3d_mark_renders(name, tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180), projection="3d")
    MARKS_3D[name](ax)
    ax.set(title=name)
    _save_all(fig, tmp_path, f"3d_{name}")


# -- polar -------------------------------------------------------------------

@pytest.mark.parametrize("name", ["plot", "scatter"])
def test_polar_renders(name, tmp_path):
    fig, ax = plt.subplots(figsize=(240, 220), projection="polar")
    theta = [i * math.pi / 8 for i in range(17)]
    r = [1 + 0.5 * math.sin(3 * t) for t in theta]
    getattr(ax, name)(theta, r, label=name)
    ax.set(title=f"polar {name}")
    _save_all(fig, tmp_path, f"polar_{name}")


# -- figure-level composition ------------------------------------------------

def test_subplots_grid_renders(tmp_path):
    fig, axs = plt.subplots(2, 3, figsize=(600, 400))
    for row in axs:
        for ax in row:
            ax.line([0, 1, 2], [0, 1, 4])
    fig.set(suptitle="grid")
    _save_all(fig, tmp_path, "grid")


def test_gridspec_and_mosaic_render(tmp_path):
    fig = plt.figure(figsize=(400, 300))
    gs = fig.add_gridspec(2, 2)
    fig.add_subplot(gs[0, :]).line([0, 1], [0, 1])
    fig.add_subplot(gs[1, 0]).scatter([0, 1], [1, 0])
    fig.add_subplot(gs[1, 1]).bar(["a"], [1])
    _save_all(fig, tmp_path, "gridspec")

    fig2, axd = plt.subplot_mosaic("AB\nCC", figsize=(400, 300))
    for ax in axd.values():
        ax.line([0, 1], [0, 1])
    _save_all(fig2, tmp_path, "mosaic")


def test_colorbar_renders(tmp_path, figure_factory):
    fig, ax = figure_factory()
    im = ax.imshow([[1.0, 2.0], [3.0, 4.0]])
    fig.colorbar(im, label="value")
    _save_all(fig, tmp_path, "colorbar")


def test_twin_inset_secondary_render(tmp_path, figure_factory):
    fig, ax = figure_factory()
    ax.line([0, 1, 2], [0, 1, 4])
    ax.twinx().line([0, 1, 2], [4, 1, 0])
    ax.twiny().line([0, 1, 2], [0, 2, 1])
    ax.inset_axes([0.6, 0.6, 0.3, 0.3]).line([0, 1], [0, 1])
    ax.secondary_yaxis("right", label="secondary")
    _save_all(fig, tmp_path, "twins")


@pytest.mark.parametrize("theme", ["default", "nature", "grayscale", "presentation"])
def test_themes_render(theme, tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180), theme=theme)
    ax.line([0, 1, 2], [0, 1, 4], label="a")
    ax.scatter([0, 1, 2], [1, 0, 2], label="b")
    ax.legend()
    ax.set(title=theme, xlabel="x", ylabel="y")
    _save_all(fig, tmp_path, f"theme_{theme}")


def test_animation_renders(tmp_path):
    def render(i):
        fig, ax = plt.subplots(figsize=(160, 120))
        ax.line([0, 1, 2], [0, i, 2 * i])
        return fig

    anim = plt.animate(render, 4, fps=8)
    assert len(anim) == 4
    for ext in ("gif", "apng"):
        out = tmp_path / f"anim.{ext}"
        anim.save(str(out))
        assert out.stat().st_size > 200, f"{ext}: suspiciously small"
