"""Rendering from several threads at once.

The README promises two things about threads, and both were partly false:

* *"No global state ... the same API works cleanly under threads."* True for
  the figure objects, which share nothing. This file pins it.
* *"The GIL is released while rendering, so a thread pool over figures actually
  parallelizes."* True only of the five render entry points (`to_pdf`,
  `to_svg`, `to_png`, and the two animation encoders). The compute kernels -
  marching squares, the filled-contour rasterizer, `hist2d`, `hexbin`, the KDE,
  the histogram and the colormap mapping - all held the GIL for their whole
  run, so four threads building contour figures took as long as doing them one
  after another, and a 2000x2000 grid blocked every other thread (and Ctrl-C)
  for twelve seconds.

**Nothing here asserts a speedup.** A wall-clock ratio on a shared CI runner is
the definition of a flaky test. What is asserted instead is the property that
makes a speedup possible: while a long kernel runs, other Python threads *get
scheduled*. That is measured against a control call which is known to hold the
GIL, on the same machine in the same run, so the bar moves with the runner
rather than being a hardcoded number that a slow VM would trip over.
"""

from __future__ import annotations

import functools
import hashlib
import math
import threading
import time
from array import array

import pyplotrs as plt
import pytest
from pyplotrs import _pyplotrs_core as _core


def _save_bytes(fig) -> bytes:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "f.png"
        fig.save(str(out))
        return out.read_bytes()


def test_concurrent_rendering_is_deterministic():
    """The same figure built on eight threads must produce identical bytes.

    This is the real content of "no global state": if any of the caches in the
    Rust core (fonts, colormap LUTs, marker stamps) were racy, this is where it
    would show up as one differing output in a hundred.
    """
    from concurrent.futures import ThreadPoolExecutor

    def one(_i):
        fig, ax = plt.subplots(figsize=(240, 180))
        ax.line([0, 1, 2, 3], [0, 1, 4, 9])
        ax.set(title="determinism", xlabel="x")
        return hashlib.sha256(_save_bytes(fig)).hexdigest()

    with ThreadPoolExecutor(max_workers=8) as pool:
        digests = set(pool.map(one, range(24)))
    assert len(digests) == 1, f"threads produced {len(digests)} different renderings"


def test_many_figures_across_threads_all_render():
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: len(_save_bytes(_build(i))), range(32)))
    assert all(n > 0 for n in results)


def _build(seed: int):
    fig, ax = plt.subplots(figsize=(320, 240))
    xs = [i / 50 for i in range(200)]
    ax.line(xs, [math.sin((seed % 5 + 1) * x) for x in xs], label=f"s{seed}")
    ax.set(title=f"panel {seed}")
    ax.legend()
    return fig


# -- the GIL is actually released --------------------------------------------

def _watchdog_steps_during(call) -> tuple[int, float]:
    """Run ``call`` while a second thread counts how often it is scheduled.

    Returns ``(steps, elapsed)``. A thread that never runs during a call of
    non-trivial duration means the GIL was held throughout.
    """
    steps = 0
    stop = threading.Event()

    def tick():
        nonlocal steps
        while not stop.is_set():
            steps += 1
            time.sleep(0.001)

    watcher = threading.Thread(target=tick, daemon=True)
    watcher.start()
    try:
        started = time.perf_counter()
        call()
        elapsed = time.perf_counter() - started
    finally:
        stop.set()
        watcher.join(timeout=1.0)
    return steps, elapsed


@functools.lru_cache(maxsize=1)
def _gil_held_rate() -> float:
    """Watchdog steps per millisecond for a call that provably holds the GIL.

    The threshold has to be calibrated on the machine running the test, not
    hardcoded: a slow runner scores lower across the board, and the interesting
    quantity is the *ratio*. `sorted()` over a few million ints is one C call
    that never releases the GIL, so it measures the floor.

    It is not zero. A watchdog started just before the call and stopped just
    after gets a step or two in at each edge, which is exactly why this test
    cannot simply assert `steps > 0` - a fully GIL-bound call still scored 3.
    """
    reversed_ints = list(range(4_000_000))[::-1]
    steps, elapsed = _watchdog_steps_during(lambda: sorted(reversed_ints))
    return steps / max(elapsed * 1000.0, 1e-9)


def _rough_grid(n: int) -> array:
    """A field with no local structure, so marching squares actually has work.

    A smooth `sin*cos` grid of the same size runs 50x faster - almost every
    cell is entirely above or below the level and exits immediately - which is
    too quick to observe a thread switch in. Generated from a linear
    congruential sequence rather than `random` so the timing does not depend on
    the interpreter's RNG.
    """
    state = 12345
    out = array("d")
    for _ in range(n * n):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        out.append(state / 0x3FFFFFFF - 1.0)
    return out


@pytest.mark.parametrize("name", ["contour_lines", "contourf_image", "hist2d", "hexbin"])
def test_compute_kernels_release_the_gil(name):
    """Each kernel must let another thread run while it works.

    Every case is sized to take roughly 30-500 ms: long enough that a watchdog
    thread would be scheduled many times over, short enough not to slow the
    suite. Measured here: these score 0.33-0.89 scheduler steps per ms against
    0.05 for the GIL-holding control, so the 3x bar has a wide margin on both
    sides.
    """
    n = 420
    grid = _rough_grid(n)
    levels = array("d", [i / 12.0 - 0.5 for i in range(1, 12)])
    npts = 1_000_000
    xs = array("d", [(i * 7919 % 10000) / 10000.0 for i in range(npts)])
    ys = array("d", [(i * 6271 % 10000) / 10000.0 for i in range(npts)])

    calls = {
        "contour_lines": lambda: _core.contour_lines(grid, n, n, levels),
        "contourf_image": lambda: _core.contourf_image(
            grid, n, n, levels, [0] * (4 * (len(levels) - 1)), 6),
        "hist2d": lambda: _core.hist2d(xs, ys, 1200, 1200, 0.0, 1.0, 0.0, 1.0),
        "hexbin": lambda: _core.hexbin(xs, ys, 400, 0.0, 1.0, 0.0, 1.0),
    }

    steps, elapsed = _watchdog_steps_during(calls[name])
    if elapsed < 0.02:  # pragma: no cover - only on a machine far faster than any CI runner
        pytest.skip(f"{name} finished in {elapsed * 1000:.1f} ms - too fast to observe")

    rate = steps / (elapsed * 1000.0)
    control = _gil_held_rate()
    assert rate > control * 3.0, (
        f"{name} ran for {elapsed * 1000:.0f} ms and scheduled another thread "
        f"{rate:.2f} times per ms, against {control:.2f} for a call that is "
        f"known to hold the GIL. It is holding the GIL for its whole run."
    )
