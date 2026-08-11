"""Phase 3 benchmark matrix: pyplotrs vs matplotlib across the full

    (mark type) x (point count) x (panel count) x (output format)

grid, and the receipt behind any speed claim. Each cell times ``fig.save`` /
``fig.savefig`` and records the wall time and file size.

Note what that does and does not include, because the two libraries divide the
work differently. ``Axes.line()`` in pyplotrs only appends a mark description;
scale resolution, tick location, layout solving, text shaping, geometry and
rendering all happen inside ``save``. So for pyplotrs the timed region is very
nearly the whole pipeline, whereas matplotlib has already built its artists by
then. Data ingestion sits outside the timer for both. If anything this
understates pyplotrs rather than flattering it - but the older claim here, that
each cell timed "the export of an already-built figure", was simply wrong.

Every cell is warmed up and then reported as the best of several runs (see
``WARMUP``/``REPEATS``); a single untimed-warmup measurement charges one-off
font-cache construction to whichever cell runs first.

The total point budget ``N`` is split evenly across the panels, so a given row
does the same total drawing work regardless of how many subplots it's spread
over; that isolates the per-panel layout/chrome overhead from the per-point
geometry cost.

Usage::

    .venv/bin/python benchmarks/matrix.py            # full grid -> RESULTS.md
    .venv/bin/python benchmarks/matrix.py --quick    # small grid (fast, CI)

matplotlib (optional, `pip install '.[bench]'`) is timed alongside when
importable; otherwise the matplotlib columns read "n/a".
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import random
import sys
import time

import pyplotrs

OUT = "/tmp/pyplotrs_bench_matrix"
os.makedirs(OUT, exist_ok=True)

# Grid axes. `--quick` trims to a fast subset for CI smoke-runs.
PANELS = [(1, 1), (2, 2), (3, 3)]            # 1, 4, 9 panels
LINE_N = [10_000, 100_000, 1_000_000]
SCATTER_N = [10_000, 100_000]                # scatter is heavier; bound mpl time
FORMATS = ["pdf", "png", "svg"]

QUICK_PANELS = [(1, 1), (2, 2)]
QUICK_LINE_N = [10_000, 100_000]
QUICK_SCATTER_N = [10_000]


def _line_xy(n: int):
    step = 10.0 / n
    xs = [i * step for i in range(n)]
    ys = [math.sin(x) * math.exp(-0.00002 * x) for x in xs]
    return xs, ys


def _scatter_xy(n: int):
    random.seed(0)
    return ([random.uniform(0, 10) for _ in range(n)],
            [random.uniform(0, 10) for _ in range(n)])


def _figsize(nrows: int, ncols: int) -> tuple[float, float]:
    """Figure size in **inches**, matplotlib's unit.

    pyplotrs sizes figures in points by default, so `_build_pyplotrs` must pass
    ``units="in"`` explicitly. Omitting it silently rendered a 3.6 x 3.0 *point*
    figure - roughly ten pixels across - against matplotlib's 3.6 x 3.0 *inch*
    one, which invalidated every number this script has ever printed.
    """
    return (3.0 * ncols + 0.6, 2.4 * nrows + 0.6)


def _fmt_size(b: int) -> str:
    v = float(b)
    for unit in ("B", "KB", "MB"):
        if v < 1024:
            return f"{v:.0f}{unit}"
        v /= 1024
    return f"{v:.1f}GB"


# -- pyplotrs ----------------------------------------------------------------

def _build_pyplotrs(mark: str, n: int, nrows: int, ncols: int):
    fig, _ = pyplotrs.subplots(
        nrows, ncols, figsize=_figsize(nrows, ncols), units="in"
    )
    per = max(2, n // (nrows * ncols))
    for ax in fig.axes:
        if mark == "line":
            xs, ys = _line_xy(per)
            ax.line(xs, ys, color="C0")
        else:
            xs, ys = _scatter_xy(per)
            ax.scatter(xs, ys, color="C1", size=4.0)
    return fig


#: Untimed warm-up saves before measuring, then the number of measured repeats
#: (the minimum is reported). Both libraries do first-call work that has nothing
#: to do with the workload - matplotlib builds its font cache, pyplotrs resolves
#: and memoizes the system font - and charging that to whichever cell happens to
#: run first is how the old single-shot harness produced a "27x" headline that
#: was really a warm-up artifact.
WARMUP = 1
REPEATS = 3


def _best(save, path: str) -> tuple[float, int]:
    """Warm up, then return the best of ``REPEATS`` timed saves, with the size.

    Minimum rather than mean: the quantity of interest is the cost of the work
    itself, and every source of noise on a shared machine only ever adds time.
    """
    for _ in range(WARMUP):
        save(path)
    best = float("inf")
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        save(path)
        best = min(best, time.perf_counter() - t0)
    return best, os.path.getsize(path)


#: Raster resolution used for both libraries. They disagree by default -
#: pyplotrs `save()` is 200 dpi, matplotlib `savefig()` follows `figure.dpi` at
#: 100 - so leaving it implicit had pyplotrs rendering four times the pixels in
#: every PNG row and losing races it was never actually in.
BENCH_DPI = 100.0


def _time_pyplotrs(mark, n, nrows, ncols, fmt) -> tuple[float, int]:
    fig = _build_pyplotrs(mark, n, nrows, ncols)
    path = f"{OUT}/pyplotrs_{mark}_{n}_{nrows}x{ncols}.{fmt}"
    return _best(lambda p: fig.save(p, dpi=BENCH_DPI), path)


# -- matplotlib (optional) -------------------------------------------------

def _build_mpl(plt, mark: str, n: int, nrows: int, ncols: int):
    fig, axes = plt.subplots(nrows, ncols, figsize=_figsize(nrows, ncols))
    axlist = axes.ravel() if hasattr(axes, "ravel") else [axes]
    per = max(2, n // (nrows * ncols))
    for ax in axlist:
        if mark == "line":
            xs, ys = _line_xy(per)
            ax.plot(xs, ys)
        else:
            import numpy as np
            xs, ys = _scatter_xy(per)
            ax.scatter(np.asarray(xs), np.asarray(ys), s=4)
    return fig


def _time_mpl(plt, mark, n, nrows, ncols, fmt) -> tuple[float, int]:
    fig = _build_mpl(plt, mark, n, nrows, ncols)
    path = f"{OUT}/mpl_{mark}_{n}_{nrows}x{ncols}.{fmt}"
    try:
        return _best(lambda p: fig.savefig(p, dpi=BENCH_DPI), path)
    finally:
        plt.close(fig)


# -- per-mark-type coverage sweep --------------------------------------------
#
# The grid above sweeps N and panel count, but over only *two* mark types. That
# made "every row wins" a claim about `line` and `scatter` and nothing else -
# contour, hexbin, boxplot, pie and all of 3D had never been timed against
# matplotlib at all. This sweep trades the N/panel axes for breadth: one
# representative size per type, one panel, all three formats.

def _field(k: int = 60):
    xc = [-3 + 6 * j / (k - 1) for j in range(k)]
    yc = [-3 + 6 * i / (k - 1) for i in range(k)]
    z = [[math.sin(xc[j]) * math.cos(yc[i]) for j in range(k)] for i in range(k)]
    return xc, yc, z


def _groups(g: int = 5, n: int = 2000):
    random.seed(1)
    return [[random.gauss(i, 1.0) for _ in range(n)] for i in range(g)]


#: name -> (pyplotrs builder, matplotlib builder or None). Sizes are chosen so
#: each cell is a few milliseconds to a few hundred, not so each is equal.
def _mark_cases():
    sx, sy = _scatter_xy(20_000)
    lx, ly = _line_xy(50_000)
    xc, yc, Z = _field()
    grp = _groups()
    cats = list(range(40))
    vals = [abs(math.sin(i)) * 10 for i in cats]
    ev = [[random.uniform(0, 10) for _ in range(400)] for _ in range(12)]
    qs = 12
    qx = [[-3 + 6 * j / (qs - 1) for j in range(qs)] for _ in range(qs)]
    qy = [[-3 + 6 * i / (qs - 1)] * qs for i in range(qs)]
    qu = [[-row[0] for _ in range(qs)] for row in qy]
    qv = [[c for c in row] for row in qx]
    sparse = [[1 if (i * j) % 7 == 0 else 0 for j in range(120)] for i in range(120)]

    return {
        "line":        (lambda a: a.line(lx, ly),
                        lambda a: a.plot(lx, ly)),
        "scatter":     (lambda a: a.scatter(sx, sy, markersize=2),
                        lambda a: a.scatter(sx, sy, s=4)),
        "scatter_cmap": (lambda a: a.scatter(sx, sy, c=sy, markersize=2),
                         lambda a: a.scatter(sx, sy, c=sy, s=4)),
        "bar":         (lambda a: a.bar(cats, vals),
                        lambda a: a.bar(cats, vals)),
        "barh":        (lambda a: a.barh(cats, vals),
                        lambda a: a.barh(cats, vals)),
        "hist":        (lambda a: a.hist(sx, bins=50),
                        lambda a: a.hist(sx, bins=50)),
        "fill_between": (lambda a: a.fill_between(lx, ly, 0.0),
                         lambda a: a.fill_between(lx, ly, 0.0)),
        "step":        (lambda a: a.step(cats, vals),
                        lambda a: a.step(cats, vals)),
        "stem":        (lambda a: a.stem(cats, vals),
                        lambda a: a.stem(cats, vals)),
        "errorbar":    (lambda a: a.errorbar(cats, vals, yerr=0.5),
                        lambda a: a.errorbar(cats, vals, yerr=0.5)),
        "boxplot":     (lambda a: a.boxplot(grp),
                        lambda a: a.boxplot(grp)),
        "violinplot":  (lambda a: a.violinplot(grp),
                        lambda a: a.violinplot(grp)),
        "pie":         (lambda a: a.pie(vals[:8]),
                        lambda a: a.pie(vals[:8])),
        "imshow":      (lambda a: a.imshow(Z),
                        lambda a: a.imshow(Z)),
        "hist2d":      (lambda a: a.hist2d(sx, sy, bins=40),
                        lambda a: a.hist2d(sx, sy, bins=40)),
        "hexbin":      (lambda a: a.hexbin(sx, sy, gridsize=40),
                        lambda a: a.hexbin(sx, sy, gridsize=40)),
        "pcolormesh":  (lambda a: a.pcolormesh(xc, yc, Z),
                        lambda a: a.pcolormesh(xc, yc, Z)),
        "contour":     (lambda a: a.contour(xc, yc, Z),
                        lambda a: a.contour(xc, yc, Z)),
        "contourf":    (lambda a: a.contourf(xc, yc, Z),
                        lambda a: a.contourf(xc, yc, Z)),
        "eventplot":   (lambda a: a.eventplot(ev),
                        lambda a: a.eventplot(ev)),
        "broken_barh": (lambda a: a.broken_barh([(i, 0.6) for i in cats], (0, 1)),
                        lambda a: a.broken_barh([(i, 0.6) for i in cats], (0, 1))),
        "stackplot":   (lambda a: a.stackplot(cats, vals, vals, vals),
                        lambda a: a.stackplot(cats, vals, vals, vals)),
        "quiver":      (lambda a: a.quiver(qx, qy, qu, qv, scale=0.3),
                        lambda a: a.quiver(qx, qy, qu, qv)),
        "streamplot":  (lambda a: a.streamplot(xc, yc, [[-y for _ in xc] for y in yc],
                                               [[x for x in xc] for _ in yc]),
                        lambda a: a.streamplot(
                            __import__("numpy").asarray(xc),
                            __import__("numpy").asarray(yc),
                            __import__("numpy").asarray([[-y for _ in xc] for y in yc]),
                            __import__("numpy").asarray([[x for x in xc] for _ in yc]))),
        "spy":         (lambda a: a.spy(sparse),
                        lambda a: a.spy(sparse)),
        "matshow":     (lambda a: a.matshow(Z),
                        lambda a: a.matshow(Z)),
    }


def _mark_cases_3d():
    random.seed(2)
    n = 5000
    xs = [random.uniform(-3, 3) for _ in range(n)]
    ys = [random.uniform(-3, 3) for _ in range(n)]
    zs = [math.sin(x) * math.cos(y) for x, y in zip(xs, ys)]
    k = 50
    X = [[-3 + 6 * j / (k - 1) for j in range(k)] for _ in range(k)]
    Y = [[-3 + 6 * i / (k - 1)] * k for i in range(k)]
    Z = [[math.sin(X[i][j]) * math.cos(Y[i][j]) for j in range(k)] for i in range(k)]
    # A smooth parametric curve as well as the random walk. They are not the
    # same workload for pyplotrs: it depth-sorts a 3D line **per segment** so
    # the line can pass behind things (and itself), which matplotlib never
    # does. On a random walk that means 5k separately-rasterized paths in
    # essentially random order, which is the worst case for it; a real curve
    # is the common one. `line3d_flat` is the same semantics matplotlib uses,
    # via `depthsort=False`, and is the honest like-for-like row.
    m = 5000
    t = [i * 20 * math.pi / m for i in range(m)]
    hx = [math.cos(v) for v in t]
    hy = [math.sin(v) for v in t]
    hz = [v / (20 * math.pi) for v in t]

    return {
        "scatter3d": (lambda a: a.scatter(xs, ys, zs, markersize=2),
                      lambda a: a.scatter(xs, ys, zs, s=4)),
        "line3d_walk": (lambda a: a.plot(xs, ys, zs),
                        lambda a: a.plot(xs, ys, zs)),
        "line3d_curve": (lambda a: a.plot(hx, hy, hz),
                         lambda a: a.plot(hx, hy, hz)),
        "line3d_flat": (lambda a: a.plot(hx, hy, hz, depthsort=False),
                        lambda a: a.plot(hx, hy, hz)),
        "surface3d": (lambda a: a.surface(X, Y, Z),
                      lambda a: a.plot_surface(
                          __import__("numpy").asarray(X),
                          __import__("numpy").asarray(Y),
                          __import__("numpy").asarray(Z))),
    }


def run_marks(plt, formats=("pdf", "png", "svg")):
    """Time every mark type once per format, pyplotrs vs matplotlib."""
    rows = []
    for label, cases, is3d in (("2D", _mark_cases(), False),
                               ("3D", _mark_cases_3d(), True)):
        for name, (build_p, build_m) in cases.items():
            for fmt in formats:
                fig, ax = pyplotrs.subplots(
                    figsize=_figsize(1, 1), units="in",
                    projection=("3d" if is3d else None))
                try:
                    build_p(ax)
                except Exception as exc:            # pragma: no cover - harness
                    print(f"  {name:12} {fmt:3}  pyplotrs FAILED: {exc}")
                    continue
                path = f"{OUT}/pyplotrs_mark_{name}.{fmt}"
                ft, fsz = _best(lambda p: fig.save(p, dpi=BENCH_DPI), path)

                mt = msz = None
                if plt is not None and build_m is not None:
                    mfig = plt.figure(figsize=_figsize(1, 1))
                    max_ = (mfig.add_subplot(projection="3d") if is3d
                            else mfig.add_subplot())
                    try:
                        build_m(max_)
                        mpath = f"{OUT}/mpl_mark_{name}.{fmt}"
                        mt, msz = _best(
                            lambda p: mfig.savefig(p, dpi=BENCH_DPI), mpath)
                    except Exception as exc:        # pragma: no cover - harness
                        print(f"  {name:12} {fmt:3}  mpl FAILED: {exc}")
                    finally:
                        plt.close(mfig)

                rows.append((label, name, fmt, ft, fsz, mt, msz))
                extra = (f"   mpl {mt:7.3f}s {_fmt_size(msz):>8}  ({mt / ft:5.1f}x)"
                         if mt is not None and ft > 0 else "   mpl n/a")
                print(f"  {name:12} {fmt:3}  pyplotrs {ft:7.3f}s "
                      f"{_fmt_size(fsz):>8}{extra}")
    return rows


# -- driver ----------------------------------------------------------------

def run(quick: bool):
    panels = QUICK_PANELS if quick else PANELS
    line_n = QUICK_LINE_N if quick else LINE_N
    scatter_n = QUICK_SCATTER_N if quick else SCATTER_N

    plt = None
    if importlib.util.find_spec("matplotlib") is not None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as _plt
        plt = _plt

    rows = []  # (mark, n, panels_label, fmt, ft, fsz, mt, msz)
    cases = [("line", n) for n in line_n] + [("scatter", n) for n in scatter_n]
    for mark, n in cases:
        for nrows, ncols in panels:
            for fmt in FORMATS:
                ft, fsz = _time_pyplotrs(mark, n, nrows, ncols, fmt)
                if plt is not None:
                    mt, msz = _time_mpl(plt, mark, n, nrows, ncols, fmt)
                else:
                    mt, msz = None, None
                rows.append((mark, n, nrows * ncols, fmt, ft, fsz, mt, msz))
                print(f"  {mark:7} N={n:<8} {nrows}x{ncols} {fmt:3}  "
                      f"pyplotrs {ft:7.3f}s {_fmt_size(fsz):>8}"
                      + (f"   mpl {mt:7.3f}s {_fmt_size(msz):>8}"
                         f"  ({mt / ft:5.1f}x)" if mt is not None else ""))

    print("\nPer-mark-type coverage sweep:")
    mark_rows = run_marks(plt, formats=(("png",) if quick else FORMATS))
    return rows, mark_rows, plt is not None


def write_markdown(rows, mark_rows, have_mpl: bool, path: str):
    lines = [
        "# pyplotrs benchmark matrix",
        "",
        "Export wall-time and file size across **mark x point-count x panels x "
        "format**. `N` is the figure's *total* point budget, split evenly over "
        "the panels. Times are `save()` / `savefig()`, "
        f"best of {REPEATS} runs after {WARMUP} untimed warm-up, at a matched "
        f"{BENCH_DPI:.0f} dpi and figure size, on this machine. "
        "Regenerate with `.venv/bin/python benchmarks/matrix.py`.",
        "",
        "Read the numbers with three caveats. For pyplotrs the timed region is "
        "close to the whole pipeline - `line()` only records a mark, and layout, "
        "shaping and rendering all happen inside `save()` - whereas matplotlib "
        "has built its artists beforehand. Data ingestion is outside the timer "
        "for both, as is import time (`import pyplotrs` is ~12 ms against "
        "~237 ms for `matplotlib.pyplot`, which no row here reflects).",
        "",
        "A third caveat applies only to **PNG**: raster export in pyplotrs is "
        "multi-threaded, both in rasterizing (an expensive canvas is split into "
        "horizontal bands) and in encoding (scanline filtering and DEFLATE both "
        "run in parallel). So the `png` rows scale with the core count of the "
        f"machine that produced them - this run had {os.cpu_count()} - and will "
        "read lower on a smaller one. PDF and SVG are single-threaded, so their "
        "rows are machine-independent in a way the PNG rows are not.",
        "",
    ]
    if have_mpl:
        lines += [
            "| mark | N | panels | format | pyplotrs time | pyplotrs size | "
            "matplotlib time | matplotlib size | speedup |",
            "|---|---:|---:|---|---:|---:|---:|---:|---:|",
        ]
        for mark, n, p, fmt, ft, fsz, mt, msz in rows:
            speed = f"{mt / ft:.1f}x" if (ft > 0) else "-"
            lines.append(
                f"| {mark} | {n:,} | {p} | {fmt} | {ft:.3f}s | {_fmt_size(fsz)} | "
                f"{mt:.3f}s | {_fmt_size(msz)} | {speed} |")
    else:
        lines += [
            "_matplotlib not installed - pyplotrs-only figures._",
            "",
            "| mark | N | panels | format | pyplotrs time | pyplotrs size |",
            "|---|---:|---:|---|---:|---:|",
        ]
        for mark, n, p, fmt, ft, fsz, _mt, _msz in rows:
            lines.append(
                f"| {mark} | {n:,} | {p} | {fmt} | {ft:.3f}s | {_fmt_size(fsz)} |")
    lines.append("")
    if have_mpl:
        lines += [
            "**Reading it.** `speedup` is matplotlib-time / pyplotrs-time "
            "(>1 means pyplotrs exports faster). pyplotrs is faster on almost every "
            "cell, and the lead is largest on **vector** export (PDF/SVG) - the "
            "editable-text formats the project exists for - where line paths are "
            "simplified and scatter markers are instanced (one reused "
            "XObject/`<use>`). The lead *grows with panel count*: pyplotrs' "
            "single-pass layout amortizes per-panel chrome that matplotlib "
            "re-solves per axes.",
            "",
            "**The large single line used to be matplotlib's one win** "
            "(`N`=1e6, 1 panel, ~0.7x), when ingest and autoscale still ran in "
            "Python. That loop moved to Rust and the row now wins like the "
            "others; the table above is the current measurement, and any "
            "statement about who wins where should be read off it rather than "
            "from this paragraph.",
            "",
            "**On file size**, each format has its own story:",
            "",
            "- **PDF** - pyplotrs is smaller everywhere (subsetted fonts + "
            "instanced markers + path simplification).",
            "- **SVG, marker-heavy (scatter)** - pyplotrs is *smaller* **and** "
            "~15-22x faster: markers are one `<defs>` glyph + a `<use>` per "
            "point, versus matplotlib's per-point path, which outweighs even the "
            "embedded font.",
            "- **SVG, sparse geometry (line)** - pyplotrs is *larger*, and on "
            "purpose: it **embeds the bundled font** so the SVG is "
            "self-contained and renders identically on any machine (a pyplotrs "
            "goal - no system-font drift), with real editable `<text>`; "
            "matplotlib only *references* a system font by name. Once the "
            "geometry is tiny (a simplified line is a few vertices), that "
            "~340 KB font floor (more with math/STIX) dominates. Shrinking it "
            "needs a cmap-preserving font subsetter - a tracked future "
            "optimization, since the Typst `subsetter` drops the `cmap` that "
            "`<text>` relies on.",
            "- **PNG** - it splits by content, and neither library wins "
            "outright. pyplotrs is *smaller* on ordinary marks (line, contour, "
            "streamplot, stackplot, matshow), where per-scanline adaptive "
            "filtering suits large flat areas. It is *larger* wherever many "
            "marks pile up and overlap - scatter, hexbin, eventplot, spy - "
            "because matplotlib's mature Agg composites those into flatter, "
            "more compressible pixels than a field of individually antialiased "
            "sprites. A small, constant part of that gap (~30 bytes per 256 KB "
            "chunk) is the price of compressing the image in parallel: each "
            "chunk restarts DEFLATE's window and emits its own Huffman tables.",
            "",
            "See `benchmarks/benchmark.py` for the like-for-like single-panel head-to-head "
            "and the deterministic `--check` CI regression gate.",
            "",
        ]

    # -- second table: every mark type, once ---------------------------------
    if mark_rows:
        lines += [
            "## Per-mark-type coverage",
            "",
            "The grid above sweeps point count and panel count but over only "
            "**two** mark types, so \"every row wins\" was a statement about "
            "`line` and `scatter`. This table trades those axes for breadth: "
            "every mark type once, one panel, at a representative size. It is "
            "the first time contour, hexbin, boxplot, pie and the 3D types have "
            "been timed against matplotlib at all.",
            "",
        ]
        if have_mpl:
            lines += [
                "| kind | mark | format | pyplotrs time | pyplotrs size | "
                "matplotlib time | matplotlib size | speedup |",
                "|---|---|---|---:|---:|---:|---:|---:|",
            ]
            for kind, name, fmt, ft, fsz, mt, msz in mark_rows:
                if mt is None:
                    lines.append(
                        f"| {kind} | {name} | {fmt} | {ft:.3f}s | "
                        f"{_fmt_size(fsz)} | n/a | n/a | - |")
                else:
                    lines.append(
                        f"| {kind} | {name} | {fmt} | {ft:.3f}s | "
                        f"{_fmt_size(fsz)} | {mt:.3f}s | {_fmt_size(msz)} | "
                        f"{mt / ft:.1f}x |")
        else:
            lines += [
                "| kind | mark | format | pyplotrs time | pyplotrs size |",
                "|---|---|---|---:|---:|",
            ]
            for kind, name, fmt, ft, fsz, _mt, _msz in mark_rows:
                lines.append(f"| {kind} | {name} | {fmt} | {ft:.3f}s | "
                             f"{_fmt_size(fsz)} |")
        lines.append("")

    with open(path, "w") as fh:
        fh.write("\n".join(lines))
    print(f"\nwrote {path} ({len(rows)} grid rows, {len(mark_rows)} mark rows)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true",
                    help="small grid for a fast smoke run")
    ap.add_argument("-o", "--out", default=os.path.join(
        os.path.dirname(__file__), "RESULTS.md"))
    args = ap.parse_args()
    print(f"=== pyplotrs benchmark matrix ({'quick' if args.quick else 'full'}) ===")
    rows, mark_rows, have_mpl = run(args.quick)
    write_markdown(rows, mark_rows, have_mpl, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
