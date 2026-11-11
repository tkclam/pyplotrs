"""Input coercion and small numeric helpers. Nothing here draws."""

from __future__ import annotations

import itertools
import math
from array import array
from collections.abc import Iterator, Sequence, Sized
from typing import Any

from . import _core

Array = Any  # array("d") or a float64 NumPy array: anything with a float64 buffer

_NUMERIC_FORMATS = frozenset("?bBhHiIlLqQnNefdg")
UNIT_TO_PT = {"pt": 1.0, "in": 72.0, "cm": 72.0 / 2.54, "mm": 72.0 / 25.4}


def _numpy_float64(values: Any) -> Any:
    """A contiguous float64 version of a NumPy-like array (masked entries
    become NaN); anything else is returned as is."""
    dtype = getattr(values, "dtype", None)
    if dtype is None or getattr(dtype, "kind", "") not in "biuf":
        return values
    if getattr(values, "mask", None) is not None and hasattr(values, "filled"):
        values = values.astype("float64").filled(math.nan)
    out = values.astype("float64", copy=False)
    return out if out.flags["C_CONTIGUOUS"] else out.copy(order="C")


def f64(values: Any) -> Array:
    """A 1-D float64 column the Rust engine reads at memcpy speed."""
    if type(values) is array and values.typecode == "d":
        return values
    values = _numpy_float64(values)
    try:
        view = memoryview(values)
    except (TypeError, ValueError):
        view = None
    if view is not None and view.c_contiguous and view.format in _NUMERIC_FORMATS:
        if view.format == "d" and view.ndim == 1:
            return values
        return array("d", view.cast("B").cast(view.format))  # type: ignore[call-overload]
    if isinstance(values, (int, float)):
        return array("d", [float(values)])
    try:
        return array("d", values)
    except TypeError:
        return array("d", [float(v) for v in values])


def is_numeric_buffer(values: Any) -> bool:
    try:
        view = memoryview(values)
    except (TypeError, ValueError):
        return False
    return view.ndim == 1 and view.format in _NUMERIC_FORMATS


def full(value: Any, n: int) -> Array:
    """``value`` broadcast to length ``n`` if it is a scalar."""
    if isinstance(value, (int, float)):
        return array("d", [float(value)]) * n
    out = f64(value)
    if len(out) != n:
        raise ValueError(f"expected {n} values, got {len(out)}")
    return out


def same_length(mark: str, **columns: Sized) -> None:
    lengths = {k: len(v) for k, v in columns.items()}
    if len(set(lengths.values())) > 1:
        detail = ", ".join(f"{k}={n}" for k, n in lengths.items())
        raise ValueError(f"{mark}() needs {' and '.join(lengths)} of equal length; got {detail}")


def is_2d(a: Any) -> bool:
    if getattr(a, "ndim", None) is not None:
        return a.ndim == 2
    try:
        return len(a) > 0 and hasattr(a[0], "__len__") and not isinstance(a[0], str)
    except TypeError:
        return False


def grid(z: Any, name: str = "Z") -> tuple[Array, int, int]:
    """A 2-D grid as ``(row-major values, width, height)``."""
    z = _numpy_float64(z)
    try:
        view = memoryview(z)
    except (TypeError, ValueError):
        view = None
    if view is not None and view.ndim == 2 and view.c_contiguous and view.shape:
        h, w = view.shape
        return f64(view.cast("B").cast(view.format)), w, h  # type: ignore[call-overload]
    rows = [f64(r) for r in z]
    if not rows:
        return array("d"), 0, 0
    w = len(rows[0])
    for i, r in enumerate(rows):
        if len(r) != w:
            raise ValueError(
                f"{name} rows must have equal length; row 0 has {w}, row {i} has {len(r)}"
            )
    flat = array("d")
    for r in rows:
        flat.extend(r)
    return flat, w, len(rows)


def rows(values: Array, w: int, h: int) -> list[list[float]]:
    return [list(values[r * w : (r + 1) * w]) for r in range(h)]


def figsize_points(figsize: tuple[float, float], units: str) -> tuple[float, float]:
    try:
        k = UNIT_TO_PT[units]
    except KeyError:
        raise ValueError(f"unknown units {units!r}; expected one of {sorted(UNIT_TO_PT)}") from None
    w, h = (float(v) for v in figsize)
    if not (0 < w < math.inf and 0 < h < math.inf):
        raise ValueError(f"figsize must be positive and finite, got {figsize!r}")
    return w * k, h * k


# -- ranges ----------------------------------------------------------------------


def union(
    a: tuple[float, float] | None, b: tuple[float, float] | None
) -> tuple[float, float] | None:
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), max(a[1], b[1]))


def span(values: Sequence[float]) -> tuple[float, float] | None:
    vals = [v for v in values if math.isfinite(v)]
    return (min(vals), max(vals)) if vals else None


# -- statistics ------------------------------------------------------------------


def quantile(sorted_vals: Sequence[float], q: float) -> float:
    """Linearly interpolated quantile of sorted values."""
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def boxstats(values: Any, whis: float = 1.5) -> dict[str, Any]:
    """Quartiles, median, whisker ends (furthest points within ``whis`` IQRs)
    and the outliers beyond them."""
    s = sorted(v for v in f64(values) if math.isfinite(v))
    if not s:
        return {
            "q1": math.nan,
            "med": math.nan,
            "q3": math.nan,
            "lo": math.nan,
            "hi": math.nan,
            "fliers": [],
        }
    q1, med, q3 = quantile(s, 0.25), quantile(s, 0.5), quantile(s, 0.75)
    lo_fence, hi_fence = q1 - whis * (q3 - q1), q3 + whis * (q3 - q1)
    inside = [v for v in s if lo_fence <= v <= hi_fence]
    return {
        "q1": q1,
        "med": med,
        "q3": q3,
        "lo": inside[0] if inside else q1,
        "hi": inside[-1] if inside else q3,
        "fliers": [v for v in s if v < lo_fence or v > hi_fence],
    }


def steps(xs: Sequence[float], ys: Sequence[float], where: str) -> tuple[list[float], list[float]]:
    """A staircase through the points: the step happens ``"pre"``, ``"post"``
    or ``"mid"`` between neighbors."""
    if where not in ("pre", "post", "mid"):
        raise ValueError(f"where must be 'pre', 'post' or 'mid', got {where!r}")
    if not len(xs):
        return [], []
    px, py = [xs[0]], [ys[0]]
    for i in range(1, len(xs)):
        if where == "pre":
            px += [xs[i - 1], xs[i]]
            py += [ys[i], ys[i]]
        elif where == "post":
            px += [xs[i], xs[i]]
            py += [ys[i - 1], ys[i]]
        else:
            m = (xs[i - 1] + xs[i]) / 2
            px += [m, m, xs[i]]
            py += [ys[i - 1], ys[i], ys[i]]
    return px, py


def edges_from_centers(c: Sequence[float]) -> list[float]:
    if len(c) == 0:
        return [0.0, 1.0]
    if len(c) == 1:
        return [c[0] - 0.5, c[0] + 0.5]
    mids = [(a + b) / 2 for a, b in itertools.pairwise(c)]
    return [c[0] - (c[1] - c[0]) / 2, *mids, c[-1] + (c[-1] - c[-2]) / 2]


def is_uniform(c: Sequence[float], tol: float = 1e-6) -> bool:
    if len(c) < 3:
        return True
    step = c[1] - c[0]
    return step != 0 and all(
        abs((b - a) - step) <= abs(step) * tol for a, b in itertools.pairwise(c)
    )


def interp(coords: Sequence[float], t: float) -> float:
    """The value of a coordinate vector at fractional index ``t``."""
    n = len(coords)
    if n == 0:
        return t
    if t <= 0 or n == 1:
        return coords[0]
    if t >= n - 1:
        return coords[-1]
    i = math.floor(t)
    return coords[i] + (coords[i + 1] - coords[i]) * (t - i)


# -- contour levels --------------------------------------------------------------

_LEVEL_STEPS = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)


def _lattice(lo: float, hi: float, n: int) -> list[float]:
    """Round-numbered levels bracketing ``lo..hi`` in about ``n + 1`` bands."""
    raw = (hi - lo) / (n + 1)
    mag = 10.0 ** math.floor(math.log10(raw))
    step = next((m * mag for m in _LEVEL_STEPS if m * mag >= raw * (1 - 1e-12)), 10 * mag)
    mid = (lo + hi) / 2
    origin = (
        0.0
        if abs(mid) / (hi - lo) < 100
        else math.copysign(10.0 ** math.floor(math.log10(abs(mid))), mid)
    )
    places = max(0, -math.floor(math.log10(step))) + 2
    k0 = math.floor((lo - origin) / step + 1e-9)
    k1 = math.ceil((hi - origin) / step - 1e-9)
    return [round(origin + k * step, places) for k in range(k0, k1 + 1)]


def levels(values: Array, spec: int | Sequence[float] | None, *, filled: bool) -> list[float]:
    """Contour levels. An int is a hint for how many; levels land on round
    numbers. Lines get the levels inside the data range; filled bands get the
    whole bracketing lattice as edges."""
    if spec is not None and not isinstance(spec, int):
        return sorted({float(v) for v in spec})
    lo, hi = _core.finite_range(values) or (0.0, 1.0)
    if hi <= lo:
        return [lo, lo + 1.0] if filled else []
    lattice = _lattice(lo, hi, max(spec or 7, 1))
    return lattice if filled else [v for v in lattice if lo < v < hi]


# -- streamlines -----------------------------------------------------------------


def streamlines(
    xc: Sequence[float],
    yc: Sequence[float],
    u: list[list[float]],
    v: list[list[float]],
    density: float = 1.0,
    max_length: float = 4.0,
) -> Iterator[tuple[list[float], list[float]]]:
    """Trace streamlines of ``(u, v)`` over the grid ``(xc, yc)``, yielding
    ``(xs, ys)`` in data coordinates.

    RK4 in index space on the normalized field (so steps are arc length), seeded
    on a lattice; an occupancy mask stops lines entering cells already covered.
    """
    h, w = len(u), len(u[0]) if u else 0
    if h < 2 or w < 2:
        return
    dx = (xc[-1] - xc[0]) / (w - 1) or 1.0
    dy = (yc[-1] - yc[0]) / (h - 1) or 1.0

    def sample(g: list[list[float]], r: float, c: float) -> float:
        r0, c0 = min(int(r), h - 2), min(int(c), w - 2)
        tr, tc = r - r0, c - c0
        top = g[r0][c0] + (g[r0][c0 + 1] - g[r0][c0]) * tc
        bot = g[r0 + 1][c0] + (g[r0 + 1][c0 + 1] - g[r0 + 1][c0]) * tc
        return top + (bot - top) * tr

    def inside(r: float, c: float) -> bool:
        return 0.0 <= r <= h - 1 and 0.0 <= c <= w - 1

    def direction(r: float, c: float) -> tuple[float, float] | None:
        if not inside(r, c):
            return None
        uu, vv = sample(u, r, c) / dx, sample(v, r, c) / dy
        mag = math.hypot(uu, vv)
        return None if mag < 1e-12 or mag != mag else (vv / mag, uu / mag)

    ds = 0.25
    nm = max(2, round(25 * density))
    mask = [[False] * nm for _ in range(nm)]

    def cell(r: float, c: float) -> tuple[int, int]:
        return min(nm - 1, int(r / (h - 1) * nm)), min(nm - 1, int(c / (w - 1) * nm))

    def step(r: float, c: float, sign: float) -> tuple[float, float] | None:
        k1 = direction(r, c)
        k2 = k1 and direction(r + sign * ds / 2 * k1[0], c + sign * ds / 2 * k1[1])
        k3 = k2 and direction(r + sign * ds / 2 * k2[0], c + sign * ds / 2 * k2[1])
        k4 = k3 and direction(r + sign * ds * k3[0], c + sign * ds * k3[1])
        if not (k1 and k2 and k3 and k4):
            return None
        return (
            r + sign * ds / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]),
            c + sign * ds / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]),
        )

    max_steps = max(1, int(max_length * max(h, w) / ds))

    def trace(r: float, c: float, sign: float) -> list[tuple[float, float]]:
        pts, home = [(r, c)], cell(r, c)
        for _ in range(max_steps):
            nxt = step(r, c, sign)
            if nxt is None or not inside(*nxt):
                break
            r, c = nxt
            here = cell(r, c)
            if here != home:
                if mask[here[0]][here[1]]:
                    break
                mask[here[0]][here[1]] = True
                home = here
            pts.append((r, c))
        return pts

    for i in range(nm):
        for j in range(nm):
            if mask[i][j]:
                continue
            r0, c0 = (i + 0.5) / nm * (h - 1), (j + 0.5) / nm * (w - 1)
            if direction(r0, c0) is None:
                continue
            mask[i][j] = True
            path = trace(r0, c0, -1.0)[::-1] + trace(r0, c0, 1.0)[1:]
            if len(path) >= 2:
                yield [interp(xc, c) for _, c in path], [interp(yc, r) for r, _ in path]
