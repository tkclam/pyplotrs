"""Where the legend goes.

``loc="best"`` has to answer one question - which corner covers the least data -
and the honest way to answer it is to know where the ink is. That used to mean
reading ``m["xs"]``/``m["ys"]`` off each mark and skipping any mark without
them, which is *all* of bar, hist, fill and image: on a bar chart or a
histogram the scorer saw nothing at all, fell through to upper right, and the
legend's opaque box cropped the tallest bar. Line marks fared little better,
being sampled only at their vertices, so a sparse polyline could cross a
candidate box and score zero.

So the ink is rasterized instead, onto a coarse fixed occupancy grid over the
plot rect ([`_Occupancy`][pyplotrs._legend._Occupancy]). Every mark kind knows
how to stamp the *area* it covers - a bar is a rectangle, a line is a chain of
segments, an image is its extent - and a candidate box is scored by how many
occupied cells it would sit on. That makes the score an area, comparable across
kinds, and it costs the same for ten points as for ten million because the grid
is fixed and each mark is subsampled into it.
"""

from __future__ import annotations

import math

from ._const import _LEGEND_PROBE_POINTS

__all__ = ["best_position"]

#: Occupancy grid resolution over the plot rect. 48x32 puts a cell at roughly
#: 1.5% of the width, which is finer than any legend box placement decision
#: needs and small enough that the whole grid is a few hundred integers.
_GRID_W = 48
_GRID_H = 32

#: Candidate order. Ties resolve to the earliest, so the familiar upper right
#: stays the answer on an empty or symmetric plot.
_ORDER = (
    "upper right", "upper left", "lower right", "lower left",
    "upper center", "lower center",
)


class _Occupancy:
    """A coarse boolean raster of "there is ink here" over a device rect.

    Cells are addressed in device coordinates; anything landing outside the
    rect is dropped rather than clamped, since a legend can only ever sit
    inside it.
    """

    __slots__ = ("x", "y", "w", "h", "cells")

    def __init__(self, rect) -> None:
        self.x, self.y, self.w, self.h = rect
        self.cells = bytearray(_GRID_W * _GRID_H)

    def _cell(self, dx: float, dy: float):
        if self.w <= 0.0 or self.h <= 0.0:
            return None
        cx = int((dx - self.x) / self.w * _GRID_W)
        cy = int((dy - self.y) / self.h * _GRID_H)
        if 0 <= cx < _GRID_W and 0 <= cy < _GRID_H:
            return cy * _GRID_W + cx
        return None

    def point(self, dx: float, dy: float) -> None:
        if not (math.isfinite(dx) and math.isfinite(dy)):
            return
        i = self._cell(dx, dy)
        if i is not None:
            self.cells[i] = 1

    def segment(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Stamp the cells a straight run of ink passes through.

        Walked in cell-sized steps rather than by endpoint, which is the fix
        for a sparse polyline: two vertices far apart used to leave everything
        between them unmarked, so a line could cross a candidate box without
        the scorer noticing.
        """
        if not (math.isfinite(x0) and math.isfinite(y0)
                and math.isfinite(x1) and math.isfinite(y1)):
            return
        cw = self.w / _GRID_W or 1.0
        ch = self.h / _GRID_H or 1.0
        steps = int(max(abs(x1 - x0) / cw, abs(y1 - y0) / ch)) + 1
        # A single segment cannot cost more than a full traverse of the grid.
        steps = min(steps, _GRID_W + _GRID_H)
        for k in range(steps + 1):
            t = k / steps
            self.point(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)

    def rect(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Stamp a filled device rectangle (a bar, a bin, an image extent)."""
        if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
            return
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        cw = self.w / _GRID_W or 1.0
        ch = self.h / _GRID_H or 1.0
        nx = min(int((x1 - x0) / cw) + 2, _GRID_W + 1)
        ny = min(int((y1 - y0) / ch) + 2, _GRID_H + 1)
        for iy in range(ny + 1):
            dy = y0 + (y1 - y0) * (iy / ny if ny else 0.0)
            for ix in range(nx + 1):
                self.point(x0 + (x1 - x0) * (ix / nx if nx else 0.0), dy)

    def covered(self, bx: float, by: float, bw: float, bh: float) -> int:
        """How many occupied cells the box ``(bx, by, bw, bh)`` sits on."""
        if self.w <= 0.0 or self.h <= 0.0:
            return 0
        cx0 = int((bx - self.x) / self.w * _GRID_W)
        cx1 = int((bx + bw - self.x) / self.w * _GRID_W)
        cy0 = int((by - self.y) / self.h * _GRID_H)
        cy1 = int((by + bh - self.y) / self.h * _GRID_H)
        cx0 = max(cx0, 0)
        cy0 = max(cy0, 0)
        cx1 = min(cx1, _GRID_W - 1)
        cy1 = min(cy1, _GRID_H - 1)
        n = 0
        for cy in range(cy0, cy1 + 1):
            row = cy * _GRID_W
            n += sum(self.cells[row + cx0:row + cx1 + 1])
        return n


def _subsample(n: int):
    """Indices covering ``n`` items in at most ``_LEGEND_PROBE_POINTS`` steps.

    The grid bounds the *output*, so this only bounds the work: a 10M-point
    scatter and a 100-point one both cost the same here.
    """
    step = max(1, n // _LEGEND_PROBE_POINTS)
    return range(0, n, step)


def _stamp_xy(grid: _Occupancy, m: dict, sx, sy, connected: bool) -> None:
    """Marks carrying plain ``xs``/``ys``: line, scatter, step, errorbar, stem."""
    xs, ys = m.get("xs"), m.get("ys")
    if xs is None or ys is None:
        return
    n = min(len(xs), len(ys))
    if n == 0:
        return
    prev = None
    for i in _subsample(n):
        x, y = xs[i], ys[i]
        if not (math.isfinite(x) and math.isfinite(y)):
            prev = None
            continue
        dx, dy = sx(x), sy(y)
        if connected and prev is not None:
            grid.segment(prev[0], prev[1], dx, dy)
        else:
            grid.point(dx, dy)
        prev = (dx, dy)


def _stamp_bar(grid: _Occupancy, m: dict, sx, sy) -> None:
    xs, heights, bottoms = m["xs"], m["heights"], m["bottoms"]
    half = m["width"] / 2.0
    for i in range(min(len(xs), len(heights), len(bottoms))):
        b = bottoms[i]
        grid.rect(sx(xs[i] - half), sy(b), sx(xs[i] + half), sy(b + heights[i]))


def _stamp_barh(grid: _Occupancy, m: dict, sx, sy) -> None:
    ys, widths, lefts = m["ys"], m["widths"], m["lefts"]
    half = m["height"] / 2.0
    for i in range(min(len(ys), len(widths), len(lefts))):
        left = lefts[i]
        grid.rect(sx(left), sy(ys[i] - half), sx(left + widths[i]), sy(ys[i] + half))


def _stamp_hist(grid: _Occupancy, m: dict, sx, sy) -> None:
    edges, counts = m["edges"], m["counts"]
    base = sy(0.0)
    for i in range(min(len(counts), len(edges) - 1)):
        grid.rect(sx(edges[i]), base, sx(edges[i + 1]), sy(counts[i]))


def _stamp_fill(grid: _Occupancy, m: dict, sx, sy) -> None:
    """A band is an area, so consecutive samples bound a filled quad.

    Stamping only the verticals at each sample would leave a two-point band -
    `fill_between([0, 1], 0, 1)`, a filled rectangle - as two hairlines with an
    empty middle, and the legend would happily sit in the gap.
    """
    xs, y1, y2 = m["xs"], m["y1"], m["y2"]
    # `fill_betweenx` stores the shared coordinate in `xs` but means it as y.
    horizontal = m.get("orient", "y") == "x"
    n = min(len(xs), len(y1), len(y2))
    idx = list(_subsample(n))
    if n and idx[-1] != n - 1:
        idx.append(n - 1)  # never drop the far edge of the band
    for a, b in zip(idx, idx[1:]):
        lo = min(y1[a], y1[b], y2[a], y2[b])
        hi = max(y1[a], y1[b], y2[a], y2[b])
        if horizontal:
            grid.rect(sx(lo), sy(xs[a]), sx(hi), sy(xs[b]))
        else:
            grid.rect(sx(xs[a]), sy(lo), sx(xs[b]), sy(hi))


def _stamp_image(grid: _Occupancy, m: dict, sx, sy) -> None:
    x0, x1, y0, y1 = m["extent"]
    grid.rect(sx(x0), sy(y0), sx(x1), sy(y1))


#: Which stamper each mark kind uses. A kind absent here contributes nothing,
#: which is the old behavior - but the set of such kinds is now small and
#: explicit rather than "everything that happens to lack xs/ys".
_STAMPERS = {
    "bar": _stamp_bar,
    "barh": _stamp_barh,
    "hist": _stamp_hist,
    "fill": _stamp_fill,
    "image": _stamp_image,
}

#: Kinds whose points are joined by ink, so the space between two samples is
#: covered too. The rest (scatter, stem heads) are discrete.
_CONNECTED = {"line", "step", "errorbar", "contour"}
_SCATTERED = {"scatter", "stem"}


def _ink(marks, proj) -> _Occupancy:
    grid = _Occupancy(proj.rect)
    sx, sy = proj.sx, proj.sy
    for m in marks:
        kind = m.get("kind")
        stamp = _STAMPERS.get(kind)
        if stamp is not None:
            try:
                stamp(grid, m, sx, sy)
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                # A mark missing a key it should have is a layout hint gone
                # wrong, never a reason to fail a render.
                continue
        elif kind in _CONNECTED:
            _stamp_xy(grid, m, sx, sy, connected=True)
        elif kind in _SCATTERED:
            _stamp_xy(grid, m, sx, sy, connected=False)
        else:
            # Unknown kind: fall back to whatever coordinates it carries.
            _stamp_xy(grid, m, sx, sy, connected=False)
    return grid


def best_position(marks, positions: dict, box_w: float, box_h: float, proj):
    """The candidate in ``positions`` that covers the least ink.

    ``positions`` maps a location name to its ``(x, y)`` top-left. Returns that
    pair for the winning candidate, or upper right when there is nothing to
    weigh (no projection, or a plot with no ink in it).
    """
    if proj is None:
        return positions["upper right"]

    grid = _ink(marks, proj)
    if not any(grid.cells):
        return positions["upper right"]

    best = None
    for name in _ORDER:
        pos = positions.get(name)
        if pos is None:
            continue
        bx, by = pos
        covered = grid.covered(bx, by, box_w, box_h)
        if best is None or covered < best[0]:
            best = (covered, bx, by)
            if covered == 0:
                break  # nothing can beat a clear corner
    return (best[1], best[2]) if best else positions["upper right"]
