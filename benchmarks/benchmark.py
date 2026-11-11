"""Time saving figures with pyplotrs and, if installed, matplotlib.

    uv run --group bench python benchmarks/benchmark.py

Each case builds a figure and saves it; the best of five runs is reported.
"""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable

import numpy as np

import pyplotrs as pp

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    plt = None

rng = np.random.default_rng(0)
X = np.linspace(0, 100, 1_000_000)
Y = np.sin(X) + rng.normal(0, 0.01, X.size)
SX, SY = rng.normal(size=100_000), rng.normal(size=100_000)
TRAINS = [np.sort(rng.random(2000) * 10) for _ in range(50)]
IMG = rng.random((1000, 1000))


def pp_line(ax):
    ax.line(X, Y)


def pp_scatter(ax):
    ax.scatter(SX, SY, size=3)


def pp_raster(ax):
    ax.eventplot(TRAINS)


def pp_image(ax):
    ax.imshow(IMG)


def mpl_line(ax):
    ax.plot(X, Y)


def mpl_scatter(ax):
    ax.scatter(SX, SY, s=9)


def mpl_raster(ax):
    ax.eventplot(TRAINS)


def mpl_image(ax):
    ax.imshow(IMG)


CASES = {
    "line, 1M points": (pp_line, mpl_line),
    "scatter, 100k points": (pp_scatter, mpl_scatter),
    "raster, 100k events": (pp_raster, mpl_raster),
    "image, 1000x1000": (pp_image, mpl_image),
}


def best(fn: Callable[[], None], runs: int = 5) -> float:
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def main() -> None:
    out = tempfile.mkdtemp()
    print(f"{'case':24s} {'format':6s} {'pyplotrs':>10s} {'matplotlib':>11s} {'speedup':>8s}")
    for name, (ours, theirs) in CASES.items():
        for fmt in ("png", "pdf", "svg"):
            path = os.path.join(out, f"f.{fmt}")

            def run_pp(ours=ours, path=path) -> None:
                fig, ax = pp.subplots(figsize=(360, 270))
                ours(ax)
                fig.save(path, dpi=100)

            t_pp = best(run_pp)
            line = f"{name:24s} {fmt:6s} {t_pp * 1e3:8.1f}ms"
            if plt is not None:

                def run_mpl(theirs=theirs, path=path) -> None:
                    fig, ax = plt.subplots(figsize=(5, 3.75))
                    theirs(ax)
                    fig.savefig(path, dpi=100)
                    plt.close(fig)

                t_mpl = best(run_mpl)
                line += f" {t_mpl * 1e3:9.1f}ms {t_mpl / t_pp:7.1f}x"
            print(line)


if __name__ == "__main__":
    main()
