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


def _require_same_length(mark: str, **arrays) -> None:
    """Raise unless every named array is the same length.

    Parallel-array marks used to truncate to the shortest input and carry on,
    which is worse than it sounds: the *axis limits* are still folded from the
    full arrays, so ``line([1,2,3,4,5], [10,20])`` drew a two-point line on an
    x axis running to 5 and reported ``get_xlim() == (0.8, 5.2)``. That is a
    figure which looks deliberate and is wrong, which is the one failure mode a
    publication-quality library must not have. matplotlib raises here too.
    """
    lengths = {name: len(values) for name, values in arrays.items()}
    if len(set(lengths.values())) <= 1:
        return
    detail = ", ".join(f"{name}={n}" for name, n in lengths.items())
    raise ValueError(
        f"{mark} needs {' and '.join(lengths)} of equal length; got {detail}"
    )


#: ``struct`` format codes for buffers that hold numbers, and so can go down
#: the ``array("d", view)`` fast path. A buffer whose format is anything else -
#: NumPy's ``1w`` for a ``<U*`` string array, ``O`` for an object array - is
#: still a valid buffer, so a caller testing only ``ndim``/``c_contiguous``
#: will happily hand it over and get an unreadable memoryview error back.
_NUMERIC_BUFFER_FORMATS = frozenset(
    "?bBhHiIlLqQnNefdg"
)


def _as_float64_buffer(values):
    """Normalize an ndarray-like to something the buffer fast path can use.

    Duck-typed on ``.dtype``/``.astype`` rather than importing NumPy, which
    pyplotrs does not depend on. Three things are handled here because all
    three otherwise fall off the fast path and into a Python loop, or fail
    outright:

    * a **masked array** carries its fill values under the mask, and the plain
      buffer is those fill values - ``[1.0, 2.0, 999.0]`` for a masked third
      element. ``filled(nan)`` routes them into the NaN-gap path lines and
      markers already implement, which is what a reader expects to see.
    * a **non-float64 dtype** (``float32``, ``int32``, ``bool``, ...) converts
      in one C-level pass here rather than element by element downstream.
    * a **non-contiguous** array (a strided slice, a transpose) is made
      contiguous so the memcpy path applies instead of a per-element read.

    Anything without a dtype - a list, a tuple, an ``array("d")``, a generator -
    is returned untouched.
    """
    astype = getattr(values, "astype", None)
    if astype is None or getattr(values, "dtype", None) is None:
        return values
    filled = getattr(values, "filled", None)
    if filled is not None and getattr(values, "mask", None) is not None:
        try:
            values = filled(float("nan"))
            astype = values.astype
        except (TypeError, ValueError):
            return values
    try:
        if values.dtype.kind not in "biuf":
            return values  # str/object/datetime64: let the caller's fallback see it
        out = astype("float64", copy=False)
        if not getattr(out, "flags", None) or not out.flags["C_CONTIGUOUS"]:
            out = out.copy(order="C")
        return out
    except (AttributeError, TypeError, ValueError):
        return values


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
    values = _as_float64_buffer(values)
    if type(values) is array and values.typecode == "d":
        return values
    try:
        view = memoryview(values)
    # A NumPy array of strings, objects or datetime64 raises here rather than
    # returning a buffer, and each dtype raises its own type: `<U8` gives
    # NotImplementedError, `datetime64` gives ValueError, `object` gives
    # NotImplementedError. Catching only TypeError let those escape as an
    # unreadable "memoryview: unsupported format 1w" instead of falling through
    # to the element-wise branch, which is what turns them into the categorical
    # and date axes the docs promise.
    except (TypeError, ValueError, NotImplementedError):
        pass
    else:
        if view.ndim == 1 and view.c_contiguous:
            if view.format == "d":
                out = array("d")
                out.frombytes(view.cast("B"))  # memcpy
                return out
            # Some other contiguous numeric type (float32, int64, ...): one
            # C-level pass, still far cheaper than a Python comprehension.
            # NotImplementedError joins the list because that is what a NumPy
            # string or object buffer raises, and falling through to the
            # element-wise branch gives a readable error (or a working
            # conversion) instead of "memoryview: unsupported format 1w".
            try:
                return array("d", view)
            except (TypeError, ValueError, NotImplementedError):
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

    A contiguous 2D buffer (a NumPy array) is taken whole - no per-pixel
    Python. Otherwise each row is converted individually, which is still one
    pass rather than the nested comprehension plus separate flatten this
    replaces.

    The flatten goes through ``cast("B")``, not ``cast(fmt, (h*w,))``:
    ``memoryview.cast`` requires a byte format on one side of every hop, so
    reshaping float32 straight to 1-D float32 raises "cannot cast between two
    non-byte formats". Going via bytes is legal for every format and is the
    same memcpy.
    """
    data = _as_float64_buffer(data)
    try:
        view = memoryview(data)
    except (TypeError, ValueError, NotImplementedError):
        view = None
    if view is not None and view.ndim == 2 and view.c_contiguous:
        h, w = view.shape
        if view.format == "d":
            out = array("d")
            out.frombytes(view.cast("B"))  # memcpy
        else:
            out = array("d", view.cast("B").cast(view.format))
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


# Nice-number step multipliers for contour levels, the set matplotlib's
# ``MaxNLocator`` uses by default. Wider than the tick locator's {1, 2, 2.5, 5}
# because a contour asks for roughly ten bands where an axis asks for five or so
# labels, and at that density the coarse set overshoots badly - a 1.57-wide
# field wants a step of 0.15, and rounding that up to 0.2 costs four lines.
_LEVEL_STEPS = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)

# Levels a bare ``contour`` / ``contourf`` asks for, matplotlib's hard-wired
# default. One constant for both: a `contour` overlaid on a `contourf` is only
# readable if the lines land on the band boundaries beneath them, and they only
# do that if both sides asked the locator the same question.
_DEFAULT_LEVELS = 7


def _level_step(lo: float, hi: float, n: int) -> tuple[float, float]:
    """``(step, origin)``: the round step spanning ``lo..hi`` in about ``n + 1``
    bands, and the value its multiples are counted from.

    The hint counts *lines*; a step spanning the range in ``n + 1`` bands puts
    ``n`` lines inside it, so that is the budget the step has to meet. Same rule
    matplotlib's ``MaxNLocator(n + 1)`` applies to the same numbers.

    ``origin`` is zero unless the field sits far from it compared to how wide it
    is - 15.0895 to 15.0970, say - where counting from zero would spend every
    round-looking digit on the part the levels have in common. matplotlib shifts
    the count to the nearest power of ten below the midpoint there, and the
    levels come out round in the digits that actually vary.
    """
    raw = (hi - lo) / (n + 1)
    mag = 10.0 ** math.floor(math.log10(raw))
    step = next((m * mag for m in _LEVEL_STEPS if m * mag >= raw * (1 - 1e-12)),
                10.0 * mag)
    mid = 0.5 * (lo + hi)
    if abs(mid) / (hi - lo) < 100.0:
        return step, 0.0
    return step, math.copysign(10.0 ** math.floor(math.log10(abs(mid))), mid)


def _level_lattice(flat: list[float], levels, default_n: int) -> tuple[list[float], float, float]:
    """``(lattice, lo, hi)``: the round-numbered levels bracketing the data.

    The lattice runs from the last step at or below the data minimum to the first
    at or above the maximum, so it covers the range whole. Both contour flavors
    read their levels off it - lines from the inside of it, filled bands from all
    of it - which is what makes them coincide.
    """
    finite = [v for v in flat if math.isfinite(v)]
    lo, hi = (min(finite), max(finite)) if finite else (0.0, 1.0)
    if hi <= lo:
        return [], lo, hi
    step, origin = _level_step(lo, hi, max(default_n if levels is None else levels, 1))
    decimals = _decimals_for_step(step)
    # Lattice indices bracketing the range, with a hair of slack so a range that
    # ends *on* a lattice point keeps that point rather than gaining an empty
    # band beyond it from a floor/ceil that missed by an ulp.
    k0 = math.floor((lo - origin) / step + 1e-9)
    k1 = math.ceil((hi - origin) / step - 1e-9)
    # `k * step` accumulates float noise around values that are meant to be
    # round; the step's own precision is the most a level can need.
    return [round(origin + k * step, decimals) for k in range(k0, k1 + 1)], lo, hi


def _auto_levels(flat: list[float], levels,
                 default_n: int = _DEFAULT_LEVELS) -> list[float]:
    """Resolve a ``levels`` argument into a sorted list of contour thresholds.

    An int (or ``None``) is a *hint*: it asks for about that many levels, and the
    thresholds land on round numbers - multiples of a nice step - rather than on
    even fractions of the data range. Contour levels are read as values (a reader
    asks "which line is z = 0.3?"), so 0.15, 0.30, 0.45 beats 0.1426, 0.2853,
    0.4279, and the count comes out near the hint rather than exactly on it.
    Only levels strictly inside the data range are kept; one on the extremes
    would draw nothing, or a single degenerate point.
    """
    if levels is not None and not isinstance(levels, int):
        return sorted(float(v) for v in levels)
    if isinstance(levels, int) and levels < 1:
        return []
    lattice, lo, hi = _level_lattice(flat, levels, default_n)
    return [v for v in lattice if lo < v < hi]


def _level_edges(flat: list[float], levels,
                 default_n: int = _DEFAULT_LEVELS) -> list[float]:
    """Band *edges* for a filled contour: the whole lattice ``_auto_levels``
    draws its lines on, out to the round numbers that bracket the data.

    So the outermost bands reach past the data - a field over -0.78..0.78 in
    steps of 0.15 fills -0.9..0.9, and the colorbar says so - which is what
    matplotlib's ``contourf`` does, and what leaves every band boundary on a
    round number a contour line can also sit on.
    """
    if levels is not None and not isinstance(levels, int):
        return sorted(set(float(v) for v in levels))
    lattice, lo, hi = _level_lattice(flat, levels, default_n)
    # A flat field has no lattice to speak of; give it one band around its value
    # so the fill is drawn at all.
    return lattice if len(lattice) > 1 else [lo, lo + 1.0]


def _decimals_for_step(step: float) -> int:
    """Decimal places needed to write ``step`` (and its multiples) exactly."""
    s = abs(step)
    if s == 0.0 or not math.isfinite(s):
        return 0
    # Start where the leading digit reaches the ones place: a step of 4e-7 needs
    # seven decimals before there is anything to test for integrality, and asking
    # earlier only finds that 4e-7 rounds to 0 within any absolute tolerance.
    first = max(0, -math.floor(math.log10(s)))
    for d in range(first, first + 11):
        scaled = s * 10.0 ** d
        # `scaled >= 1` from here, so the tolerance is relative to the step, not
        # to the absolute size of the number being written.
        if abs(scaled - round(scaled)) < 1e-6 * scaled:
            return d
    return first + 10


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


def _spine_ends(join: str, width: float, lo_meets: bool, hi_meets: bool):
    """How far a spine should run past each of its two ends, in points.

    Two strokes that meet at a right angle are drawn as separate paths, so each
    stops on the other's *centerline* and the outer quarter of the junction is
    left uncovered: a spine ending at another spine notches its corner, and a
    tick sitting on the axis limit juts half a stroke width past the flat end of
    the spine it belongs to. Both read as "these two lines missed each other".
    Extending the spine by half its width covers exactly what a miter join
    between the two would have, without merging them into one path - they are
    different lines with different meanings, and a tick has to stay free to
    point inward or vanish with ``axis("off")``.

    ``join`` selects when to do it: ``"miter"`` only at an end something abuts
    (``lo_meets`` / ``hi_meets``, decided by the caller, which is the only one
    that knows where the ticks landed), ``"square"`` unconditionally - a
    projecting cap, so a free end overhangs - and ``"butt"`` never.
    """
    if join == "butt" or width <= 0.0:
        return 0.0, 0.0
    half = width / 2.0
    if join == "square":
        return half, half
    return (half if lo_meets else 0.0), (half if hi_meets else 0.0)


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


def _rectangular(Z: list[list[float]], what: str = "Z") -> list[list[float]]:
    """Return ``Z`` unchanged, or raise if its rows are not all the same length.

    The callers take ``w`` from ``Z[0]`` and ``h`` from ``len(Z)`` and hand the
    pair to a Rust kernel alongside the flattened values. On a ragged grid that
    pair describes more elements than were actually flattened, and the kernel
    indexes off the end of the buffer - which surfaces as a ``PanicException``
    naming a line inside the extension. Checking here means the message names
    the argument instead.
    """
    if not Z:
        return Z
    w = len(Z[0])
    for i, row in enumerate(Z):
        if len(row) != w:
            raise ValueError(
                f"{what} rows must all be the same length; row 0 has {w}, "
                f"row {i} has {len(row)}"
            )
    return Z


def _field_args(args) -> tuple[list[float], list[float], list[list[float]]]:
    """Parse ``(Z)`` or ``(X, Y, Z)`` field-plot positional args into 1D x/y
    coordinate vectors and the 2D ``Z`` grid."""
    if len(args) == 1:
        Z = _rectangular([[float(v) for v in row] for row in args[0]])
        h = len(Z); w = len(Z[0]) if Z else 0
        return [float(i) for i in range(w)], [float(i) for i in range(h)], Z
    X, Y, Z = args[0], args[1], args[2]
    Z = _rectangular([[float(v) for v in row] for row in Z])
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
    boxes legible without introducing a second theme color.
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
