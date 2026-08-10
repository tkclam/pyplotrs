"""Pure data and geometry helpers for the Figure/Axes layer.

Nothing here touches a Scene or a Theme: these are array coercion, range
folding, and the small geometric routines - clipping, interpolation,
quantiles, triangulation, streamline integration - that the axes classes build
on. Kept separate so the drawing code has an obvious, testable floor under it.
"""

from __future__ import annotations

import math
from array import array

from . import _pyplotrs_core as _core

from ._const import _DATA_PAD, _UNIT_TO_PT


def _figsize_to_points(figsize, units: str) -> tuple[float, float]:
    """Convert a ``(w, h)`` figure size in ``units`` to points."""
    try:
        factor = _UNIT_TO_PT[units]
    except KeyError:
        raise ValueError(
            f"unknown units {units!r}; expected one of {sorted(_UNIT_TO_PT)}"
        )
    w, h = figsize
    return (float(w) * factor, float(h) * factor)


def _with_alpha(color: tuple[int, int, int, int], alpha: float) -> tuple[int, int, int, int]:
    """Scale ``color``'s alpha channel by ``alpha`` in [0, 1]."""
    r, g, b, a = color
    return (r, g, b, max(0, min(255, int(a * alpha))))


def _as_seq(value, n: int) -> list[float]:
    """Coerce a scalar or sequence into a length-``n`` list of floats."""
    try:
        items = list(value)
    except TypeError:
        return [float(value)] * n
    return [float(v) for v in items]


def _to_f64(values) -> "array":
    """Coerce a numeric sequence to a contiguous ``array.array("d")``.

    This is the single ingest point for coordinate data, and the reason large
    plots are fast. ``array("d")`` exposes the buffer protocol, so the Rust side
    copies it out with a memcpy instead of calling ``__float__`` once per
    element; the same is true of a NumPy ``float64`` array, which is passed
    straight through its own buffer here. Everything else falls back to an
    element-wise conversion, which is still one pass rather than the three the
    old ingest made.

    ``array`` rather than NumPy deliberately: it is standard library (pyplotrs
    has no runtime dependencies) and it has list-like truthiness, so the
    ``if some_coords:`` checks scattered through this module keep working -
    a NumPy array would raise "truth value is ambiguous" instead.
    """
    if type(values) is array and values.typecode == "d":
        return values
    try:
        view = memoryview(values)
    except TypeError:
        pass
    else:
        if view.ndim == 1 and view.c_contiguous:
            if view.format == "d":
                out = array("d")
                out.frombytes(view.cast("B"))  # memcpy
                return out
            # Some other contiguous numeric type (float32, int64, ...): one
            # C-level pass, still far cheaper than a Python comprehension.
            try:
                return array("d", view)
            except (TypeError, ValueError):
                pass
    # A plain list/tuple/generator. `array("d", ...)` converts in C and raises
    # on the first non-number, which doubles as the "are these numeric?" test -
    # so the common case never pays for a separate isinstance scan.
    try:
        return array("d", values)
    except (TypeError, ValueError):
        return array("d", [float(v) for v in values])


def _concat(arrays: list) -> "array":
    """Join coordinate arrays into one. Only the non-linear-scale autoscaling
    path needs this; the linear path folds bounds instead (see :class:`_RangeAcc`)."""
    if not arrays:
        return array("d")
    if len(arrays) == 1:
        return _to_f64(arrays[0])
    out = array("d")
    for a in arrays:
        out.extend(_to_f64(a))
    return out


def _data_range(values, pad: float = _DATA_PAD) -> tuple[float, float]:
    """Padded ``(lo, hi)`` over the finite members of ``values``.

    Non-finite data is ignored, as matplotlib does, so a single ``NaN``/``inf``
    (common in real data with gaps) can't collapse an axis to ``(-inf, inf)``.
    The scan itself runs in Rust - it used to be a Python ``math.isfinite``
    comprehension plus ``min``/``max``, three passes over a full intermediate
    list, and it accounted for 79% of a one-million-point export.
    """
    return _pad_range(_core.data_range(_to_f64(values)))


def _pad_range(bounds: tuple[float, float] | None,
               pad: float = _DATA_PAD) -> tuple[float, float]:
    """Apply the data margin to a raw ``(lo, hi)``; ``None`` means no data."""
    if bounds is None:
        return (0.0, 1.0)
    lo, hi = bounds
    if lo == hi:
        lo -= 0.5
        hi += 0.5
    span = hi - lo
    return lo - span * pad, hi + span * pad


class _RangeAcc:
    """Running finite ``(lo, hi)`` over many marks, without concatenating them.

    Autoscaling used to build one Python list holding *every point of every
    mark* and scan that. This keeps only the running bounds: each bulk array is
    reduced in Rust and folded in, so the cost is O(points) in Rust and O(marks)
    in Python instead of O(points) in Python plus a full copy.

    Bulk arrays are also retained by reference (never copied) for
    :meth:`arrays`, because non-linear scales do their own domain-aware
    autoscaling and need the values, not just the bounds.
    """

    __slots__ = ("lo", "hi", "_arrays")

    def __init__(self) -> None:
        self.lo = math.inf
        self.hi = -math.inf
        self._arrays: list = []

    def _fold(self, bounds: tuple[float, float] | None) -> None:
        if bounds is not None:
            lo, hi = bounds
            if lo < self.lo:
                self.lo = lo
            if hi > self.hi:
                self.hi = hi

    def add_array(self, values) -> None:
        """Fold in a bulk coordinate array (reduced in Rust)."""
        if len(values) == 0:
            return
        self._arrays.append(values)
        self._fold(_core.data_range(values))

    def add_offsets(self, values, offsets, *, two_sided: bool = True) -> None:
        """Fold in ``values + offsets``, and ``values - offsets`` too when
        ``two_sided``, reduced in Rust without building the intermediates.

        ``two_sided=True`` is an errorbar (the whisker extends both ways);
        ``False`` is a bar, which runs from its base to ``base + height`` and
        nowhere else."""
        if len(values) == 0 or offsets is None or len(offsets) == 0:
            return
        bounds = _core.offset_range(values, offsets, two_sided)
        self._fold(bounds)
        if bounds is not None:
            self._arrays.append(array("d", bounds))

    def add(self, *scalars: float) -> None:
        """Fold in a handful of individual values (bar edges, extents, ...)."""
        finite = [v for v in scalars if math.isfinite(v)]
        if finite:
            self._fold((min(finite), max(finite)))
            self._arrays.append(array("d", finite))

    @property
    def empty(self) -> bool:
        return self.lo > self.hi

    def bounds(self) -> tuple[float, float] | None:
        """Raw finite ``(lo, hi)``, or ``None`` if nothing finite was added."""
        return None if self.empty else (self.lo, self.hi)

    def padded(self, pad: float = _DATA_PAD) -> tuple[float, float]:
        return _pad_range(self.bounds(), pad)

    def arrays(self) -> list:
        """Every contributed array, for scales that autoscale their own domain."""
        return self._arrays


def _to_f64_grid(data) -> tuple["array", int, int]:
    """Flatten a 2D grid to ``(values, nrows, ncols)`` in row-major order.

    A contiguous 2D buffer (a NumPy array) is taken whole with a single cast -
    no per-pixel Python. Otherwise each row is converted individually, which is
    still one pass rather than the nested comprehension plus separate flatten
    this replaces.
    """
    try:
        view = memoryview(data)
    except TypeError:
        view = None
    if view is not None and view.ndim == 2 and view.c_contiguous:
        h, w = view.shape
        if view.format == "d":
            out = array("d")
            out.frombytes(view.cast("B"))  # memcpy
        else:
            out = array("d", view.cast(view.format, (h * w,)))
        return out, h, w

    rows = list(data)
    h = len(rows)
    if h == 0:
        return array("d"), 0, 0
    flat = array("d")
    w = -1
    for row in rows:
        converted = _to_f64(row)
        if w < 0:
            w = len(converted)
        elif len(converted) != w:
            raise ValueError(
                f"image rows must all be the same length; got {len(converted)} after {w}"
            )
        flat.extend(converted)
    return flat, h, max(w, 0)


def _circle_pts(cx: float, cy: float, r: float, n: int = 24) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(2.0 * math.pi * i / n), cy + r * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    ]


def _clip_segment(x0, y0, x1, y1, rx, ry, rw, rh):
    """Liang-Barsky clip of segment ``(x0,y0)-(x1,y1)`` to rect ``(rx,ry,rw,rh)``.
    Returns the clipped endpoints, or ``None`` if the segment misses the rect."""
    dx, dy = x1 - x0, y1 - y0
    p = [-dx, dx, -dy, dy]
    q = [x0 - rx, rx + rw - x0, y0 - ry, ry + rh - y0]
    t0, t1 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if pi == 0:
            if qi < 0:
                return None  # parallel and outside
        else:
            r = qi / pi
            if pi < 0:
                if r > t1:
                    return None
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return None
                if r < t1:
                    t1 = r
    return (x0 + t0 * dx, y0 + t0 * dy, x0 + t1 * dx, y0 + t1 * dy)


def _step_points(xs: list[float], ys: list[float], where: str
                 ) -> tuple[list[float], list[float]]:
    """Expand ``(xs, ys)`` into a staircase polyline for ``step``. ``where`` is
    ``pre`` (step before the point), ``post`` (after), or ``mid`` (halfway)."""
    px: list[float] = []
    py: list[float] = []
    for i in range(len(xs)):
        if i == 0:
            px.append(xs[0]); py.append(ys[0])
            continue
        if where == "pre":
            px += [xs[i - 1], xs[i]]; py += [ys[i], ys[i]]
        elif where == "post":
            px += [xs[i], xs[i]]; py += [ys[i - 1], ys[i]]
        else:  # mid
            xm = (xs[i - 1] + xs[i]) / 2.0
            px += [xm, xm, xs[i]]; py += [ys[i - 1], ys[i], ys[i]]
    return px, py


def _quantile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated quantile of an already-sorted list (matplotlib default)."""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def _boxstats(values: list[float], whis: float = 1.5) -> dict:
    """Box-plot summary: quartiles, median, whisker ends (last point within
    ``whis``·IQR), and the outliers beyond them."""
    s = sorted(v for v in values if math.isfinite(v))
    if not s:
        return {"q1": 0.0, "med": 0.0, "q3": 0.0, "lo": 0.0, "hi": 0.0, "fliers": []}
    q1, med, q3 = _quantile(s, 0.25), _quantile(s, 0.5), _quantile(s, 0.75)
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - whis * iqr, q3 + whis * iqr
    inside = [v for v in s if lo_fence <= v <= hi_fence]
    lo = inside[0] if inside else q1
    hi = inside[-1] if inside else q3
    fliers = [v for v in s if v < lo_fence or v > hi_fence]
    return {"q1": q1, "med": med, "q3": q3, "lo": lo, "hi": hi, "fliers": fliers}


def _auto_levels(flat: list[float], levels, default_n: int = 8) -> list[float]:
    """Resolve a ``levels`` argument into a sorted list of contour thresholds.
    An int (or ``None``) picks that many evenly-spaced levels spanning the data."""
    finite = [v for v in flat if math.isfinite(v)]
    lo, hi = (min(finite), max(finite)) if finite else (0.0, 1.0)
    if levels is None:
        n = default_n
    elif isinstance(levels, int):
        n = levels
    else:
        return sorted(float(v) for v in levels)
    if hi <= lo:
        hi = lo + 1.0
    step = (hi - lo) / (n + 1)
    return [lo + step * (i + 1) for i in range(n)]


def _subdivide(majors: list[float], n: int, lo: float, hi: float) -> list[float]:
    """``n`` evenly spaced minor values inside each major interval.

    A linear axis has no canonical subdivision the way a log axis does (2..9
    x 10^k), so the count is the caller's choice and the spacing comes from the
    located major ticks. Extends half an interval past the end majors so the
    subdivision does not stop short of the view, and clips to ``lo..hi``.
    """
    if n < 2 or len(majors) < 2:
        return []
    step = (majors[1] - majors[0]) / n
    if step == 0.0:
        return []
    out: list[float] = []
    v = majors[0] - step * (n - 1)
    end = majors[-1] + step * (n - 1)
    major_set = {round(m, 12) for m in majors}
    view_lo, view_hi = (lo, hi) if lo <= hi else (hi, lo)
    while v <= end + step * 0.5:
        if view_lo <= v <= view_hi and round(v, 12) not in major_set:
            out.append(v)
        v += step
    return out


def _flatten2d(values):
    """Flatten a 2D grid row-major; pass a 1D sequence straight through.

    Lets the grid-shaped inputs (``quiver`` meshes) and the point-list form
    reach the same ingest path.
    """
    return [v for row in values for v in row] if _is_2d(values) else values


def _streamlines(xc, yc, gu, gv, density: float = 1.0, maxlength: float = 4.0):
    """Trace streamlines of the field ``(gu, gv)`` over the grid ``(xc, yc)``.

    Integration runs in **index space** (fractional row/column), where a step
    is one cell regardless of the data units, and the field is normalized to
    unit length so the step size is arc length rather than speed - otherwise a
    slow region would be sampled to death and a fast one would skip cells.
    RK4 with a quarter-cell step; every sub-step is bounds-checked, since the
    field is only defined inside the grid.

    Seeds are laid on a ``density``-scaled lattice and a coarse occupancy mask
    stops a trajectory that wanders into a cell another one already covers,
    which is what keeps the picture readable instead of a solid mat of lines.

    Yields ``(xs, ys)`` in **data** coordinates.
    """
    h = len(gu)
    w = len(gu[0]) if gu else 0
    dx = ((xc[-1] - xc[0]) / (w - 1) if w > 1 else 1.0) or 1.0
    dy = ((yc[-1] - yc[0]) / (h - 1) if h > 1 else 1.0) or 1.0

    def inside(r, c):
        return 0.0 <= r <= h - 1 and 0.0 <= c <= w - 1

    def direction(r, c):
        """Unit ``(dr, dc)`` in index space, or ``None`` at a stagnation point."""
        uu = _bilinear_grid(gu, r, c) / dx
        vv = _bilinear_grid(gv, r, c) / dy
        mag = math.hypot(uu, vv)
        if mag < 1e-12:
            return None
        return vv / mag, uu / mag

    ds = 0.25
    nm = max(2, int(round(25 * density)))
    mask = [[False] * nm for _ in range(nm)]

    def cell(r, c):
        return (min(nm - 1, max(0, int(r / max(h - 1, 1e-9) * nm))),
                min(nm - 1, max(0, int(c / max(w - 1, 1e-9) * nm))))

    def rk4(r, c, sign):
        k1 = direction(r, c)
        if k1 is None:
            return None
        r2, c2 = r + sign * ds / 2 * k1[0], c + sign * ds / 2 * k1[1]
        k2 = direction(r2, c2) if inside(r2, c2) else None
        if k2 is None:
            return None
        r3, c3 = r + sign * ds / 2 * k2[0], c + sign * ds / 2 * k2[1]
        k3 = direction(r3, c3) if inside(r3, c3) else None
        if k3 is None:
            return None
        r4, c4 = r + sign * ds * k3[0], c + sign * ds * k3[1]
        k4 = direction(r4, c4) if inside(r4, c4) else None
        if k4 is None:
            return None
        return (r + sign * ds / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]),
                c + sign * ds / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]))

    max_steps = max(1, int(maxlength * max(h, w) / ds))

    def trace(r0, c0, sign):
        pts = [(r0, c0)]
        r, c = r0, c0
        home = cell(r0, c0)
        for _ in range(max_steps):
            nxt = rk4(r, c, sign)
            if nxt is None:
                break
            r, c = nxt
            if not inside(r, c):
                break
            here = cell(r, c)
            if here != home:
                if mask[here[0]][here[1]]:
                    break
                mask[here[0]][here[1]] = True
                home = here
            pts.append((r, c))
        return pts

    for mi in range(nm):
        for mj in range(nm):
            if mask[mi][mj]:
                continue
            r0 = (mi + 0.5) / nm * (h - 1)
            c0 = (mj + 0.5) / nm * (w - 1)
            if direction(r0, c0) is None:
                continue
            mask[mi][mj] = True
            back = trace(r0, c0, -1.0)
            fwd = trace(r0, c0, 1.0)
            path = list(reversed(back)) + fwd[1:]
            if len(path) < 2:
                continue
            yield ([_interp_coord(xc, c) for _, c in path],
                   [_interp_coord(yc, r) for r, _ in path])


def _interp_coord(coords: list[float], t: float) -> float:
    """Value of the 1D coordinate vector ``coords`` at fractional index ``t``."""
    n = len(coords)
    if n == 0:
        return t
    if n == 1:
        return coords[0]
    if t <= 0:
        return coords[0]
    if t >= n - 1:
        return coords[-1]
    i = int(math.floor(t))
    frac = t - i
    return coords[i] * (1.0 - frac) + coords[i + 1] * frac


def _field_args(args) -> tuple[list[float], list[float], list[list[float]]]:
    """Parse ``(Z)`` or ``(X, Y, Z)`` field-plot positional args into 1D x/y
    coordinate vectors and the 2D ``Z`` grid."""
    if len(args) == 1:
        Z = [[float(v) for v in row] for row in args[0]]
        h = len(Z); w = len(Z[0]) if Z else 0
        return [float(i) for i in range(w)], [float(i) for i in range(h)], Z
    X, Y, Z = args[0], args[1], args[2]
    Z = [[float(v) for v in row] for row in Z]
    # Accept 1D vectors or 2D meshgrids for X/Y (take the first row / column).
    xc = [float(v) for v in (X[0] if _is_2d(X) else X)]
    yc = [float(v) for v in ([r[0] for r in Y] if _is_2d(Y) else Y)]
    return xc, yc, Z


def _is_2d(a) -> bool:
    try:
        return hasattr(a[0], "__len__")
    except (TypeError, IndexError):
        return False


def _delaunay(points: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """Bowyer-Watson Delaunay triangulation of 2D ``points``. Returns index
    triples into ``points`` (used by ``plot_trisurf``). No NumPy/scipy."""
    n = len(points)
    if n < 3:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    dx = (maxx - minx) or 1.0
    dy = (maxy - miny) or 1.0
    dmax = max(dx, dy)
    midx, midy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    # A super-triangle enclosing every point (indices n, n+1, n+2).
    pts = list(points) + [(midx - 20 * dmax, midy - dmax),
                          (midx, midy + 20 * dmax),
                          (midx + 20 * dmax, midy - dmax)]

    def circumcircle(i, j, k):
        ax, ay = pts[i]; bx, by = pts[j]; cx, cy = pts[k]
        d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-12:
            return None
        a2 = ax * ax + ay * ay
        b2 = bx * bx + by * by
        c2 = cx * cx + cy * cy
        ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
        uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
        r2 = (ax - ux) ** 2 + (ay - uy) ** 2
        return ux, uy, r2

    tris = [(n, n + 1, n + 2)]
    circ = {tris[0]: circumcircle(*tris[0])}
    for ip in range(n):
        px, py = pts[ip]
        bad = []
        for tri in tris:
            cc = circ.get(tri)
            if cc and (px - cc[0]) ** 2 + (py - cc[1]) ** 2 <= cc[2] + 1e-12:
                bad.append(tri)
        # Boundary of the polygonal hole = edges not shared by two bad triangles.
        edge_count: dict = {}
        for a, b, c in bad:
            for e in ((a, b), (b, c), (c, a)):
                key = (min(e), max(e))
                edge_count[key] = edge_count.get(key, 0) + 1
        boundary = [e for e, cnt in edge_count.items() if cnt == 1]
        for tri in bad:
            tris.remove(tri)
            circ.pop(tri, None)
        for a, b in boundary:
            tri = (a, b, ip)
            tris.append(tri)
            circ[tri] = circumcircle(*tri)
    # Drop triangles touching the super-triangle vertices.
    return [(a, b, c) for a, b, c in tris if a < n and b < n and c < n]


def _is_uniform(coords: list[float], tol: float = 1e-6) -> bool:
    """Whether ``coords`` is evenly spaced (so a mesh can route to ``imshow``)."""
    if len(coords) < 3:
        return True
    step = coords[1] - coords[0]
    if step == 0:
        return False
    return all(abs((coords[i + 1] - coords[i]) - step) <= abs(step) * tol
               for i in range(len(coords) - 1))


def _edges_from_centers(c: list[float]) -> list[float]:
    """Cell edges bracketing the coordinate centers ``c`` (midpoints inside,
    half-steps at the ends)."""
    n = len(c)
    if n == 0:
        return [0.0, 1.0]
    if n == 1:
        return [c[0] - 0.5, c[0] + 0.5]
    edges = [c[0] - (c[1] - c[0]) / 2.0]
    for i in range(n - 1):
        edges.append((c[i] + c[i + 1]) / 2.0)
    edges.append(c[-1] + (c[-1] - c[-2]) / 2.0)
    return edges


def _bilinear_grid(grid: list[list[float]], row: float, col: float) -> float:
    """Sample ``grid[row][col]`` at *fractional* indices by bilinear interpolation.

    The Rust marching-squares kernel (``_core.contour_lines``) reports crossing
    points in grid-index space - a point on the edge between columns 2 and 3 of
    row 4 comes back as ``(2.4, 4.0)``. Mapping those back onto the caller's
    ``X``/``Y`` coordinate grids is what this does.
    """
    nr = len(grid)
    nc = len(grid[0]) if nr else 0
    if nr == 0 or nc == 0:
        return 0.0
    r0 = min(max(int(row), 0), nr - 1)
    c0 = min(max(int(col), 0), nc - 1)
    r1 = min(r0 + 1, nr - 1)
    c1 = min(c0 + 1, nc - 1)
    tr = row - r0
    tc = col - c0
    top = grid[r0][c0] + (grid[r0][c1] - grid[r0][c0]) * tc
    bot = grid[r1][c0] + (grid[r1][c1] - grid[r1][c0]) * tc
    return top + (bot - top) * tr


def _darker(color: tuple[int, int, int, int], factor: float = 0.65) -> tuple[int, int, int, int]:
    """A darkened shade of ``color``, preserving alpha.

    Used for the edges of 3D boxes (``bar3d``, ``voxels``), where an outline
    derived from the fill reads as shading and keeps a solid full of adjacent
    boxes legible without introducing a second theme colour.
    """
    r, g, b, a = color
    return (int(r * factor), int(g * factor), int(b * factor), a)


def _patch_bbox(p: dict) -> tuple[list[float], list[float]]:
    """The data-space corners of a patch, for autoscaling."""
    k = p["kind"]
    if k == "rectangle":
        x0, y0 = p["xy"]
        w, h = p["w"], p["h"]
        a = math.radians(p["angle"])
        ca, sa = math.cos(a), math.sin(a)
        corners = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
        xs = [x0 + cx * ca - cy * sa for cx, cy in corners]
        ys = [y0 + cx * sa + cy * ca for cx, cy in corners]
        return xs, ys
    if k == "ellipse":
        cx, cy = p["xy"]
        rx, ry = p["rx"], p["ry"]
        a = math.radians(p["angle"])
        hw = math.hypot(rx * math.cos(a), ry * math.sin(a))
        hh = math.hypot(rx * math.sin(a), ry * math.cos(a))
        return [cx - hw, cx + hw], [cy - hh, cy + hh]
    if k == "polygon":
        return [x for x, _ in p["pts"]], [y for _, y in p["pts"]]
    if k == "arrow":
        return [p["x"], p["x"] + p["dx"]], [p["y"], p["y"] + p["dy"]]
    return [], []
