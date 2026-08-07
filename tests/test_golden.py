"""Golden-image regression tests.

The smoke tier proves a figure *renders*; this tier proves it renders the
*same*. It is what makes the "move the compute into Rust" migration safe: any
port that shifts a pixel shows up here rather than in a reader's PDF.

Rendering is byte-deterministic once the font is pinned (see ``conftest.py``),
but the comparison uses a mean-absolute-difference tolerance rather than a hash
so that last-bit floating-point differences between architectures do not turn
into red CI on an unrelated platform.

Regenerate after an intentional visual change::

    PYPLOTRS_UPDATE_GOLDEN=1 pytest tests/test_golden.py
"""

from __future__ import annotations

import math
import random

import pytest

import pyplotrs as plt
from conftest import assert_matches_golden, read_png


def _core_figure():
    """A figure exercising the main 2D vocabulary, layout and text at once."""
    random.seed(0)
    fig, axs = plt.subplots(2, 2, figsize=(560, 420))

    xs = [i / 40 for i in range(120)]
    a = axs[0][0]
    for k, label in [(1, "k=1"), (2, "k=2"), (3, "k=3")]:
        a.line(xs, [math.sin(k * x) * math.exp(-x / 6) for x in xs], label=label)
    a.set(title="Damped sinusoids", xlabel=r"time $t$ (s)", ylabel=r"$A e^{-t/\tau}$")
    a.legend()

    axs[0][1].bar(["alpha", "beta", "gamma"], [3.2, 4.8, 2.1])
    axs[0][1].set(title="Categories", ylabel="count")

    axs[1][0].hist([random.gauss(0, 1) for _ in range(500)], bins=16)
    axs[1][0].set(title="Histogram", xlabel="x")

    axs[1][1].scatter([random.gauss(0, 1) for _ in range(120)],
                      [random.gauss(0, 1) for _ in range(120)])
    axs[1][1].set(title="Scatter", xlabel="x", ylabel="y")

    fig.set(suptitle="pyplotrs golden reference")
    return fig


CASES = {
    "core": _core_figure,
}


def _theme_case(name):
    def build():
        fig, ax = plt.subplots(figsize=(300, 220), theme=name)
        ax.line([0, 1, 2, 3], [0, 1, 4, 9], label="squares")
        ax.scatter([0, 1, 2, 3], [9, 4, 1, 0], label="reversed")
        ax.set(title=f"theme: {name}", xlabel="x", ylabel="y")
        ax.legend()
        return fig
    return build


for _name in ("default", "nature", "grayscale", "presentation"):
    CASES[f"theme_{_name}"] = _theme_case(_name)


def _math_case():
    fig, ax = plt.subplots(figsize=(360, 240))
    ax.line([0, 1], [0, 1], label=r"$\sum_{j=1}^{n}\beta_j$")
    ax.set(title=r"$\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt{\pi}}{2}$",
           xlabel=r"$\alpha_i^2$", ylabel=r"$\mathbb{R}^3$")
    ax.legend()
    return fig


CASES["math"] = _math_case


def _log_case():
    fig, ax = plt.subplots(figsize=(300, 220))
    ax.line([1, 10, 100, 1000], [1, 10, 100, 1000], marker="o")
    ax.errorbar([1, 10, 100], [2, 20, 200], yerr=[0.5, 5, 50])
    ax.set(xscale="log", yscale="log", title="log-log")
    return fig


CASES["log"] = _log_case


@pytest.mark.parametrize("name", sorted(CASES))
def test_golden(name, tmp_path):
    fig = CASES[name]()
    out = tmp_path / f"{name}.png"
    fig.save(str(out))
    assert_matches_golden(out, name)


def test_render_is_deterministic(tmp_path):
    """Two saves of the same figure must be byte-identical.

    If this fails, every other golden test becomes flaky, so it is worth
    isolating the cause here.
    """
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    _core_figure().save(str(first))
    _core_figure().save(str(second))
    assert first.read_bytes() == second.read_bytes()


def test_png_dpi_scales_pixel_dimensions(tmp_path):
    fig, ax = plt.subplots(figsize=(200, 100))
    ax.line([0, 1], [0, 1])
    low, high = tmp_path / "low.png", tmp_path / "high.png"
    fig.save(str(low), dpi=100)
    fig.save(str(high), dpi=200)
    lw, lh, _ = read_png(low)
    hw, hh, _ = read_png(high)
    assert (hw, hh) == (lw * 2, lh * 2), f"dpi did not scale: {(lw, lh)} -> {(hw, hh)}"
