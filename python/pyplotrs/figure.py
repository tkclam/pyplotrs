"""pyplotrs Figure/Axes API.

Layout is solved in a single pass by the Rust ``pyplotrs-layout`` engine using
*pre-measured* real text extents: every band (title, axis labels, tick labels)
is reserved space sized from shaped text, so labels can never overlap the plot
and there is no draw-measure-adjust loop. Axis ticks come from the Rust "nice
numbers" locator. Data is drawn clipped to the plot area, and the y-axis label
is rotated via an affine group.

**This module orchestrates; Rust computes.** Coordinate data is held as
``array.array("d")`` (see :func:`_to_f64`) so it crosses into Rust through the
buffer protocol as a memcpy rather than a per-element interpreter round-trip,
and the scans over it - autoscaling, histogram binning, the data-to-device
transform, polyline simplification - all run on the Rust side. Anything that
loops over individual data points in this file is a bug or a to-do, not a
design.
"""

from __future__ import annotations

import html
import math
from array import array
from typing import Sequence

from . import _pyplotrs_core as _core
from . import colormaps as _colormaps
from . import mathtext as _mathtext
from . import norms as _norms
from . import scales as _scales
from . import ticker as _ticker
from . import theme as _theme
from . import threed as _threed
from .theme import Theme


def _font(weight: str = "normal", style: str = "normal") -> str:
    """The Rust face selector for a weight/slant pair.

    ``"normal"``/``"bold"`` and ``"normal"``/``"italic"`` compose into
    ``"body"``, ``"body-bold"``, ``"body-italic"``, ``"body-bolditalic"``.
    Unknown values fall back to normal rather than raising: a typo should not
    lose a whole figure at save time.
    """
    bold = str(weight).lower() in ("bold", "semibold", "heavy", "black")
    italic = str(style).lower() in ("italic", "oblique")
    if not bold and not italic:
        return "body"
    return "body-" + ("bold" if bold else "") + ("italic" if italic else "")


def _tw(scene, text, size, font: str = "body") -> float:
    """Math-aware text width (drop-in for ``scene.measure_text``)."""
    return _mathtext.measure(scene, text, size, font)[0]


def _th(scene, text, size, font: str = "body") -> tuple[float, float]:
    """Math-aware ``(ascent, depth)`` for a string at ``size``."""
    _w, a, d = _mathtext.measure(scene, text, size, font)
    return a, d


def _text(scene, x, baseline, text, size, color, font: str = "body") -> None:
    """Math-aware text draw (drop-in for ``scene.add_text``)."""
    _mathtext.draw(scene, x, baseline, text, size, color, font)

# Module-level alias so methods taking a ``range=`` keyword can still reach the
# builtin without shadowing pain.
_irange = range

# Okabe-Ito colorblind-safe categorical palette (C0-C7).
_COLOR_CYCLE: list[tuple[int, int, int, int]] = [
    (0, 114, 178, 255),  # C0 blue
    (230, 159, 0, 255),  # C1 orange
    (0, 158, 115, 255),  # C2 green
    (204, 121, 167, 255),  # C3 pink
    (86, 180, 233, 255),  # C4 sky blue
    (213, 94, 0, 255),  # C5 vermillion
    (240, 228, 66, 255),  # C6 yellow
    (0, 0, 0, 255),  # C7 black
]

_BLACK = (0, 0, 0, 255)
_WHITE = (255, 255, 255, 255)
_SPINE = (89, 89, 89, 255)  # mid-gray spines/ticks (softer than pure black)
_LEGEND_BG = (255, 255, 255, 255)  # opaque: data must never bleed through the box
_LEGEND_BORDER = (179, 179, 179, 255)
# Gaps (points) framing a figure-level legend within its reserved right column:
# space between the axes grid and the box, and between the box and figure edge.
_LEGEND_COL_GAP_L = 10.0
_LEGEND_COL_GAP_R = 2.0

# Type scale (points), calibrated for journal figure sizes.
_TICK_LABEL_SIZE = 9.0
_AXIS_LABEL_SIZE = 10.0
_TITLE_SIZE = 11.0
_SUPTITLE_SIZE = 13.0
_LEGEND_SIZE = 9.0

# Spacing (points).
_TICK_LENGTH = 3.5
_TICK_LABEL_GAP = 2.5
_AXIS_LABEL_GAP = 3.0
_TITLE_GAP = 4.0
_OUTER_MARGIN = 6.0
_INLINE_DPI = 150.0  # raster resolution for Jupyter `_repr_png_` inline display
_WSPACE = 26.0
_HSPACE = 24.0

# Colorbar geometry (points).
_CBAR_GAP = 8.0  # between the plot's right edge and the color strip
_CBAR_WIDTH = 11.0  # width of the color strip
_CBAR_TICK_LEN = 3.0
_CBAR_TICK_GAP = 2.5

# 3D chrome.
_PANE_FILL = (242, 242, 242, 255)  # back-wall panes
_PANE_EDGE = (170, 170, 170, 255)  # pane borders (the 3 axis frames)
_GRID_3D = (214, 214, 214, 255)  # 3D gridlines
_CUBE_FILL = 0.86  # fraction of the plot rect the projected cube fills

_DATA_PAD = 0.05  # fraction of range added as margin around data

# Figure size units. pyplotrs sizes figures in *points* by default, so a plot can
# be reasoned about directly against its font scale (e.g. a 480x360 pt figure
# with a 10 pt font). These factors convert a length in the named unit to points
# (1 pt = 1/72 in).
_UNIT_TO_PT = {"pt": 1.0, "in": 72.0, "cm": 72.0 / 2.54, "mm": 72.0 / 25.4}


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


def _svg_to_html(svg: str, title: str, alt: str) -> str:
    """Wrap a standalone SVG document in a self-contained HTML5 page.

    The SVG is *inlined* (not referenced via ``<img>``), so the result is a
    single portable file that keeps real, selectable ``<text>`` and its embedded
    fonts; raster images inside the scene are already base64 data URIs, so the
    page fetches nothing when viewed. The figure is centred and shrinks to fit
    narrow viewports while never upscaling past its natural point size."""
    body = svg
    if body.startswith("<?xml"):  # the XML prolog is meaningless once inlined
        body = body[body.index("?>") + 2:].lstrip("\n")
    if body.startswith("<svg "):  # label the root for assistive tech
        body = f'<svg role="img" aria-label="{html.escape(alt, quote=True)}" ' + body[len("<svg "):]
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        "<style>\n"
        "html,body{margin:0;height:100%}\n"
        "body{display:flex;align-items:center;justify-content:center;background:#f5f5f5}\n"
        "svg{max-width:100%;height:auto;background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.15)}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}"
        "</body>\n"
        "</html>\n"
    )


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


def _xform_coeffs(sx, sy) -> tuple[float, float, float, float]:
    """Recover the linear data->device transform ``(ax, bx, ay, by)`` from the
    affine scale closures, so the per-point mapping can run in Rust:
    ``dx = ax*x + bx``, ``dy = ay*y + by``."""
    bx = sx(0.0)
    by = sy(0.0)
    return sx(1.0) - bx, bx, sy(1.0) - by, by


class _Proj:
    """Data->device projection for one axes.

    Bundles the data->device closures ``sx``/``sy`` (the scale transform composed
    with the affine device map, used by the per-element slow paths), ``coeffs`` —
    the affine map ``(ax, bx, ay, by)`` over *transformed* space — and the scale
    ``xcode``/``ycode`` strings. The Rust fast paths (``add_line_xform``/
    ``add_markers_xform``) take raw data plus ``coeffs`` and the codes, and apply
    the (possibly nonlinear) transform per point **in Rust** before the affine,
    so no per-point Python runs on the hot path under any scale.
    """

    __slots__ = ("sx", "sy", "coeffs", "xcode", "ycode")

    def __init__(self, sx, sy, coeffs, xcode: str, ycode: str) -> None:
        self.sx = sx
        self.sy = sy
        self.coeffs = coeffs  # (ax, bx, ay, by) over TRANSFORMED space
        self.xcode = xcode
        self.ycode = ycode


def _colorbar_ticks(cb: dict, max_ticks: int = 6) -> list[tuple[float, str]]:
    """Locate colorbar ticks, honoring the mappable's ``norm`` (linear -> nice
    numbers, ``LogNorm`` -> decades, etc.)."""
    norm = cb.get("norm")
    if norm is not None:
        return norm.colorbar_ticks(max_ticks)
    return _core.nice_ticks(cb["vmin"], cb["vmax"], max_ticks)


#: Cache of colormap -> 1024-byte RGBA LUT. `Colormap` has no `__eq__`, so this
#: keys on object identity while holding the colormap alive - unlike an `id()`
#: key, which a later allocation at the same address could impersonate.
#: Bounded so a program minting many ad-hoc colormaps cannot grow it without end.
_LUT_CACHE: dict = {}
_LUT_CACHE_MAX = 64


def _colormap_lut(cmap) -> bytes:
    """A 256-entry RGBA lookup table sampled from ``cmap`` (1024 bytes).

    Sampling costs 256 Python calls, and it used to run on *every* draw of every
    image and again for each colorbar gradient. The table is the only form the
    Rust side needs, so it is built once and reused.
    """
    hit = _LUT_CACHE.get(cmap)
    if hit is not None:
        return hit
    out = bytearray(256 * 4)
    for i in range(256):
        r, g, b, a = cmap(i / 255.0)
        o = i * 4
        out[o] = r
        out[o + 1] = g
        out[o + 2] = b
        out[o + 3] = a
    lut = bytes(out)
    if len(_LUT_CACHE) >= _LUT_CACHE_MAX:
        _LUT_CACHE.clear()
    _LUT_CACHE[cmap] = lut
    return lut


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


def _rgba_values(values, cmap, norm) -> list[tuple[int, int, int, int]]:
    """One RGBA per value, through ``norm`` then ``cmap``.

    Runs in Rust whenever the norm names a transform Rust knows
    (:attr:`pyplotrs.norms.Normalize.code`), which covers linear and log - two
    Python calls per point otherwise, so 200k interpreter round-trips for a
    100k-point scatter. ``TwoSlopeNorm`` and ``BoundaryNorm`` are piecewise and
    have no such transform, so they keep the per-value Python path.
    """
    code = getattr(norm, "code", None)
    if code is not None:
        return _core.map_colors(values, _colormap_lut(cmap), norm.vmin, norm.vmax, code)
    return [cmap(norm(v)) for v in values]


# -- line styles ------------------------------------------------------------

_DASH_PATTERNS: dict = {
    "solid": None,
    "-": None,
    "dashed": [4.0, 3.0],
    "--": [4.0, 3.0],
    "dotted": [1.0, 2.5],
    ":": [1.0, 2.5],
    "dashdot": [5.0, 2.0, 1.0, 2.0],
    "-.": [5.0, 2.0, 1.0, 2.0],
    "none": None,
    None: None,
}


def _dash_for(style) -> list[float] | None:
    return _DASH_PATTERNS.get(style, None)


def _draws_line(style) -> bool:
    return style not in ("none", None)


# -- marker shapes ----------------------------------------------------------

def _circle_pts(cx: float, cy: float, r: float, n: int = 24) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(2.0 * math.pi * i / n), cy + r * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    ]


_HATCH_SPACING = 6.0  # device-point gap between hatch lines


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


def _draw_hatch(scene, dev: list[tuple[float, float]], pattern: str, color,
                lw: float = 0.6) -> None:
    """Fill the device-space bounding box of ``dev`` with a line hatch. Exact for
    axis-aligned rectangles; a bbox approximation for other shapes."""
    xs = [x for x, _ in dev]
    ys = [y for _, y in dev]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 <= x0 or y1 <= y0:
        return
    sp = _HATCH_SPACING
    diag = sp * math.sqrt(2.0)
    scene.begin_group(1.0, 0.0, 0.0, 1.0, 0.0, 0.0, clip=(x0, y0, x1 - x0, y1 - y0))

    def line(a, b):
        scene.add_path([a, b], stroke_color=color, stroke_width=lw)

    if "|" in pattern or "+" in pattern:
        x = x0
        while x <= x1:
            line((x, y0), (x, y1)); x += sp
    if "-" in pattern or "+" in pattern:
        y = y0
        while y <= y1:
            line((x0, y), (x1, y)); y += sp
    if "/" in pattern or "x" in pattern:  # constant x+y
        c = x0 + y0
        while c <= x1 + y1:
            line((c - y0, y0), (c - y1, y1)); c += diag
    if "\\" in pattern or "x" in pattern:  # constant x-y
        c = x0 - y1
        while c <= x1 - y0:
            line((c + y0, y0), (c + y1, y1)); c += diag
    scene.end_group()


_ELLIPSE_N = 72  # polygon segments approximating an ellipse/circle patch


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


class _Rect:
    """A plain rectangle mirroring the Rust ``Rect`` (for Python-synthesized
    layouts: insets, twins, secondary axes)."""
    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h

    @property
    def x1(self) -> float:
        return self.x + self.w

    @property
    def y1(self) -> float:
        return self.y + self.h


class _AxLayout:
    """Duck-typed twin of the Rust ``AxesLayout`` so ``Axes._draw`` can render
    into a Python-computed cell (insets/twins)."""
    __slots__ = ("cell", "plot", "title", "xlabel", "ylabel", "x_tick", "y_tick", "cbar")

    def __init__(self, **kw) -> None:
        for k, v in kw.items():
            setattr(self, k, v)


def _layout_cell(cell: _Rect, bands: tuple) -> _AxLayout:
    """Python port of the Rust ``layout_cell``: reserve the axis bands within
    ``cell`` and return the plot area + band rects."""
    title_h, xlabel_h, ylabel_w, x_tick_h, y_tick_w, cbar_w = bands
    ylabel = _Rect(cell.x, cell.y, ylabel_w, cell.h)
    y_tick_x = cell.x + ylabel_w
    cbar = _Rect(cell.x1 - cbar_w, cell.y, cbar_w, cell.h)
    title = _Rect(cell.x, cell.y, cell.w, title_h)
    plot_x = y_tick_x + y_tick_w
    plot_y = cell.y + title_h
    plot_w = max(cell.x1 - cbar_w - plot_x, 0.0)
    plot_h = max(cell.y1 - xlabel_h - x_tick_h - plot_y, 0.0)
    plot = _Rect(plot_x, plot_y, plot_w, plot_h)
    y_tick = _Rect(y_tick_x, plot_y, y_tick_w, plot_h)
    x_tick = _Rect(plot_x, plot.y1, plot_w, x_tick_h)
    xlabel = _Rect(plot_x, plot.y1 + x_tick_h, plot_w, xlabel_h)
    return _AxLayout(cell=cell, plot=plot, title=title, xlabel=xlabel, ylabel=ylabel,
                     x_tick=x_tick, y_tick=y_tick, cbar=cbar)


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


def _draw_marker(scene, cx: float, cy: float, d: float, shape: str,
                 facecolor, edgecolor=None, edgewidth: float = 1.0) -> None:
    """Draw a single marker of diameter ``d`` centered at ``(cx, cy)``.

    Filled shapes: ``o`` circle, ``s`` square, ``^`` triangle-up,
    ``v`` triangle-down, ``D`` diamond. Stroke-only shapes: ``+`` plus,
    ``x`` cross.
    """
    r = d / 2.0
    if shape in ("+", "x"):
        col = edgecolor or facecolor or _BLACK
        if shape == "+":
            segs = [[(cx - r, cy), (cx + r, cy)], [(cx, cy - r), (cx, cy + r)]]
        else:
            segs = [[(cx - r, cy - r), (cx + r, cy + r)], [(cx - r, cy + r), (cx + r, cy - r)]]
        for seg in segs:
            scene.add_path(seg, stroke_color=col, stroke_width=max(edgewidth, 1.0), cap="round")
        return

    if shape == "s":
        pts = [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
    elif shape == "^":
        s = r * 0.95
        pts = [(cx, cy - r), (cx + s, cy + r * 0.8), (cx - s, cy + r * 0.8)]
    elif shape == "v":
        s = r * 0.95
        pts = [(cx, cy + r), (cx - s, cy - r * 0.8), (cx + s, cy - r * 0.8)]
    elif shape == "D":
        pts = [(cx, cy - r), (cx + r * 0.8, cy), (cx, cy + r), (cx - r * 0.8, cy)]
    else:  # "o" and any unknown shape fall back to a circle
        pts = _circle_pts(cx, cy, r)

    scene.add_path(
        pts,
        fill_color=facecolor,
        close=True,
        stroke_color=edgecolor,
        stroke_width=edgewidth if edgecolor else 1.0,
    )


def _place_text(scene, dx: float, dy: float, s: str, size: float, color,
                ha: str = "left", va: str = "baseline", font: str = "body") -> None:
    """Draw ``s`` (math-aware) anchored at device ``(dx, dy)`` with the given
    horizontal/vertical alignment. Coordinates are y-down device points.
    ``font`` must match between measuring and drawing or the anchor drifts."""
    tw = _tw(scene, s, size, font)
    a, d = _th(scene, s, size, font)
    if ha == "center":
        dx -= tw / 2.0
    elif ha == "right":
        dx -= tw
    if va == "bottom":
        baseline = dy - d
    elif va == "top":
        baseline = dy + a
    elif va == "center":
        baseline = dy + (a - d) / 2.0
    else:  # baseline
        baseline = dy
    _text(scene, dx, baseline, s, size, color, font)


def _draw_arrow(scene, x0: float, y0: float, x1: float, y1: float, color,
                width: float, head_len: float = 8.0, head_w: float = 3.2) -> None:
    """Stroke a line from ``(x0, y0)`` to ``(x1, y1)`` with a filled triangular
    arrowhead at the second point."""
    ang = math.atan2(y1 - y0, x1 - x0)
    # Shorten the shaft so it meets the back of the head, not the tip.
    bx = x1 - head_len * math.cos(ang)
    by = y1 - head_len * math.sin(ang)
    scene.add_path([(x0, y0), (bx, by)], stroke_color=color, stroke_width=width, cap="round")
    px, py = -math.sin(ang), math.cos(ang)  # unit perpendicular
    scene.add_path(
        [(x1, y1), (bx + head_w * px, by + head_w * py), (bx - head_w * px, by - head_w * py)],
        fill_color=color, close=True,
    )


class _Mappable:
    """Handle returned by :meth:`Axes.imshow`/:meth:`Axes.scatter` (``c=``),
    consumed by :meth:`Figure.colorbar` to build a matching color scale."""

    def __init__(self, ax: "Axes", cmap, vmin: float, vmax: float, norm=None) -> None:
        self.ax = ax
        self.cmap = cmap
        self.vmin = vmin
        self.vmax = vmax
        self.norm = norm  # None => linear; else a pyplotrs.norms.Normalize


class _AxesBase:
    """State and behaviour every axes class shares.

    ``Axes``, ``Axes3D`` and ``PolarAxes`` are separate coordinate systems, but
    they are all "a theme, a colour cycle and a stack of labelled marks". That
    much used to be written out three times - ``_next_color`` byte-identically,
    ``legend`` differing only in its default position, and the legend-entry
    normalization twice over - which is how the ``barh`` legend crash and the
    hardcoded swatch size survived: a fix applied to one copy silently missed
    the others.
    """

    #: Where this axes class puts a legend when the caller doesn't say. 2D can
    #: search for a clear corner; 3D and polar fill their cell too densely for
    #: that to mean much, so they pin a corner.
    _LEGEND_DEFAULT_LOC = "best"

    #: Attribute holding the mark stack legend entries are drawn from.
    _MARKS_ATTR = "_marks"

    def _init_common(self, theme) -> None:
        self._theme: Theme = _theme.get(theme)
        self._cidx = 0  # next palette index for auto-colored marks
        self._legend: dict | None = None
        self._title: str | None = None

    @staticmethod
    def _marker_diameter(markersize, size, default: float = 6.0) -> float:
        """Marker size in **points of diameter**, the one unit pyplotrs uses.

        matplotlib spells this two ways - ``scatter(s=...)`` is an *area* in
        pt^2 while ``plot(markersize=...)`` is a *diameter* in pt - and pyplotrs
        inherited both. ``markersize`` is now the single spelling everywhere;
        ``size`` is still accepted on scatter, still means area, and is
        converted here, so ported matplotlib code keeps drawing the right size
        instead of silently getting 36 pt blobs.
        """
        if markersize is not None:
            return float(markersize)
        if size is not None:
            return math.sqrt(float(size))
        return default

    def _mark_color(self, color, alpha: float = 1.0):
        """The resolved colour for a mark, with ``alpha`` folded in.

        Folding opacity into the colour here is what lets every mark take an
        ``alpha`` without each draw branch having to know about it - the IR
        carries RGBA throughout, so there is nothing else to plumb.
        """
        c = self._next_color(color)
        return c if alpha >= 1.0 else _with_alpha(c, float(alpha))

    def _next_color(self, color):
        """Resolve ``color``, or take the next palette entry when it is ``None``.

        Advancing the cycle is a side effect, so this must be called exactly once
        per mark - at construction, not at draw time.
        """
        if color is None:
            palette = self._theme.palette
            c = palette[self._cidx % len(palette)]
            self._cidx += 1
            return c
        return self._theme.resolve(color)

    def legend(self, *, loc: str | None = None):
        """Enable an auto-legend over this axes' labelled marks.

        ``loc`` is ``best`` / ``upper right`` / ``upper left`` / ``lower right``
        / ``lower left`` / ``upper center`` / ``lower center``; ``None`` uses
        this axes class's default. ``best`` picks the corner that overlaps the
        data least.
        """
        self._legend = {"loc": self._LEGEND_DEFAULT_LOC if loc is None else loc}
        return self

    def _legend_entries(self) -> list[dict]:
        """The labelled marks to draw legend keys for.

        3D and polar marks carry projection-specific fields, so they are
        normalized here into the line/scatter shapes the shared glyph drawer
        understands; marks with no single colour (a surface) are dropped.
        :class:`Axes` overrides this to pass its marks through untouched, since
        its glyph drawer has real branches for bar/hist/fill swatches that this
        normalization would flatten into plain rules.
        """
        out: list[dict] = []
        for m in getattr(self, self._MARKS_ATTR):
            if not m.get("label"):
                continue
            if m["kind"] == "scatter":
                out.append({"kind": "scatter", "label": m["label"], "color": m["color"],
                            "markersize": m["markersize"], "marker": m.get("marker", "o"),
                            "edgecolor": m.get("edgecolor"),
                            "edgewidth": m.get("edgewidth", 1.0)})
            else:
                out.append({"kind": "line", "label": m["label"], "color": m["color"],
                            "width": m.get("width", 1.5),
                            "linestyle": m.get("linestyle", "solid"),
                            "marker": m.get("marker"),
                            "markersize": m.get("markersize", 5.0)})
        return out


class Axes(_AxesBase):
    """A single set of axes: a coordinate system plus a stack of marks."""

    def __init__(self, theme: Theme | None = None) -> None:
        self._init_common(theme)
        self._marks: list[dict] = []
        self._annotations: list[dict] = []
        self._colorbar: dict | None = None
        self._xlabel: str | None = None
        self._ylabel: str | None = None
        # View limits, populated during layout; None => auto from data.
        self._xlim: tuple[float, float] | None = None
        self._ylim: tuple[float, float] | None = None
        # Axis scales (linear by default; LogScale etc. set via ``set(xscale=)``).
        self._xscale: _scales.Scale = _scales.LinearScale()
        self._yscale: _scales.Scale = _scales.LinearScale()
        # Reference primitives (axhline/axvline/axspan/axline) and free-form
        # patches (rectangle/circle/...) live outside the data-mark stack: refs
        # never drive autoscaling, patches contribute a bbox. All default empty
        # so figures that use none stay byte-identical to before Phase D.
        self._refs: list[dict] = []
        self._patches: list[dict] = []
        # Axis/tick/grid overrides (all None/False => theme + scale defaults).
        self._grid_override: bool | None = None
        self._aspect: str | None = None
        self._frame_off: bool = False
        self._xticks_manual: list[float] | None = None
        self._yticks_manual: list[float] | None = None
        self._xticklabels_manual: list[str] | None = None
        self._yticklabels_manual: list[str] | None = None
        self._xformatter = None
        self._yformatter = None
        # Overlays sharing this axes' cell (Phase F): a twin y/x axis, inset
        # child axes (fractional sub-rects), and functional secondary axes.
        self._twinx: "Axes | None" = None
        self._twiny: "Axes | None" = None
        self._insets: list[tuple["Axes", tuple]] = []
        self._secondary: list[dict] = []
        self._is_twin: bool = False  # a twin skips its own facecolor/grid

    # -- styling helpers ----------------------------------------------------

    def _coords(self, values, axis: str) -> "array":
        """Coerce plot coordinates to a contiguous ``array("d")``.

        Datetime-like values switch that axis to a
        :class:`~pyplotrs.scales.DateScale` (mapped via ``date2num``); strings
        switch it to a :class:`~pyplotrs.scales.CategoricalScale`, mapping each
        distinct label to an integer position in first-seen order.

        The numeric case is the hot one and is handled first, without ever
        materializing an intermediate Python list: anything already offering an
        ``f64`` buffer (a NumPy array, another ``array("d")``) is taken as-is.
        Only inputs that are *not* plain numbers pay for the datetime/string
        inspection below.
        """
        # Buffer-backed numeric input can't be dates or strings - take the fast
        # path before touching the sequence at all.
        try:
            view = memoryview(values)
        except TypeError:
            view = None
        if view is not None and view.ndim == 1 and view.c_contiguous:
            return _to_f64(values)

        if not isinstance(values, (list, tuple)):
            values = list(values)
        if values and _scales.is_datetime_like(values[0]):
            scale = self._axis_scale(axis, _scales.DateScale)
            return array("d", [_scales.date2num(v) for v in values])
        if any(isinstance(v, str) for v in values):
            scale = self._axis_scale(axis, _scales.CategoricalScale)
            out = array("d")
            for v in values:
                s = str(v)
                if s not in scale.index:
                    scale.index[s] = len(scale.categories)
                    scale.categories.append(s)
                out.append(float(scale.index[s]))
            return out
        return _to_f64(values)

    def _axis_scale(self, axis: str, kind):
        """The scale on ``axis``, replacing it with a fresh ``kind`` if it isn't
        one already. Used when the *data* dictates the scale (dates, categories)."""
        scale = self._xscale if axis == "x" else self._yscale
        if not isinstance(scale, kind):
            scale = _scales.CategoricalScale([]) if kind is _scales.CategoricalScale else kind()
            if axis == "x":
                self._xscale = scale
            else:
                self._yscale = scale
        return scale

    # -- public API: marks --------------------------------------------------

    def line(self, xs, ys, *, label: str | None = None, color=None,
             linewidth: float | None = None, alpha: float = 1.0,
             linestyle: str = "solid", marker: str | None = None,
             markersize: float = 5.0, simplify: bool = True) -> "Axes":
        """Plot a polyline through ``(xs, ys)``.

        ``color`` may be ``None`` (cycle the palette), ``"C0".."C7"``, or an
        ``(r, g, b[, a])`` tuple. ``linestyle`` is one of ``solid``/``dashed``/
        ``dotted``/``dashdot`` (or ``none`` for markers only). An optional
        ``marker`` draws a glyph at each vertex.

        ``simplify`` (default ``True``) collapses runs of near-collinear
        vertices in device space - visually identical output, far smaller and
        faster vector export on dense data. Set ``False`` to keep every vertex
        exactly (e.g. when the polyline *is* the data being exported).
        """
        self._marks.append({
            "kind": "line",
            "xs": self._coords(xs, "x"),
            "ys": self._coords(ys, "y"),
            "label": label,
            "color": self._mark_color(color, alpha),
            "width": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle,
            "marker": marker,
            "markersize": float(markersize),
            "simplify": bool(simplify),
        })
        return self

    def scatter(self, xs, ys, *, label: str | None = None, color=None,
                markersize: float | None = None, alpha: float = 1.0,
                marker: str = "o", edgecolor=None, edgewidth: float = 1.0,
                size: float | None = None,
                c=None, cmap="viridis", norm=None, vmin: float | None = None,
                vmax: float | None = None):
        """Scatter markers at ``(xs, ys)``.

        ``markersize`` is the marker **diameter in points**, the same unit every
        other mark uses. ``size`` is accepted for matplotlib compatibility and
        means *area* in pt² (so ``size=36`` and ``markersize=6`` agree).

        Pass ``c`` (a per-point array) to color markers by value through ``cmap``
        and ``norm`` (``vmin``/``vmax`` set the range; ``norm="log"`` or a
        :mod:`pyplotrs.norms` instance for non-linear). Returns a colorbar handle
        in that case, else ``self``."""
        xs = self._coords(xs, "x")
        ys = self._coords(ys, "y")
        mark = {
            "kind": "scatter",
            "xs": xs,
            "ys": ys,
            "label": label,
            "color": self._mark_color(color, alpha) if c is None else _BLACK,
            "markersize": self._marker_diameter(markersize, size),
            "marker": marker,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
            "edgewidth": float(edgewidth),
            "colors": None,
        }
        self._marks.append(mark)
        if c is None:
            return self
        # Colormapped scatter: precompute one RGBA per point and hand back a
        # mappable so ``fig.colorbar(sc)`` matches the color scale.
        cvals = _to_f64(c)
        nrm = _norms.get(norm, vmin, vmax).autoscale(cvals)
        cm = _colormaps.get_cmap(cmap)
        mark["colors"] = _rgba_values(cvals, cm, nrm)
        return _Mappable(self, cm, nrm.vmin, nrm.vmax, norm=nrm)

    def bar(self, x, height, *, width: float = 0.8, bottom=0.0, color=None,
            alpha: float = 1.0, label: str | None = None, edgecolor=None) -> "Axes":
        """Draw vertical bars of the given ``height`` at positions ``x``. ``x``
        may be strings (categories), which set a categorical x-axis."""
        xs = self._coords(x, "x")
        heights = [float(v) for v in height]
        self._marks.append({
            "kind": "bar",
            "xs": xs,
            "heights": heights,
            "bottoms": _as_seq(bottom, len(xs)),
            "width": float(width),
            "color": self._mark_color(color, alpha),
            "label": label,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
        })
        return self

    def hist(self, data, *, bins: int = 10, color=None, alpha: float = 1.0,
             label: str | None = None, range=None, density: bool = False) -> "Axes":
        """Bin ``data`` into ``bins`` equal-width bins and draw the histogram.

        The binning loop runs in Rust (``_core.histogram``), matching what
        ``hist2d`` already did."""
        vals = _to_f64(data)
        if not len(vals):
            vals = array("d", (0.0, 1.0))
        span = (float(range[0]), float(range[1])) if range else None
        edges, counts = _core.histogram(vals, max(int(bins), 1), span, bool(density))
        self._marks.append({
            "kind": "hist",
            "edges": edges,
            "counts": counts,
            "color": self._mark_color(color, alpha),
            "label": label,
        })
        return self

    def fill_between(self, xs, y1, y2=0.0, *, color=None, alpha: float = 0.3,
                     label: str | None = None) -> "Axes":
        """Fill the band between ``y1`` and ``y2`` across ``xs``."""
        xs = self._coords(xs, "x")
        self._marks.append({
            "kind": "fill",
            "orient": "y",
            "xs": xs,
            "y1": _to_f64(y1),
            "y2": _to_f64(_as_seq(y2, len(xs))),
            "color": self._next_color(color),
            "alpha": float(alpha),
            "label": label,
        })
        return self

    def fill_betweenx(self, ys, x1, x2=0.0, *, color=None, alpha: float = 0.3,
                      label: str | None = None) -> "Axes":
        """Fill the band between ``x1`` and ``x2`` across ``ys`` - the transpose
        of :meth:`fill_between`, for bands around a horizontal profile."""
        ys = self._coords(ys, "y")
        self._marks.append({
            "kind": "fill",
            "orient": "x",
            "ys": ys,
            "y1": _to_f64(x1),
            "y2": _to_f64(_as_seq(x2, len(ys))),
            "color": self._next_color(color),
            "alpha": float(alpha),
            "label": label,
        })
        return self

    def hlines(self, y, xmin, xmax, *, color=None, linewidth: float | None = None,
               alpha: float = 1.0, linestyle: str = "solid",
               label: str | None = None) -> "Axes":
        """Horizontal line segments at each ``y``, spanning ``xmin`` to ``xmax``
        in **data** coordinates.

        Unlike :meth:`axhline`, which spans a fraction of the axes and is a
        guide, these are data and participate in autoscaling. Each argument may
        be a scalar or a sequence; scalars broadcast."""
        return self._add_lines("h", y, xmin, xmax, color, linewidth, linestyle, label, alpha)

    def vlines(self, x, ymin, ymax, *, color=None, linewidth: float | None = None,
               alpha: float = 1.0, linestyle: str = "solid",
               label: str | None = None) -> "Axes":
        """Vertical line segments at each ``x``, spanning ``ymin`` to ``ymax`` in
        **data** coordinates (see :meth:`hlines`)."""
        return self._add_lines("v", x, ymin, ymax, color, linewidth, linestyle, label, alpha)

    def _add_lines(self, orient, pos, lo, hi, color, linewidth, linestyle, label,
                   alpha=1.0) -> "Axes":
        """Shared body of :meth:`hlines` / :meth:`vlines`."""
        pos = _to_f64(pos if hasattr(pos, "__len__") else [pos])
        n = len(pos)
        lo = _to_f64(_as_seq(lo, n))
        hi = _to_f64(_as_seq(hi, n))
        self._marks.append({
            "kind": "lines", "orient": orient, "pos": pos, "lo": lo, "hi": hi,
            "color": self._mark_color(color, alpha),
            "width": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle, "label": label,
        })
        return self

    def errorbar(self, xs, ys, *, yerr=None, xerr=None, color=None, label: str | None = None,
                 marker: str | None = "o", markersize: float = 5.0,
                 linewidth: float = 1.5, alpha: float = 1.0,
                 capsize: float = 3.0, linestyle: str = "solid") -> "Axes":
        """Plot ``(xs, ys)`` with symmetric ``yerr``/``xerr`` error bars."""
        xs = [float(x) for x in xs]
        ys = [float(y) for y in ys]
        n = len(xs)
        self._marks.append({
            "kind": "errorbar",
            "xs": xs,
            "ys": ys,
            "yerr": _as_seq(yerr, n) if yerr is not None else None,
            "xerr": _as_seq(xerr, n) if xerr is not None else None,
            "color": self._mark_color(color, alpha),
            "label": label,
            "marker": marker,
            "markersize": float(markersize),
            "width": float(linewidth),
            "capsize": float(capsize),
            "linestyle": linestyle,
        })
        return self

    def _map_colors(self, values, cmap, norm, vmin, vmax):
        """``(colormap, norm, rgba_per_value)`` for the per-element coloured
        types (hexbin, pcolormesh). The mapping itself runs in Rust - see
        :func:`_rgba_values`."""
        vals = _to_f64(values)
        cm = _colormaps.get_cmap(cmap)
        nrm = _norms.get(norm, vmin, vmax).autoscale(vals)
        return cm, nrm, _rgba_values(vals, cm, nrm)

    # -- discrete family ----------------------------------------------------

    def barh(self, y, width, *, height: float = 0.8, left=0.0, color=None,
             alpha: float = 1.0, label: str | None = None, edgecolor=None) -> "Axes":
        """Horizontal bars of the given ``width`` at vertical positions ``y``.
        ``y`` may be strings (categories), which set a categorical y-axis."""
        ys = self._coords(y, "y")
        self._marks.append({
            "kind": "barh", "ys": ys, "widths": [float(v) for v in width],
            "lefts": _as_seq(left, len(ys)), "height": float(height),
            "color": self._mark_color(color, alpha), "label": label,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
        })
        return self

    # -- statistical --------------------------------------------------------

    def boxplot(self, data, *, positions=None, widths: float = 0.5, color=None,
                showfliers: bool = True) -> "Axes":
        """Box-and-whisker plot. ``data`` is a list of numeric arrays (one box
        each); ``positions`` default to ``1..n``."""
        groups = data if _is_2d(data) else [data]
        stats = [_boxstats([float(v) for v in g]) for g in groups]
        positions = ([float(p) for p in positions] if positions is not None
                     else [float(i + 1) for i in range(len(groups))])
        self._marks.append({
            "kind": "boxplot", "stats": stats, "positions": positions,
            "width": float(widths), "color": self._next_color(color),
            "showfliers": showfliers,
        })
        return self

    def violinplot(self, data, *, positions=None, widths: float = 0.5, color=None,
                   points: int = 128) -> "Axes":
        """Violin plot: a mirrored Gaussian-KDE density for each array in
        ``data`` (KDE computed in Rust, no SciPy dependency)."""
        groups = data if _is_2d(data) else [data]
        positions = ([float(p) for p in positions] if positions is not None
                     else [float(i + 1) for i in range(len(groups))])
        violins = []
        for g in groups:
            vals = [float(v) for v in g if math.isfinite(v)]
            if not vals:
                violins.append(([], []))
                continue
            lo, hi = min(vals), max(vals)
            pad = (hi - lo) * 0.15 or 1.0
            grid = [lo - pad + (hi - lo + 2 * pad) * i / (points - 1) for i in range(points)]
            dens = _core.gaussian_kde(vals, grid, 0.0)
            violins.append((grid, dens))
        self._marks.append({
            "kind": "violin", "violins": violins, "positions": positions,
            "width": float(widths), "color": self._next_color(color),
        })
        return self

    def pie(self, sizes, *, labels=None, colors=None, startangle: float = 90.0,
            radius: float = 1.0) -> "Axes":
        """Pie chart of ``sizes`` (auto-normalized). Turns the frame off and fixes
        an equal aspect so wedges stay circular."""
        vals = [float(v) for v in sizes]
        total = sum(vals) or 1.0
        wedges = []
        ang = math.radians(startangle)
        for i, v in enumerate(vals):
            sweep = 2.0 * math.pi * v / total
            col = colors[i] if colors else None
            wedges.append({"a0": ang, "a1": ang + sweep,
                           "color": self._next_color(col),
                           "label": labels[i] if labels else None})
            ang += sweep
        self._marks.append({"kind": "pie", "wedges": wedges, "radius": float(radius)})
        self._frame_off = True
        self._aspect = "equal"
        # Reserve room around the pie for the slice labels drawn just outside the
        # rim (wider when any slice is labelled, so long labels aren't clipped).
        margin = 1.55 if any(w["label"] for w in wedges) else 1.15
        self._xlim = (-margin * radius, margin * radius)
        self._ylim = (-margin * radius, margin * radius)
        return self

    def _level_colors(self, n: int, colors, cmap):
        """One RGBA per contour level from ``colors`` (a single color or a list)
        or ``cmap`` (default: a single palette color)."""
        if colors is not None:
            if isinstance(colors, str) or (
                hasattr(colors, "__len__") and len(colors) in (3, 4)
                and all(isinstance(c, (int, float)) for c in colors)
            ):
                return [self._theme.resolve(colors)] * n
            return [self._theme.resolve(colors[i % len(colors)]) for i in _irange(n)]
        if cmap is None:
            return [self._theme.palette[0]] * n
        cm = _colormaps.get_cmap(cmap)
        return [cm((i + 0.5) / n) for i in _irange(n)]

    def imshow(self, data, *, cmap="viridis", vmin: float | None = None,
               vmax: float | None = None, norm=None, extent=None,
               origin: str = "upper") -> "_Mappable":
        """Display 2D ``data`` as a colormapped image.

        ``data`` is a sequence of equal-length rows. ``cmap`` is a colormap
        name (see :mod:`pyplotrs.colormaps`) or a ``Colormap``. ``norm`` maps
        values onto the color axis (``None`` linear, ``"log"`` for a
        :class:`~pyplotrs.norms.LogNorm`, or any :class:`~pyplotrs.norms.Normalize`);
        the per-pixel lookup runs in Rust. ``extent`` is ``(x0, x1, y0, y1)`` in
        data coordinates (default ``(0, ncols, 0, nrows)``); ``origin`` is
        ``"upper"`` (row 0 at top) or ``"lower"``. Returns a handle for
        :meth:`Figure.colorbar`.
        """
        # Flattened once here, row-major, and handed to Rust as a buffer; the
        # draw path used to re-flatten a nested list per pixel on every save.
        flat, h, w = _to_f64_grid(data)
        cm = _colormaps.get_cmap(cmap)
        # Resolve the norm to fill vmin/vmax from the data (log norms use only
        # positive samples) and to pick the Rust per-pixel transform code.
        nrm = _norms.get(norm, vmin, vmax)
        nrm.autoscale(flat)
        lo, hi = nrm.vmin, nrm.vmax
        # A norm with no Rust transform (TwoSlope, Boundary) can't drive the
        # per-pixel path; fall back to linear there rather than mis-mapping.
        norm_code = getattr(nrm, "code", None) or "linear"
        if extent is None:
            extent = (0.0, float(w), 0.0, float(h))
        else:
            extent = (float(extent[0]), float(extent[1]), float(extent[2]), float(extent[3]))
        self._marks.append({
            "kind": "image",
            "flat": flat,
            "w": w,
            "h": h,
            "cmap": cm,
            "vmin": lo,
            "vmax": hi,
            "norm_code": norm_code,
            "extent": extent,
            "origin": origin,
        })
        return _Mappable(self, cm, lo, hi, norm=(nrm if norm_code != "linear" else None))

    # -- step / stair family ------------------------------------------------

    def step(self, xs, ys, *, where: str = "pre", color=None,
             linewidth: float | None = None, alpha: float = 1.0,
             linestyle: str = "solid", label: str | None = None) -> "Axes":
        """Step plot through ``(xs, ys)``; ``where`` is ``pre``/``post``/``mid``."""
        px, py = _step_points(list(_to_f64(xs)), list(_to_f64(ys)), where)
        self._marks.append({
            "kind": "line", "xs": _to_f64(px), "ys": _to_f64(py), "label": label,
            "color": self._mark_color(color, alpha),
            "width": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle, "marker": None, "markersize": 5.0, "simplify": False,
        })
        return self

    def stairs(self, values, edges=None, *, color=None, linewidth: float | None = None,
               alpha: float = 1.0, fill: bool = False, baseline: float = 0.0,
               label: str | None = None) -> "Axes":
        """Step outline of ``values`` over bin ``edges`` (``len(values)+1`` edges;
        defaults to ``0..n``). ``fill=True`` fills down to ``baseline``."""
        values = _to_f64(values)
        edges = (_to_f64(edges) if edges is not None
                 else _to_f64(range(len(values) + 1)))
        xs = array("d")
        top = array("d")
        for i, v in enumerate(values):
            xs.extend((edges[i], edges[i + 1]))
            top.extend((v, v))
        if fill:
            self._marks.append({
                "kind": "fill", "xs": xs, "y1": top,
                "y2": _to_f64(_as_seq(baseline, len(xs))),
                "color": self._next_color(color), "alpha": 0.3, "label": label,
            })
        else:
            px = array("d", [edges[0]]) + xs + array("d", [edges[-1]])
            py = array("d", [baseline]) + top + array("d", [baseline])
            self._marks.append({
                "kind": "line", "xs": px, "ys": py, "label": label,
                "color": self._mark_color(color, alpha),
                "width": self._theme.line_width if linewidth is None else float(linewidth),
                "linestyle": "solid", "marker": None, "markersize": 5.0, "simplify": False,
            })
        return self

    def stem(self, xs, ys, *, bottom: float = 0.0, color=None, alpha: float = 1.0,
             marker: str = "o", markersize: float = 5.0,
             label: str | None = None) -> "Axes":
        """Stem plot: a vertical line from ``bottom`` to each ``(x, y)`` topped by
        a marker, with a baseline."""
        self._marks.append({
            "kind": "stem", "xs": self._coords(xs, "x"), "ys": self._coords(ys, "y"),
            "bottom": float(bottom), "color": self._mark_color(color, alpha),
            "marker": marker, "markersize": float(markersize), "label": label,
        })
        return self

    def broken_barh(self, xranges, yrange, *, color=None, edgecolor=None,
                    alpha: float = 1.0, label: str | None = None) -> "Axes":
        """Horizontal bars from ``(xstart, width)`` pairs, all spanning the
        vertical ``yrange = (ymin, height)`` (e.g. Gantt / interval plots)."""
        self._marks.append({
            "kind": "broken_barh",
            "bars": [(float(x0), float(w)) for x0, w in xranges],
            "y0": float(yrange[0]), "h": float(yrange[1]),
            "color": self._next_color(color), "alpha": float(alpha),
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
            "label": label,
        })
        return self

    def eventplot(self, positions, *, orientation: str = "horizontal",
                  lineoffsets: float = 1.0, linelengths: float = 0.8,
                  color=None, linewidth: float = 1.0) -> "Axes":
        """Raster of event marks. ``positions`` is a 1D array or a list of rows;
        each row is offset by ``lineoffsets`` and drawn ``linelengths`` long
        (perpendicular to ``orientation``)."""
        rows = positions if len(positions) and _is_2d(positions) else [positions]
        rows = [_to_f64(r) for r in rows]
        self._marks.append({
            "kind": "eventplot", "rows": rows, "orientation": orientation,
            "offset": float(lineoffsets), "length": float(linelengths),
            "color": self._next_color(color), "width": float(linewidth),
        })
        return self

    # -- 2D binning ---------------------------------------------------------

    def hist2d(self, xs, ys, *, bins=10, range=None, cmap="viridis", norm=None,
               vmin: float | None = None, vmax: float | None = None) -> "_Mappable":
        """2D histogram of ``(xs, ys)`` rendered as a colormapped image. ``bins``
        is an int or ``(nx, ny)``; the count grid is built in Rust."""
        xs = _to_f64(xs)
        ys = _to_f64(ys)
        nx, ny = (bins, bins) if isinstance(bins, int) else (int(bins[0]), int(bins[1]))
        if range is not None:
            (xlo, xhi), (ylo, yhi) = range
        else:
            xlo, xhi = _core.data_range(xs) or (0.0, 1.0)
            ylo, yhi = _core.data_range(ys) or (0.0, 1.0)
        counts = _core.hist2d(xs, ys, nx, ny, xlo, xhi, ylo, yhi)
        rows = [counts[iy * nx:(iy + 1) * nx] for iy in _irange(ny)]
        return self.imshow(rows, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax,
                           extent=(xlo, xhi, ylo, yhi), origin="lower")

    def hexbin(self, xs, ys, *, gridsize: int = 30, cmap="viridis", norm=None,
               vmin: float | None = None, vmax: float | None = None) -> "_Mappable":
        """Hexagonal binning of ``(xs, ys)`` colored by count (binning in Rust)."""
        xs = _to_f64(xs)
        ys = _to_f64(ys)
        xlo, xhi = _core.data_range(xs) or (0.0, 1.0)
        ylo, yhi = _core.data_range(ys) or (0.0, 1.0)
        hexes = _core.hexbin(xs, ys, gridsize, xlo, xhi, ylo, yhi)
        counts = _to_f64([c for _, _, c in hexes])
        cm, nrm, colors = self._map_colors(counts, cmap, norm, vmin, vmax)
        sx = (xhi - xlo) / max(gridsize, 1)
        sy = sx  # data-space cell; hexagon offsets below tile the two grids
        # Pointy-top hexagon offsets (width ~ sx, height ~ 1.33 sy).
        offs = [(0.0, sy * 0.66), (sx / 2.0, sy * 0.33), (sx / 2.0, -sy * 0.33),
                (0.0, -sy * 0.66), (-sx / 2.0, -sy * 0.33), (-sx / 2.0, sy * 0.33)]
        self._marks.append({
            "kind": "hexbin", "centers": [(cx, cy) for cx, cy, _ in hexes],
            "colors": colors, "offsets": offs,
        })
        return _Mappable(self, cm, nrm.vmin, nrm.vmax,
                         norm=(nrm if type(nrm) is not _norms.Normalize else None))

    # -- field / grid -------------------------------------------------------

    def pcolormesh(self, *args, cmap="viridis", norm=None, vmin: float | None = None,
                   vmax: float | None = None) -> "_Mappable":
        """Pseudocolor plot of a 2D grid: ``pcolormesh(C)`` or
        ``pcolormesh(X, Y, C)``. Regular grids route to the fast Rust image path;
        irregular grids draw one colored quad per cell."""
        xc, yc, Z = _field_args(args)
        h = len(Z)
        w = len(Z[0]) if Z else 0
        if _is_uniform(xc) and _is_uniform(yc):
            # Cell-centered image: extent spans half a cell beyond edge centers.
            dx = (xc[-1] - xc[0]) / (w - 1) if w > 1 else 1.0
            dy = (yc[-1] - yc[0]) / (h - 1) if h > 1 else 1.0
            extent = (xc[0] - dx / 2, xc[-1] + dx / 2, yc[0] - dy / 2, yc[-1] + dy / 2)
            return self.imshow(Z, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax,
                               extent=extent, origin="lower")
        cm, nrm, colors = self._map_colors(
            [v for row in Z for v in row], cmap, norm, vmin, vmax)
        # Cell edges from coordinate midpoints (irregular quad mesh).
        xe = _edges_from_centers(xc)
        ye = _edges_from_centers(yc)
        quads = []
        for iy in _irange(h):
            for ix in _irange(w):
                quads.append((xe[ix], xe[ix + 1], ye[iy], ye[iy + 1],
                              colors[iy * w + ix]))
        self._marks.append({"kind": "quadmesh", "quads": quads,
                            "extent": (xe[0], xe[-1], ye[0], ye[-1])})
        return _Mappable(self, cm, nrm.vmin, nrm.vmax)

    def contour(self, *args, levels=None, colors=None, cmap=None,
                linewidth: float = 1.0) -> "Axes":
        """Contour *lines* of a 2D field: ``contour(Z)`` or ``contour(X, Y, Z)``.
        Marching squares runs in Rust; lines are colored per level from
        ``colors`` (a single color / list) or ``cmap`` (default palette C0)."""
        xc, yc, Z = _field_args(args)
        h = len(Z)
        w = len(Z[0]) if Z else 0
        flat = _to_f64([v for row in Z for v in row])
        lvls = _auto_levels(list(flat), levels)
        segs = _core.contour_lines(flat, w, h, lvls)
        lcolors = self._level_colors(len(lvls), colors, cmap)
        self._marks.append({
            "kind": "contour", "segs": segs, "xcoords": xc, "ycoords": yc,
            "colors": lcolors, "width": float(linewidth),
            "extent": (min(xc), max(xc), min(yc), max(yc)),
        })
        return self

    def contourf(self, *args, levels=None, cmap="viridis", norm=None,
                 vmin: float | None = None, vmax: float | None = None,
                 upsample: int = 6) -> "_Mappable":
        """Filled contour bands of a 2D field. The field is bilinearly upsampled
        and band-colored in Rust (a raster fill, like ``imshow``)."""
        xc, yc, Z = _field_args(args)
        h = len(Z)
        w = len(Z[0]) if Z else 0
        flat = _to_f64([v for row in Z for v in row])
        # Filled bands must span the full data range (unlike contour *lines*,
        # whose levels are interior), so the extrema aren't left transparent.
        if levels is not None and not isinstance(levels, int):
            edges = sorted(set(float(v) for v in levels))
        else:
            lo, hi = _core.data_range(flat) or (0.0, 1.0)
            if hi <= lo:
                hi = lo + 1.0
            n = levels if isinstance(levels, int) else 9
            edges = [lo + (hi - lo) * i / n for i in _irange(n + 1)]
        nbands = len(edges) - 1
        cm = _colormaps.get_cmap(cmap)
        nrm = _norms.get(norm, edges[0], edges[-1])
        nrm.vmin, nrm.vmax = edges[0], edges[-1]
        band_lut = bytes(b for k in _irange(nbands)
                         for b in cm(nrm(0.5 * (edges[k] + edges[k + 1]))))
        img, uw, uh = _core.contourf_image(flat, w, h, edges, band_lut, upsample)
        self._marks.append({
            "kind": "contourf", "img": bytes(img), "uw": uw, "uh": uh,
            "extent": (min(xc), max(xc), min(yc), max(yc)),
        })
        return _Mappable(self, cm, edges[0], edges[-1], norm=nrm)

    # -- public API: reference lines & patches ------------------------------

    def axhline(self, y: float = 0.0, *, xmin: float = 0.0, xmax: float = 1.0,
                color=None, linewidth: float | None = None,
                linestyle: str = "solid") -> "Axes":
        """Draw a horizontal reference line at data ``y`` spanning the axes
        fraction ``xmin..xmax`` (0 = left edge, 1 = right). Reference lines are
        guides: they are drawn over the data but never affect autoscaling."""
        self._refs.append({
            "kind": "axhline", "y": float(y), "min": float(xmin), "max": float(xmax),
            "color": self._theme.resolve(color) if color is not None else self._theme.text_color,
            "width": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle,
        })
        return self

    def axvline(self, x: float = 0.0, *, ymin: float = 0.0, ymax: float = 1.0,
                color=None, linewidth: float | None = None,
                linestyle: str = "solid") -> "Axes":
        """Draw a vertical reference line at data ``x`` spanning the axes
        fraction ``ymin..ymax``. See :meth:`axhline`."""
        self._refs.append({
            "kind": "axvline", "x": float(x), "min": float(ymin), "max": float(ymax),
            "color": self._theme.resolve(color) if color is not None else self._theme.text_color,
            "width": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle,
        })
        return self

    def axhspan(self, ymin: float, ymax: float, *, xmin: float = 0.0, xmax: float = 1.0,
                color=None, alpha: float = 0.3) -> "Axes":
        """Shade the horizontal band between data ``ymin`` and ``ymax`` (spanning
        the axes fraction ``xmin..xmax`` in x). Drawn behind the data."""
        self._refs.append({
            "kind": "axhspan", "lo": float(ymin), "hi": float(ymax),
            "min": float(xmin), "max": float(xmax),
            "color": self._next_color(color), "alpha": float(alpha),
        })
        return self

    def axvspan(self, xmin: float, xmax: float, *, ymin: float = 0.0, ymax: float = 1.0,
                color=None, alpha: float = 0.3) -> "Axes":
        """Shade the vertical band between data ``xmin`` and ``xmax`` (spanning
        the axes fraction ``ymin..ymax`` in y). Drawn behind the data."""
        self._refs.append({
            "kind": "axvspan", "lo": float(xmin), "hi": float(xmax),
            "min": float(ymin), "max": float(ymax),
            "color": self._next_color(color), "alpha": float(alpha),
        })
        return self

    def axline(self, xy1, *, xy2=None, slope: float | None = None, color=None,
               linewidth: float | None = None, linestyle: str = "solid") -> "Axes":
        """Draw an infinite line through ``xy1``, defined by a second point
        ``xy2`` or a ``slope``. Clipped to the plot rect; not autoscaled."""
        if (xy2 is None) == (slope is None):
            raise ValueError("axline requires exactly one of xy2= or slope=")
        self._refs.append({
            "kind": "axline", "p1": (float(xy1[0]), float(xy1[1])),
            "p2": None if xy2 is None else (float(xy2[0]), float(xy2[1])),
            "slope": None if slope is None else float(slope),
            "color": self._theme.resolve(color) if color is not None else self._theme.text_color,
            "width": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle,
        })
        return self

    def rectangle(self, xy, width: float, height: float, *, angle: float = 0.0,
                  facecolor=None, edgecolor=None, linewidth: float = 1.0,
                  linestyle: str = "solid", alpha: float = 1.0,
                  fill: bool = True, hatch: str | None = None) -> "Axes":
        """Add an axis-aligned (or ``angle``-rotated, degrees CCW) rectangle with
        lower-left corner ``xy`` and the given data-space ``width``/``height``."""
        self._patches.append(self._patch_style({
            "kind": "rectangle", "xy": (float(xy[0]), float(xy[1])),
            "w": float(width), "h": float(height), "angle": float(angle),
        }, facecolor, edgecolor, linewidth, linestyle, alpha, fill, hatch))
        return self

    def circle(self, xy, radius: float, *, facecolor=None, edgecolor=None,
               linewidth: float = 1.0, linestyle: str = "solid", alpha: float = 1.0,
               fill: bool = True, hatch: str | None = None) -> "Axes":
        """Add a circle of data-space ``radius`` centered at ``xy``. Note it maps
        to an ellipse when the x/y scales differ (use ``set(aspect='equal')``)."""
        self._patches.append(self._patch_style({
            "kind": "ellipse", "xy": (float(xy[0]), float(xy[1])),
            "rx": float(radius), "ry": float(radius), "angle": 0.0,
        }, facecolor, edgecolor, linewidth, linestyle, alpha, fill, hatch))
        return self

    def ellipse(self, xy, width: float, height: float, *, angle: float = 0.0,
                facecolor=None, edgecolor=None, linewidth: float = 1.0,
                linestyle: str = "solid", alpha: float = 1.0, fill: bool = True,
                hatch: str | None = None) -> "Axes":
        """Add an ellipse of full data-space ``width``/``height`` (diameters)
        centered at ``xy``, rotated ``angle`` degrees CCW."""
        self._patches.append(self._patch_style({
            "kind": "ellipse", "xy": (float(xy[0]), float(xy[1])),
            "rx": float(width) / 2.0, "ry": float(height) / 2.0, "angle": float(angle),
        }, facecolor, edgecolor, linewidth, linestyle, alpha, fill, hatch))
        return self

    def polygon(self, points, *, closed: bool = True, facecolor=None,
                edgecolor=None, linewidth: float = 1.0, linestyle: str = "solid",
                alpha: float = 1.0, fill: bool = True, hatch: str | None = None) -> "Axes":
        """Add a polygon through the data-space vertices ``points``."""
        self._patches.append(self._patch_style({
            "kind": "polygon", "pts": [(float(x), float(y)) for x, y in points],
            "closed": bool(closed),
        }, facecolor, edgecolor, linewidth, linestyle, alpha, fill, hatch))
        return self

    def arrow(self, x: float, y: float, dx: float, dy: float, *, color=None,
              linewidth: float = 1.5) -> "Axes":
        """Draw an arrow from data ``(x, y)`` to ``(x + dx, y + dy)``."""
        self._patches.append({
            "kind": "arrow", "x": float(x), "y": float(y),
            "dx": float(dx), "dy": float(dy),
            "edgecolor": self._next_color(color), "linewidth": float(linewidth),
        })
        return self

    def _patch_style(self, patch: dict, facecolor, edgecolor, linewidth,
                     linestyle, alpha, fill, hatch) -> dict:
        """Attach resolved fill/edge/hatch styling to a patch dict."""
        if facecolor is None and fill:
            face = self._next_color(None)
        elif facecolor is None or not fill:
            face = None
        else:
            face = self._theme.resolve(facecolor)
        patch["facecolor"] = _with_alpha(face, alpha) if face is not None else None
        patch["edgecolor"] = self._theme.resolve(edgecolor) if edgecolor is not None else None
        patch["linewidth"] = float(linewidth)
        patch["linestyle"] = linestyle
        patch["hatch"] = hatch
        return patch

    def axis(self, arg: str) -> "Axes":
        """Coarse axis control: ``"off"``/``"on"`` toggle the frame (spines,
        ticks, grid); ``"equal"`` requests an equal data-unit aspect."""
        if arg == "off":
            self._frame_off = True
        elif arg == "on":
            self._frame_off = False
        elif arg == "equal":
            self._aspect = "equal"
        elif arg == "auto":
            self._aspect = None
        else:
            raise ValueError(f"unknown axis({arg!r}); expected 'off'/'on'/'equal'/'auto'")
        return self

    # -- public API: twin / secondary / inset axes --------------------------

    def twinx(self) -> "Axes":
        """A second axes sharing this one's x-axis but with an independent y-axis
        drawn on the right (e.g. two series in different units). Plot on the
        returned axes; it overlays the same cell."""
        tw = Axes(self._theme)
        tw._is_twin = True
        tw._cidx = self._cidx  # continue the palette so colors don't collide
        self._twinx = tw
        return tw

    def twiny(self) -> "Axes":
        """A second axes sharing this one's y-axis with an independent x-axis
        drawn along the top."""
        tw = Axes(self._theme)
        tw._is_twin = True
        tw._cidx = self._cidx
        self._twiny = tw
        return tw

    def inset_axes(self, bounds) -> "Axes":
        """A child axes occupying ``bounds = (x0, y0, width, height)`` given as
        fractions of this axes' plot area (``(0, 0)`` = lower-left). Returns the
        inset axes to plot on."""
        x0, y0, w, h = (float(v) for v in bounds)
        child = Axes(self._theme)
        self._insets.append((child, (x0, y0, w, h)))
        return child

    def secondary_xaxis(self, location: str, *, functions=None,
                        label: str | None = None) -> "Axes":
        """A functional secondary x-axis at ``location`` (``"top"``/``"bottom"``).
        ``functions=(forward, inverse)`` maps primary→secondary data (e.g.
        Celsius↔Fahrenheit); omit for a plain duplicate axis. Returns ``self``."""
        self._secondary.append({"axis": "x", "loc": location, "functions": functions,
                                "label": label})
        return self

    def secondary_yaxis(self, location: str, *, functions=None,
                        label: str | None = None) -> "Axes":
        """A functional secondary y-axis at ``location`` (``"left"``/``"right"``)."""
        self._secondary.append({"axis": "y", "loc": location, "functions": functions,
                                "label": label})
        return self

    def _has_extras(self) -> bool:
        return bool(self._twinx or self._twiny or self._insets or self._secondary)

    # -- public API: chrome -------------------------------------------------

    # -- annotations --------------------------------------------------------

    def text(self, x, y, s, *, color=None, fontsize: float | None = None,
             weight: str = "normal", style: str = "normal",
             ha: str = "left", va: str = "baseline") -> "Axes":
        """Draw ``s`` at data coordinates ``(x, y)``.

        ``ha`` is ``left``/``center``/``right``; ``va`` is
        ``baseline``/``bottom``/``center``/``top``. ``s`` may contain ``$...$``
        math. ``color`` defaults to the theme text colour. ``weight`` is
        ``normal`` or ``bold`` and ``style`` is ``normal`` or ``italic``; both
        select a real face of the body family, so the glyphs are genuinely bold
        or italic rather than synthetically slanted."""
        self._annotations.append({
            "kind": "text", "x": float(x), "y": float(y), "s": str(s),
            "color": self._theme.text_color if color is None else self._theme.resolve(color),
            "size": None if fontsize is None else float(fontsize),
            "font": _font(weight, style), "ha": ha, "va": va,
        })
        return self

    def annotate(self, text, xy, *, xytext=None, color=None, fontsize: float | None = None,
                 weight: str = "normal", style: str = "normal",
                 arrow: bool = True, ha: str = "left", va: str = "bottom") -> "Axes":
        """Annotate the data point ``xy`` with ``text`` placed at ``xytext``
        (defaults to ``xy``), optionally drawing a callout arrow from the text to
        the point. All coordinates are in data space. ``weight``/``style`` select
        a bold and/or italic face (see :meth:`text`)."""
        xy = (float(xy[0]), float(xy[1]))
        self._annotations.append({
            "kind": "annotate", "s": str(text), "xy": xy,
            "xytext": xy if xytext is None else (float(xytext[0]), float(xytext[1])),
            "color": self._theme.text_color if color is None else self._theme.resolve(color),
            "size": None if fontsize is None else float(fontsize),
            "font": _font(weight, style),
            "arrow": bool(arrow), "ha": ha, "va": va,
        })
        return self

    def set(self, *, title=None, xlabel=None, ylabel=None, xlim=None, ylim=None,
            xscale=None, yscale=None, xticks=None, yticks=None,
            xticklabels=None, yticklabels=None, xformatter=None, yformatter=None,
            grid=None, aspect=None) -> "Axes":
        """Set any combination of title, axis labels, view limits, axis scales,
        and tick/grid/aspect controls.

        ``xscale``/``yscale`` accept ``"linear"`` (default), ``"log"``,
        ``"symlog"``, ``"logit"`` or a :class:`pyplotrs.scales.Scale`.
        ``xticks``/``yticks`` pin tick positions; ``xticklabels``/``yticklabels``
        give matching label strings. ``xformatter``/``yformatter`` accept a
        :class:`pyplotrs.ticker.Formatter`, a ``"{x:.2f}"`` template, or a
        callable. ``grid`` overrides the theme grid; ``aspect="equal"`` equalizes
        the data-unit scale on both axes."""
        if title is not None:
            self._title = title
        if xlabel is not None:
            self._xlabel = xlabel
        if ylabel is not None:
            self._ylabel = ylabel
        if xlim is not None:
            self._xlim = (float(xlim[0]), float(xlim[1]))
        if ylim is not None:
            self._ylim = (float(ylim[0]), float(ylim[1]))
        if xscale is not None:
            self._xscale = _scales.get(xscale)
        if yscale is not None:
            self._yscale = _scales.get(yscale)
        if xticks is not None:
            self._xticks_manual = [float(v) for v in xticks]
        if yticks is not None:
            self._yticks_manual = [float(v) for v in yticks]
        if xticklabels is not None:
            self._xticklabels_manual = [str(s) for s in xticklabels]
        if yticklabels is not None:
            self._yticklabels_manual = [str(s) for s in yticklabels]
        if xformatter is not None:
            self._xformatter = _ticker.get(xformatter)
        if yformatter is not None:
            self._yformatter = _ticker.get(yformatter)
        if grid is not None:
            self._grid_override = bool(grid)
        if aspect is not None:
            self._aspect = None if aspect == "auto" else str(aspect)
        return self

    def _resolve_ticks(self, scale, lo: float, hi: float, max_n: int,
                       manual, manual_labels, formatter) -> list[tuple[float, str]]:
        """Locate ``(value, label)`` tick pairs honoring manual positions,
        manual labels, and a formatter override. Falls back to the scale's own
        locator+labels when nothing is overridden (byte-identical to before)."""
        if manual is not None:
            values = manual
        elif manual_labels is not None or formatter is not None:
            values = [v for v, _ in scale.ticks(lo, hi, max_n)]
        else:
            return scale.ticks(lo, hi, max_n)  # unchanged default path
        if manual_labels is not None:
            labels = [manual_labels[i] if i < len(manual_labels) else ""
                      for i in range(len(values))]
        elif formatter is not None:
            labels = [formatter(v, i) for i, v in enumerate(values)]
        else:
            labels = [_scales._fmt_plain(v) if v == int(v) else f"{v:g}" for v in values]
        return list(zip(values, labels))

    # -- layout helpers -----------------------------------------------------

    def _ranges(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Autoscaled ``(xrange, yrange)`` for this axes.

        Bulk coordinate arrays are reduced to their finite min/max **in Rust**
        and folded into a running bound (see :class:`_RangeAcc`); only the
        handful of derived scalars each mark contributes - bar edges, image
        extents, whisker ends - are touched in Python. Previously this
        concatenated every point of every mark into one list and scanned that,
        which was the single most expensive step in saving a large figure.
        """
        xs = _RangeAcc()
        ys = _RangeAcc()
        has_bar = False
        has_image = False
        for m in self._marks:
            k = m["kind"]
            if k in ("line", "scatter"):
                xs.add_array(m["xs"])
                ys.add_array(m["ys"])
            elif k == "bar":
                has_bar = True
                hw = m["width"] / 2.0
                bx = _core.data_range(m["xs"])
                if bx is not None:
                    xs.add(bx[0] - hw, bx[1] + hw)
                ys.add_array(m["bottoms"])
                ys.add_offsets(m["bottoms"], m["heights"], two_sided=False)
            elif k == "hist":
                has_bar = True
                xs.add(m["edges"][0], m["edges"][-1])
                ys.add_array(m["counts"])
                ys.add(0.0)
            elif k == "fill":
                if m.get("orient", "y") == "x":
                    # fill_betweenx: the band runs along y, bounded in x.
                    ys.add_array(m["ys"])
                    xs.add_array(m["y1"])
                    xs.add_array(m["y2"])
                else:
                    xs.add_array(m["xs"])
                    ys.add_array(m["y1"])
                    ys.add_array(m["y2"])
            elif k == "lines":
                along, across = (ys, xs) if m["orient"] == "h" else (xs, ys)
                along.add_array(m["pos"])
                across.add_array(m["lo"])
                across.add_array(m["hi"])
            elif k == "errorbar":
                xs.add_array(m["xs"])
                ys.add_array(m["ys"])
                if m["yerr"] is not None and len(m["yerr"]):
                    ys.add_offsets(m["ys"], m["yerr"])
                if m["xerr"] is not None and len(m["xerr"]):
                    xs.add_offsets(m["xs"], m["xerr"])
            elif k == "image":
                has_image = True
                x0, x1, y0, y1 = m["extent"]
                xs.add(x0, x1)
                ys.add(y0, y1)
            elif k == "barh":
                has_bar = True
                hh = m["height"] / 2.0
                by = _core.data_range(m["ys"])
                if by is not None:
                    ys.add(by[0] - hh, by[1] + hh)
                xs.add_array(m["lefts"])
                xs.add_offsets(m["lefts"], m["widths"], two_sided=False)
            elif k == "stem":
                xs.add_array(m["xs"])
                ys.add_array(m["ys"])
                ys.add(m["bottom"])
            elif k == "broken_barh":
                for x0, wdt in m["bars"]:
                    xs.add(x0, x0 + wdt)
                ys.add(m["y0"], m["y0"] + m["h"])
            elif k == "eventplot":
                horiz = m["orientation"] == "horizontal"
                for i, row in enumerate(m["rows"]):
                    off = m["offset"] * i
                    half = m["length"] / 2.0
                    if horiz:
                        xs.add_array(_to_f64(row))
                        ys.add(off - half, off + half)
                    else:
                        ys.add_array(_to_f64(row))
                        xs.add(off - half, off + half)
            elif k == "boxplot":
                hw = m["width"] / 2.0
                for pos, st in zip(m["positions"], m["stats"]):
                    xs.add(pos - hw, pos + hw)
                    ys.add(st["lo"], st["hi"])
                    if st["fliers"]:
                        ys.add_array(_to_f64(st["fliers"]))
            elif k == "violin":
                hw = m["width"] / 2.0
                for pos, (grid, _dens) in zip(m["positions"], m["violins"]):
                    xs.add(pos - hw, pos + hw)
                    ys.add_array(_to_f64(grid))
            elif k == "hexbin":
                for cx, cy in m["centers"]:
                    xs.add(cx)
                    ys.add(cy)
            elif k in ("quadmesh", "contourf"):
                has_image = True
                x0, x1, y0, y1 = m["extent"]
                xs.add(x0, x1)
                ys.add(y0, y1)
            elif k == "contour":
                x0, x1, y0, y1 = m["extent"]
                xs.add(x0, x1)
                ys.add(y0, y1)
            elif k == "quiver":
                xs.add_array(m["xs"])
                ys.add_array(m["ys"])
                scale = m["scale"]
                for x, y, u, v in zip(m["xs"], m["ys"], m["us"], m["vs"]):
                    xs.add(x + u * scale)
                    ys.add(y + v * scale)
            elif k == "pie":
                r = m["radius"]
                xs.add(-r, r)
                ys.add(-r, r)

        # Patches contribute their bounding box (reference lines/spans do not).
        for p in self._patches:
            bx, by = _patch_bbox(p)
            xs.add(*bx)
            ys.add(*by)

        if xs.empty:
            xs.add(0.0, 1.0)
            ys.add(0.0, 1.0)

        # Images set tight limits exactly at their extent (no data margin).
        if self._xlim:
            xr = self._xlim
        elif has_image:
            xr = xs.bounds() or (0.0, 1.0)
        else:
            xr = xs.padded()

        if self._ylim:
            yr = self._ylim
        elif has_image:
            yr = ys.bounds() or (0.0, 1.0)
        elif has_bar:
            lo, hi = ys.bounds() or (0.0, 1.0)
            # Bars are read against a baseline, so a non-negative series keeps
            # zero in view rather than floating above it.
            yr = (0.0, hi + (hi or 1.0) * _DATA_PAD) if lo >= 0.0 else ys.padded()
        else:
            yr = ys.padded()

        # Non-linear scales own their autoscaling (positive-domain clipping and
        # transformed-space padding), unless the user pinned explicit limits.
        # This is the one path that still needs the values rather than the
        # bounds, so it pays for a concatenation - non-linear scales are the
        # uncommon case, and the arrays were retained by reference anyway.
        if not self._xscale.is_identity and not self._xlim:
            xr = self._xscale.data_limits(_concat(xs.arrays()))
        if not self._yscale.is_identity and not self._ylim:
            yr = self._yscale.data_limits(_concat(ys.arrays()))
        return xr, yr

    def _bands(self, scene: "_core.Scene", xr, yr) -> tuple[
        tuple[float, float, float, float, float, float],
        list[tuple[float, str]],
        list[tuple[float, str]],
    ]:
        """Measure the reserved band sizes for this axes and locate ticks.

        Returns ``(bands, xticks, yticks)`` where ``bands`` is the 6-tuple
        ``solve_layout`` expects and ticks are ``(value, label)`` lists.
        """
        # Theme type scale - locals shadow the module defaults so every size
        # reference below picks up this axes' theme (measurement must match draw).
        t = self._theme
        _TICK_LABEL_SIZE = t.tick_label_size
        _AXIS_LABEL_SIZE = t.axis_label_size
        _TITLE_SIZE = t.title_size

        t_asc, t_desc, _ = scene.font_vmetrics(_TICK_LABEL_SIZE)
        tick_label_h = t_asc + t_desc

        xticks = self._resolve_ticks(self._xscale, xr[0], xr[1], 7,
                                     self._xticks_manual, self._xticklabels_manual,
                                     self._xformatter)
        yticks = self._resolve_ticks(self._yscale, yr[0], yr[1], 6,
                                     self._yticks_manual, self._yticklabels_manual,
                                     self._yformatter)

        x_tick_h = _TICK_LENGTH + _TICK_LABEL_GAP + tick_label_h
        y_label_w = max((_tw(scene, lbl, _TICK_LABEL_SIZE) for _, lbl in yticks), default=0.0)
        y_tick_w = _TICK_LENGTH + _TICK_LABEL_GAP + y_label_w

        title_h = 0.0
        title_font = _font(t.title_weight)
        label_font = _font(t.axis_label_weight)
        if self._title:
            a, d = _th(scene, self._title, _TITLE_SIZE, title_font)
            title_h = a + d + _TITLE_GAP
        xlabel_h = 0.0
        if self._xlabel:
            a, d = _th(scene, self._xlabel, _AXIS_LABEL_SIZE, label_font)
            xlabel_h = a + d + _AXIS_LABEL_GAP
        ylabel_w = 0.0
        if self._ylabel:
            a, d = _th(scene, self._ylabel, _AXIS_LABEL_SIZE, label_font)
            ylabel_w = a + d + _AXIS_LABEL_GAP

        cbar_w = 0.0
        if self._colorbar:
            cb = self._colorbar
            cbticks = _colorbar_ticks(cb)
            max_lbl = max(
                (_tw(scene, lbl, _TICK_LABEL_SIZE) for _, lbl in cbticks),
                default=0.0,
            )
            cbar_w = _CBAR_GAP + _CBAR_WIDTH + _CBAR_TICK_LEN + _CBAR_TICK_GAP + max_lbl
            if cb["label"]:
                a, d, _ = scene.font_vmetrics(_AXIS_LABEL_SIZE)
                cbar_w += a + d + _AXIS_LABEL_GAP

        # A twinx reserves right-side space for its y ticks/labels (shares the
        # cbar band slot); a twiny reserves top space in the title band.
        if self._twinx is not None and not self._colorbar:
            txr, tyr = self._twinx._ranges()
            tyt = self._twinx._yscale.ticks(tyr[0], tyr[1], 6)
            tlw = max((_tw(scene, lbl, _TICK_LABEL_SIZE) for _, lbl in tyt), default=0.0)
            cbar_w = _TICK_LENGTH + _TICK_LABEL_GAP + tlw
            if self._twinx._ylabel:
                a, d, _ = scene.font_vmetrics(_AXIS_LABEL_SIZE)
                cbar_w += a + d + _AXIS_LABEL_GAP
        if self._twiny is not None:
            t_asc2, t_desc2, _ = scene.font_vmetrics(_TICK_LABEL_SIZE)
            title_h += _TICK_LENGTH + _TICK_LABEL_GAP + t_asc2 + t_desc2

        bands = (title_h, xlabel_h, ylabel_w, x_tick_h, y_tick_w, cbar_w)
        return bands, xticks, yticks

    # -- drawing ------------------------------------------------------------

    def _draw(self, scene: "_core.Scene", layout, xr, yr, xticks, yticks) -> None:
        plot = layout.plot
        px, py, pw, ph = plot.x, plot.y, plot.w, plot.h
        (xmin, xmax), (ymin, ymax) = xr, yr

        # Compose each axis' scale transform with the linear device map. For a
        # linear scale ``fx``/``fy`` are the identity, so ``sx``/``sy`` (and the
        # affine ``coeffs`` below) are bit-for-bit what the old linear-only code
        # produced; a nonlinear scale (log, ...) positions data in transformed
        # space while the device map stays affine.
        fx = self._xscale.transform
        fy = self._yscale.transform
        txmin, txmax = fx(xmin), fx(xmax)
        tymin, tymax = fy(ymin), fy(ymax)
        txspan = (txmax - txmin) or 1.0
        tyspan = (tymax - tymin) or 1.0

        # Equal aspect: shrink the used plot rect so one data (transformed) unit
        # spans the same device length on both axes, centering the smaller box.
        if self._aspect == "equal":
            u = min(pw / txspan, ph / tyspan)
            new_pw, new_ph = u * txspan, u * tyspan
            px += (pw - new_pw) / 2.0
            py += (ph - new_ph) / 2.0
            pw, ph = new_pw, new_ph

        def sx(x: float) -> float:
            return px + (fx(x) - txmin) / txspan * pw

        def sy(y: float) -> float:
            return py + ph - (fy(y) - tymin) / tyspan * ph

        # Affine map over *transformed* space (dx = ax*t + bx, dy = ay*t + by) for
        # the Rust polyline/marker fast paths.
        ax_c = pw / txspan
        bx_c = px - txmin * ax_c
        ay_c = -ph / tyspan
        by_c = py + ph - tymin * ay_c
        proj = _Proj(sx, sy, (ax_c, bx_c, ay_c, by_c),
                     self._xscale.code, self._yscale.code)

        # Theme: locals shadow the module defaults (sizes/colours) for this axes.
        t = self._theme
        _TICK_LABEL_SIZE = t.tick_label_size
        _AXIS_LABEL_SIZE = t.axis_label_size
        _TITLE_SIZE = t.title_size
        _SPINE = t.spine_color
        _BLACK = t.text_color
        sw = t.spine_width

        # Minor ticks: empty for linear scales (so linear output is unchanged),
        # e.g. the 2..9 x 10^k subdivisions on a log axis.
        x_minor = self._xscale.minor_ticks(xmin, xmax)
        y_minor = self._yscale.minor_ticks(ymin, ymax)

        # Axes background fill (behind everything in the plot area).
        if t.axes_facecolor is not None:
            scene.add_path(
                [(px, py), (px + pw, py), (px + pw, py + ph), (px, py + ph)],
                fill_color=t.axes_facecolor, close=True,
            )

        # Gridlines at tick positions, behind the data. ``grid`` may be overridden
        # per-axes via ``set(grid=)``; ``axis("off")`` suppresses it entirely.
        show_grid = (t.grid if self._grid_override is None else self._grid_override) \
            and not self._frame_off
        if show_grid:
            for value, _label in xticks:
                x = sx(value)
                scene.add_path([(x, py), (x, py + ph)],
                               stroke_color=t.grid_color, stroke_width=t.grid_width)
            for value, _label in yticks:
                y = sy(value)
                scene.add_path([(px, y), (px + pw, y)],
                               stroke_color=t.grid_color, stroke_width=t.grid_width)
            # Fainter, thinner minor gridlines (log subdivisions etc.).
            for value in x_minor:
                x = sx(value)
                scene.add_path([(x, py), (x, py + ph)],
                               stroke_color=t.grid_color, stroke_width=t.grid_width * 0.5)
            for value in y_minor:
                y = sy(value)
                scene.add_path([(px, y), (px + pw, y)],
                               stroke_color=t.grid_color, stroke_width=t.grid_width * 0.5)

        # Shaded reference bands (axhspan/axvspan), behind the data.
        if self._refs:
            scene.begin_group(1.0, 0.0, 0.0, 1.0, 0.0, 0.0, clip=(px, py, pw, ph))
            self._draw_spans(scene, sx, sy, px, py, pw, ph)
            scene.end_group()

        # Spines (despining is per-theme: only the listed edges are drawn;
        # ``axis("off")`` suppresses them all).
        if not self._frame_off:
            if "left" in t.spines:
                scene.add_path([(px, py), (px, py + ph)], stroke_color=_SPINE,
                               stroke_width=sw, cap="butt")
            if "bottom" in t.spines:
                scene.add_path([(px, py + ph), (px + pw, py + ph)], stroke_color=_SPINE,
                               stroke_width=sw, cap="butt")
            if "right" in t.spines:
                scene.add_path([(px + pw, py), (px + pw, py + ph)], stroke_color=_SPINE,
                               stroke_width=sw, cap="butt")
            if "top" in t.spines:
                scene.add_path([(px, py), (px + pw, py)], stroke_color=_SPINE,
                               stroke_width=sw, cap="butt")

        # All data marks, clipped to the plot rect.
        scene.begin_group(1.0, 0.0, 0.0, 1.0, 0.0, 0.0, clip=(px, py, pw, ph))
        for m in self._marks:
            self._draw_mark(scene, m, proj)
        scene.end_group()

        # Patches and reference lines, clipped, on top of the data.
        if self._patches or self._refs:
            scene.begin_group(1.0, 0.0, 0.0, 1.0, 0.0, 0.0, clip=(px, py, pw, ph))
            for p in self._patches:
                self._draw_patch(scene, p, sx, sy)
            self._draw_reflines(scene, sx, sy, px, py, pw, ph)
            scene.end_group()

        t_asc, t_desc, _ = scene.font_vmetrics(_TICK_LABEL_SIZE)

        # ``axis("off")`` suppresses every tick and tick label (the reserved
        # layout band is simply left empty); otherwise iterate the located ticks.
        _xt = [] if self._frame_off else xticks
        _yt = [] if self._frame_off else yticks
        _xm = [] if self._frame_off else x_minor
        _ym = [] if self._frame_off else y_minor

        # X ticks + labels.
        for value, label in _xt:
            x = sx(value)
            scene.add_path(
                [(x, py + ph), (x, py + ph + _TICK_LENGTH)],
                stroke_color=_SPINE,
                stroke_width=sw,
            )
            tw = _tw(scene, label, _TICK_LABEL_SIZE)
            baseline = py + ph + _TICK_LENGTH + _TICK_LABEL_GAP + t_asc
            _text(scene, x - tw / 2.0, baseline, label, _TICK_LABEL_SIZE, _BLACK)

        # Shorter, unlabeled minor tick marks (log subdivisions etc.).
        _MINOR_LEN = _TICK_LENGTH * 0.6
        for value in _xm:
            x = sx(value)
            scene.add_path([(x, py + ph), (x, py + ph + _MINOR_LEN)],
                           stroke_color=_SPINE, stroke_width=sw)

        # Y ticks + labels (right-aligned, vertically centered on the tick).
        for value, label in _yt:
            y = sy(value)
            scene.add_path(
                [(px - _TICK_LENGTH, y), (px, y)],
                stroke_color=_SPINE,
                stroke_width=sw,
            )
            tw = _tw(scene, label, _TICK_LABEL_SIZE)
            baseline = y + (t_asc - t_desc) / 2.0
            _text(scene, px - _TICK_LENGTH - _TICK_LABEL_GAP - tw, baseline, label,
                           _TICK_LABEL_SIZE, _BLACK)
        for value in _ym:
            y = sy(value)
            scene.add_path([(px - _MINOR_LEN, y), (px, y)],
                           stroke_color=_SPINE, stroke_width=sw)

        # Title, centered over the plot area.
        title_font = _font(t.title_weight)
        label_font = _font(t.axis_label_weight)
        if self._title:
            a, _d = _th(scene, self._title, _TITLE_SIZE, title_font)
            tw = _tw(scene, self._title, _TITLE_SIZE, title_font)
            baseline = layout.title.y + a
            _text(scene, px + (pw - tw) / 2.0, baseline, self._title, _TITLE_SIZE,
                  _BLACK, title_font)

        # X-axis label, centered over the plot area.
        if self._xlabel:
            a, _d = _th(scene, self._xlabel, _AXIS_LABEL_SIZE, label_font)
            tw = _tw(scene, self._xlabel, _AXIS_LABEL_SIZE, label_font)
            baseline = layout.xlabel.y + a
            _text(scene, px + (pw - tw) / 2.0, baseline, self._xlabel, _AXIS_LABEL_SIZE,
                  _BLACK, label_font)

        # Y-axis label, rotated 90deg CCW, centered on the plot area's height.
        if self._ylabel:
            a, d, _ = scene.font_vmetrics(_AXIS_LABEL_SIZE)
            tw = _tw(scene, self._ylabel, _AXIS_LABEL_SIZE, label_font)
            band = layout.ylabel
            pivot_x = band.x + band.w / 2.0 - (d - a) / 2.0
            pivot_y = py + ph / 2.0
            # Affine = translate(pivot) * rotate(-90deg): (x,y) -> (y+px, -x+py).
            scene.begin_group(0.0, -1.0, 1.0, 0.0, pivot_x, pivot_y)
            _text(scene, -tw / 2.0, 0.0, self._ylabel, _AXIS_LABEL_SIZE, _BLACK, label_font)
            scene.end_group()

        # Annotations (text + callout arrows), on top of the data.
        if self._annotations:
            self._draw_annotations(scene, sx, sy)

        # Colorbar, drawn in its reserved right-hand band (outside the clip).
        if self._colorbar is not None:
            self._draw_colorbar(scene, layout)

        # Legend, drawn last so it sits above the data (and outside the clip).
        if self._legend is not None:
            self._draw_legend(scene, px, py, pw, ph)

    def _draw_annotations(self, scene, sx, sy) -> None:
        size_default = self._theme.axis_label_size
        for an in self._annotations:
            size = an["size"] or size_default
            color = an["color"]
            if an["kind"] == "annotate":
                tx, ty = an["xytext"]
                hx, hy = an["xy"]
                if an["arrow"]:
                    _draw_arrow(scene, sx(tx), sy(ty), sx(hx), sy(hy),
                                self._theme.spine_color, max(self._theme.spine_width, 1.0))
                _place_text(scene, sx(tx), sy(ty), an["s"], size, color,
                            an["ha"], an["va"], an.get("font", "body"))
            else:  # plain text
                _place_text(scene, sx(an["x"]), sy(an["y"]), an["s"], size, color,
                            an["ha"], an["va"], an.get("font", "body"))

    # -- twin / secondary / inset drawing -----------------------------------

    def _proj_for(self, plot, xr, yr, xscale, yscale) -> "_Proj":
        """Build a projection (device map + affine coeffs) for a given plot rect,
        data ranges, and axis scales - the reusable core of ``_draw``."""
        px, py, pw, ph = plot.x, plot.y, plot.w, plot.h
        fx, fy = xscale.transform, yscale.transform
        txmin, tymin = fx(xr[0]), fy(yr[0])
        txspan = (fx(xr[1]) - txmin) or 1.0
        tyspan = (fy(yr[1]) - tymin) or 1.0

        def sx(x):
            return px + (fx(x) - txmin) / txspan * pw

        def sy(y):
            return py + ph - (fy(y) - tymin) / tyspan * ph

        ax_c = pw / txspan
        bx_c = px - txmin * ax_c
        ay_c = -ph / tyspan
        by_c = py + ph - tymin * ay_c
        return _Proj(sx, sy, (ax_c, bx_c, ay_c, by_c), xscale.code, yscale.code)

    def _draw_extras(self, scene, axl, xr, yr) -> None:
        plot = axl.plot
        t = self._theme
        _SPINE, sw, _BLACK = t.spine_color, t.spine_width, t.text_color
        _TL = t.tick_label_size
        t_asc, t_desc, _ = scene.font_vmetrics(_TL)

        if self._twinx is not None:
            tw = self._twinx
            _txr, tyr = tw._ranges()
            proj = self._proj_for(plot, xr, tyr, self._xscale, tw._yscale)
            scene.begin_group(1.0, 0.0, 0.0, 1.0, 0.0, 0.0,
                              clip=(plot.x, plot.y, plot.w, plot.h))
            for m in tw._marks:
                tw._draw_mark(scene, m, proj)
            scene.end_group()
            scene.add_path([(plot.x1, plot.y), (plot.x1, plot.y1)],
                           stroke_color=_SPINE, stroke_width=sw, cap="butt")
            for val, label in tw._yscale.ticks(tyr[0], tyr[1], 6):
                y = proj.sy(val)
                scene.add_path([(plot.x1, y), (plot.x1 + _TICK_LENGTH, y)],
                               stroke_color=_SPINE, stroke_width=sw)
                _text(scene, plot.x1 + _TICK_LENGTH + _TICK_LABEL_GAP,
                      y + (t_asc - t_desc) / 2.0, label, _TL, _BLACK)
            if tw._ylabel:
                self._draw_side_label(scene, axl.cbar, plot, tw._ylabel, right=True)

        if self._twiny is not None:
            tw = self._twiny
            txr, _tyr = tw._ranges()
            proj = self._proj_for(plot, txr, yr, tw._xscale, self._yscale)
            scene.begin_group(1.0, 0.0, 0.0, 1.0, 0.0, 0.0,
                              clip=(plot.x, plot.y, plot.w, plot.h))
            for m in tw._marks:
                tw._draw_mark(scene, m, proj)
            scene.end_group()
            scene.add_path([(plot.x, plot.y), (plot.x1, plot.y)],
                           stroke_color=_SPINE, stroke_width=sw, cap="butt")
            for val, label in tw._xscale.ticks(txr[0], txr[1], 7):
                x = proj.sx(val)
                scene.add_path([(x, plot.y), (x, plot.y - _TICK_LENGTH)],
                               stroke_color=_SPINE, stroke_width=sw)
                lw = _tw(scene, label, _TL)
                _text(scene, x - lw / 2.0, plot.y - _TICK_LENGTH - _TICK_LABEL_GAP - t_desc,
                      label, _TL, _BLACK)

        for spec in self._secondary:
            self._draw_secondary(scene, plot, xr, yr, spec)

        for child, (fx0, fy0, fw, fh) in self._insets:
            cell = _Rect(plot.x + fx0 * plot.w, plot.y + (1.0 - fy0 - fh) * plot.h,
                         fw * plot.w, fh * plot.h)
            cxr, cyr = child._ranges()
            bands, cxt, cyt = child._bands(scene, cxr, cyr)
            child._draw(scene, _layout_cell(cell, bands), cxr, cyr, cxt, cyt)

    def _draw_side_label(self, scene, band, plot, text, right: bool) -> None:
        t = self._theme
        size = t.axis_label_size
        a, d, _ = scene.font_vmetrics(size)
        tw = _tw(scene, text, size)
        pivot_x = band.x + band.w - (a + d) / 2.0 if right else band.x + (a + d) / 2.0
        pivot_y = plot.y + plot.h / 2.0
        # Rotate +90deg (reads bottom-to-top on the right side).
        scene.begin_group(0.0, 1.0, -1.0, 0.0, pivot_x, pivot_y)
        _text(scene, -tw / 2.0, 0.0, text, size, t.text_color)
        scene.end_group()

    def _draw_secondary(self, scene, plot, xr, yr, spec) -> None:
        t = self._theme
        _SPINE, sw, _BLACK = t.spine_color, t.spine_width, t.text_color
        _TL = t.tick_label_size
        t_asc, t_desc, _ = scene.font_vmetrics(_TL)
        fns = spec["functions"]
        fwd = fns[0] if fns else (lambda v: v)
        inv = fns[1] if fns else (lambda v: v)
        hproj = self._proj_for(plot, xr, yr, self._xscale, self._yscale)
        if spec["axis"] == "x":
            s0, s1 = fwd(xr[0]), fwd(xr[1])
            ticks = _core.nice_ticks(min(s0, s1), max(s0, s1), 7)
            top = spec["loc"] == "top"
            edge_y = plot.y if top else plot.y1
            direction = -1.0 if top else 1.0
            scene.add_path([(plot.x, edge_y), (plot.x1, edge_y)],
                           stroke_color=_SPINE, stroke_width=sw, cap="butt")
            for sval, label in ticks:
                x = hproj.sx(inv(sval))
                if x < plot.x - 0.5 or x > plot.x1 + 0.5:
                    continue
                scene.add_path([(x, edge_y), (x, edge_y + direction * _TICK_LENGTH)],
                               stroke_color=_SPINE, stroke_width=sw)
                lw = _tw(scene, label, _TL)
                by = (edge_y - _TICK_LENGTH - _TICK_LABEL_GAP - t_desc if top
                      else edge_y + _TICK_LENGTH + _TICK_LABEL_GAP + t_asc)
                _text(scene, x - lw / 2.0, by, label, _TL, _BLACK)
        else:  # secondary y
            s0, s1 = fwd(yr[0]), fwd(yr[1])
            ticks = _core.nice_ticks(min(s0, s1), max(s0, s1), 6)
            right = spec["loc"] == "right"
            edge_x = plot.x1 if right else plot.x
            direction = 1.0 if right else -1.0
            scene.add_path([(edge_x, plot.y), (edge_x, plot.y1)],
                           stroke_color=_SPINE, stroke_width=sw, cap="butt")
            for sval, label in ticks:
                y = hproj.sy(inv(sval))
                if y < plot.y - 0.5 or y > plot.y1 + 0.5:
                    continue
                scene.add_path([(edge_x, y), (edge_x + direction * _TICK_LENGTH, y)],
                               stroke_color=_SPINE, stroke_width=sw)
                lw = _tw(scene, label, _TL)
                bx = (edge_x + _TICK_LENGTH + _TICK_LABEL_GAP if right
                      else edge_x - _TICK_LENGTH - _TICK_LABEL_GAP - lw)
                _text(scene, bx, y + (t_asc - t_desc) / 2.0, label, _TL, _BLACK)

    # -- reference lines & patches drawing ----------------------------------

    def _draw_spans(self, scene, sx, sy, px, py, pw, ph) -> None:
        """Draw shaded axhspan/axvspan bands (behind the data)."""
        for r in self._refs:
            k = r["kind"]
            if k == "axhspan":
                y0, y1 = sy(r["lo"]), sy(r["hi"])
                x0, x1 = px + r["min"] * pw, px + r["max"] * pw
            elif k == "axvspan":
                x0, x1 = sx(r["lo"]), sx(r["hi"])
                # fraction 0 = bottom (py+ph), 1 = top (py), in y-down device space.
                y0, y1 = py + ph - r["min"] * ph, py + ph - r["max"] * ph
            else:
                continue
            scene.add_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                           fill_color=_with_alpha(r["color"], r["alpha"]), close=True)

    def _draw_reflines(self, scene, sx, sy, px, py, pw, ph) -> None:
        """Draw axhline/axvline/axline reference guides (on top of the data)."""
        for r in self._refs:
            k = r["kind"]
            if k == "axhline":
                y = sy(r["y"])
                x0, x1 = px + r["min"] * pw, px + r["max"] * pw
                scene.add_path([(x0, y), (x1, y)], stroke_color=r["color"],
                               stroke_width=r["width"], dash=_dash_for(r["linestyle"]))
            elif k == "axvline":
                x = sx(r["x"])
                y0, y1 = py + ph - r["min"] * ph, py + ph - r["max"] * ph
                scene.add_path([(x, y0), (x, y1)], stroke_color=r["color"],
                               stroke_width=r["width"], dash=_dash_for(r["linestyle"]))
            elif k == "axline":
                self._draw_axline(scene, r, sx, sy, px, py, pw, ph)

    def _draw_axline(self, scene, r, sx, sy, px, py, pw, ph) -> None:
        p1x, p1y = r["p1"]
        if r["slope"] is not None:
            p2x, p2y = p1x + 1.0, p1y + r["slope"]
        else:
            p2x, p2y = r["p2"]
        d1x, d1y = sx(p1x), sy(p1y)
        d2x, d2y = sx(p2x), sy(p2y)
        ddx, ddy = d2x - d1x, d2y - d1y
        if ddx == 0.0 and ddy == 0.0:
            return
        # Extend far past the plot rect in both directions, then clip to it.
        big = 1e5
        seg = _clip_segment(d1x - ddx * big, d1y - ddy * big,
                            d1x + ddx * big, d1y + ddy * big, px, py, pw, ph)
        if seg is not None:
            scene.add_path([(seg[0], seg[1]), (seg[2], seg[3])], stroke_color=r["color"],
                           stroke_width=r["width"], dash=_dash_for(r["linestyle"]))

    def _draw_patch(self, scene, p, sx, sy) -> None:
        k = p["kind"]
        if k == "arrow":
            _draw_arrow(scene, sx(p["x"]), sy(p["y"]),
                        sx(p["x"] + p["dx"]), sy(p["y"] + p["dy"]),
                        p["edgecolor"], p["linewidth"])
            return
        if k == "rectangle":
            x0, y0 = p["xy"]
            w, h = p["w"], p["h"]
            a = math.radians(p["angle"])
            ca, sa = math.cos(a), math.sin(a)
            data_pts = [(x0 + cx * ca - cy * sa, y0 + cx * sa + cy * ca)
                        for cx, cy in ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h))]
            closed = True
        elif k == "ellipse":
            cx, cy = p["xy"]
            rx, ry = p["rx"], p["ry"]
            a = math.radians(p["angle"])
            ca, sa = math.cos(a), math.sin(a)
            data_pts = []
            for i in range(_ELLIPSE_N):
                th = 2.0 * math.pi * i / _ELLIPSE_N
                ex, ey = rx * math.cos(th), ry * math.sin(th)
                data_pts.append((cx + ex * ca - ey * sa, cy + ex * sa + ey * ca))
            closed = True
        else:  # polygon
            data_pts = p["pts"]
            closed = p["closed"]
        dev = [(sx(x), sy(y)) for x, y in data_pts]
        if len(dev) < 2:
            return
        scene.add_path(dev, fill_color=p["facecolor"], close=closed,
                       stroke_color=p["edgecolor"],
                       stroke_width=p["linewidth"] if p["edgecolor"] else 1.0,
                       dash=_dash_for(p["linestyle"]))
        if p["hatch"]:
            hc = p["edgecolor"] or self._theme.text_color
            _draw_hatch(scene, dev, p["hatch"], hc, max(p["linewidth"] * 0.5, 0.5))

    def _draw_mark(self, scene, m: dict, proj: "_Proj") -> None:
        sx, sy = proj.sx, proj.sy
        kind = m["kind"]
        if kind == "line":
            # Fast path: map + build the polyline in Rust (no per-point Python).
            # The scale transform (identity for linear) is applied per point in
            # Rust before the affine ``coeffs``, so any scale stays on the fast path.
            ax, bx, ay, by = proj.coeffs
            xc, yc = proj.xcode, proj.ycode
            if _draws_line(m["linestyle"]) and len(m["xs"]) >= 2:
                scene.add_line_xform(m["xs"], m["ys"], ax, bx, ay, by, m["color"],
                                     m["width"], _dash_for(m["linestyle"]), "round", "round",
                                     m.get("simplify", True), 0.1, xc, yc)
            if m["marker"]:
                scene.add_markers_xform(m["xs"], m["ys"], ax, bx, ay, by, m["marker"],
                                        m["markersize"], m["color"], None, 1.0, xc, yc)
        elif kind == "scatter":
            ax, bx, ay, by = proj.coeffs
            if m.get("colors") is not None:
                scene.add_markers_xform_colored(
                    m["xs"], m["ys"], ax, bx, ay, by, m["marker"],
                    m["markersize"], m["colors"], m["edgecolor"],
                    m["edgewidth"], proj.xcode, proj.ycode)
            else:
                scene.add_markers_xform(m["xs"], m["ys"], ax, bx, ay, by, m["marker"],
                                        m["markersize"], m["color"], m["edgecolor"],
                                        m["edgewidth"], proj.xcode, proj.ycode)
        elif kind == "bar":
            hw = m["width"] / 2.0
            for x, h, b in zip(m["xs"], m["heights"], m["bottoms"]):
                x0, x1 = sx(x - hw), sx(x + hw)
                y0, y1 = sy(b), sy(b + h)
                scene.add_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                               fill_color=m["color"], close=True,
                               stroke_color=m["edgecolor"], stroke_width=1.0)
        elif kind == "hist":
            edges, counts = m["edges"], m["counts"]
            y0 = sy(0.0)
            for i, c in enumerate(counts):
                x0, x1 = sx(edges[i]), sx(edges[i + 1])
                y1 = sy(c)
                scene.add_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                               fill_color=m["color"], close=True,
                               stroke_color=self._theme.separator_color,
                               stroke_width=0.75)
        elif kind == "fill":
            if m.get("orient", "y") == "x":
                seq = m["ys"]
                top = [(sx(a), sy(y)) for y, a in zip(seq, m["y1"])]
                bot = [(sx(b), sy(y)) for y, b in zip(reversed(seq), reversed(m["y2"]))]
            else:
                seq = m["xs"]
                top = [(sx(x), sy(a)) for x, a in zip(seq, m["y1"])]
                bot = [(sx(x), sy(b)) for x, b in zip(reversed(seq), reversed(m["y2"]))]
            poly = top + bot
            if len(poly) >= 3:
                scene.add_path(poly, fill_color=_with_alpha(m["color"], m["alpha"]), close=True)
        elif kind == "lines":
            dash = _dash_for(m["linestyle"])
            horizontal = m["orient"] == "h"
            for p, a, b in zip(m["pos"], m["lo"], m["hi"]):
                if horizontal:
                    pts = [(sx(a), sy(p)), (sx(b), sy(p))]
                else:
                    pts = [(sx(p), sy(a)), (sx(p), sy(b))]
                scene.add_path(pts, stroke_color=m["color"], stroke_width=m["width"],
                               dash=dash, cap="butt")
        elif kind == "errorbar":
            self._draw_errorbar(scene, m, proj)
        elif kind == "image":
            self._draw_image(scene, m, sx, sy)
        elif kind == "barh":
            hh = m["height"] / 2.0
            for y, wdt, lft in zip(m["ys"], m["widths"], m["lefts"]):
                x0, x1 = sx(lft), sx(lft + wdt)
                y0, y1 = sy(y - hh), sy(y + hh)
                scene.add_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                               fill_color=m["color"], close=True,
                               stroke_color=m["edgecolor"], stroke_width=1.0)
        elif kind == "stem":
            y0 = sy(m["bottom"])
            baseline_pts = []
            for x, y in zip(m["xs"], m["ys"]):
                X = sx(x)
                scene.add_path([(X, y0), (X, sy(y))], stroke_color=m["color"], stroke_width=1.0)
                baseline_pts.append((X, y0))
            if baseline_pts:
                scene.add_path([baseline_pts[0], baseline_pts[-1]],
                               stroke_color=m["color"], stroke_width=1.0)
            if m["marker"]:
                for x, y in zip(m["xs"], m["ys"]):
                    _draw_marker(scene, sx(x), sy(y), m["markersize"], m["marker"], m["color"])
        elif kind == "broken_barh":
            y0, y1 = sy(m["y0"]), sy(m["y0"] + m["h"])
            for x0d, wdt in m["bars"]:
                x0, x1 = sx(x0d), sx(x0d + wdt)
                scene.add_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                               fill_color=_with_alpha(m["color"], m["alpha"]), close=True,
                               stroke_color=m["edgecolor"],
                               stroke_width=1.0 if m["edgecolor"] else 1.0)
        elif kind == "eventplot":
            horiz = m["orientation"] == "horizontal"
            half = m["length"] / 2.0
            for i, row in enumerate(m["rows"]):
                off = m["offset"] * i
                for pos in row:
                    if horiz:
                        scene.add_path([(sx(pos), sy(off - half)), (sx(pos), sy(off + half))],
                                       stroke_color=m["color"], stroke_width=m["width"])
                    else:
                        scene.add_path([(sx(off - half), sy(pos)), (sx(off + half), sy(pos))],
                                       stroke_color=m["color"], stroke_width=m["width"])
        elif kind == "boxplot":
            self._draw_boxplot(scene, m, sx, sy)
        elif kind == "violin":
            self._draw_violin(scene, m, sx, sy)
        elif kind == "hexbin":
            for (cx, cy), col in zip(m["centers"], m["colors"]):
                poly = [(sx(cx + ox), sy(cy + oy)) for ox, oy in m["offsets"]]
                scene.add_path(poly, fill_color=col, close=True)
        elif kind == "quadmesh":
            for x0, x1, y0, y1, col in m["quads"]:
                scene.add_path([(sx(x0), sy(y0)), (sx(x1), sy(y0)),
                                (sx(x1), sy(y1)), (sx(x0), sy(y1))],
                               fill_color=col, close=True)
        elif kind == "contour":
            xc, yc, w = m["xcoords"], m["ycoords"], m["width"]
            for li, x0, y0, x1, y1 in m["segs"]:
                col = m["colors"][li] if li < len(m["colors"]) else m["colors"][-1]
                scene.add_path(
                    [(sx(_interp_coord(xc, x0)), sy(_interp_coord(yc, y0))),
                     (sx(_interp_coord(xc, x1)), sy(_interp_coord(yc, y1)))],
                    stroke_color=col, stroke_width=w)
        elif kind == "contourf":
            self._draw_field_image(scene, m, sx, sy)
        elif kind == "quiver":
            for x, y, u, v in zip(m["xs"], m["ys"], m["us"], m["vs"]):
                _draw_arrow(scene, sx(x), sy(y),
                            sx(x + u * m["scale"]), sy(y + v * m["scale"]),
                            m["color"], m["width"], head_len=6.0, head_w=2.5)
        elif kind == "pie":
            self._draw_pie(scene, m, sx, sy)

    def _draw_boxplot(self, scene, m, sx, sy) -> None:
        hw = m["width"] / 2.0
        col = m["color"]
        for pos, st in zip(m["positions"], m["stats"]):
            x0, x1 = sx(pos - hw), sx(pos + hw)
            xc = sx(pos)
            q1, q3 = sy(st["q1"]), sy(st["q3"])
            # Box (IQR) with median line.
            scene.add_path([(x0, q1), (x1, q1), (x1, q3), (x0, q3)], close=True,
                           fill_color=_with_alpha(col, 0.25), stroke_color=col, stroke_width=1.2)
            ymed = sy(st["med"])
            scene.add_path([(x0, ymed), (x1, ymed)], stroke_color=col, stroke_width=1.6)
            # Whiskers + caps.
            for yq, yend in ((q1, sy(st["lo"])), (q3, sy(st["hi"]))):
                scene.add_path([(xc, yq), (xc, yend)], stroke_color=col, stroke_width=1.0)
                scene.add_path([(x0 + (x1 - x0) * 0.25, yend), (x1 - (x1 - x0) * 0.25, yend)],
                               stroke_color=col, stroke_width=1.0)
            if m["showfliers"]:
                for fv in st["fliers"]:
                    _draw_marker(scene, xc, sy(fv), 4.0, "o", None, edgecolor=col, edgewidth=1.0)

    def _draw_violin(self, scene, m, sx, sy) -> None:
        col = m["color"]
        hw = m["width"] / 2.0
        for pos, (grid, dens) in zip(m["positions"], m["violins"]):
            if not grid:
                continue
            peak = max(dens) or 1.0
            left = [(sx(pos - hw * d / peak), sy(g)) for g, d in zip(grid, dens)]
            right = [(sx(pos + hw * d / peak), sy(g)) for g, d in reversed(list(zip(grid, dens)))]
            poly = left + right
            if len(poly) >= 3:
                scene.add_path(poly, fill_color=_with_alpha(col, 0.4), close=True,
                               stroke_color=col, stroke_width=1.0)

    def _draw_field_image(self, scene, m, sx, sy) -> None:
        if m["uw"] == 0 or m["uh"] == 0:
            return
        x0, x1, y0, y1 = m["extent"]
        left, right = sx(x0), sx(x1)
        rx, rw = min(left, right), abs(right - left)
        top, bot = sy(max(y0, y1)), sy(min(y0, y1))
        scene.add_image(m["img"], m["uw"], m["uh"], rx, top, rw, bot - top)

    def _draw_pie(self, scene, m, sx, sy) -> None:
        r = m["radius"]
        cx0, cy0 = sx(0.0), sy(0.0)
        for wd in m["wedges"]:
            a0, a1 = wd["a0"], wd["a1"]
            n = max(2, int((a1 - a0) / (math.pi / 36)) + 1)
            pts = [(cx0, cy0)]
            for i in range(n + 1):
                a = a0 + (a1 - a0) * i / n
                pts.append((sx(r * math.cos(a)), sy(r * math.sin(a))))
            scene.add_path(pts, fill_color=wd["color"], close=True,
                           stroke_color=self._theme.separator_color, stroke_width=1.0)
        # Slice labels just outside each wedge, at its mid-angle. The pie sets
        # its view limits to +/-1.3r, so labels at 1.12r sit clear of the rim.
        lab_size = self._theme.tick_label_size
        for wd in m["wedges"]:
            lab = wd.get("label")
            if not lab:
                continue
            am = (wd["a0"] + wd["a1"]) / 2.0
            lx = sx(r * 1.12 * math.cos(am))
            ly = sy(r * 1.12 * math.sin(am))
            w = _tw(scene, lab, lab_size)
            asc, desc = _th(scene, lab, lab_size)
            tx = lx if math.cos(am) >= 0.0 else lx - w
            _text(scene, tx, ly + (asc - desc) / 2.0, lab, lab_size, self._theme.text_color)

    def _draw_image(self, scene, m: dict, sx, sy) -> None:
        x0, x1, y0, y1 = m["extent"]
        w, h = m["w"], m["h"]
        if w == 0 or h == 0:
            return
        # Device bbox of the extent (y-down, so the larger data-y is the top).
        left, right = sx(x0), sx(x1)
        rx, rw = min(left, right), abs(right - left)
        top, bot = sy(max(y0, y1)), sy(min(y0, y1))
        ry, rh = top, bot - top

        # 256-entry RGBA LUT, cached per colormap; the per-pixel lookup (the hot
        # loop) runs in Rust via add_colormapped_image, reading `flat` - already
        # row-major and contiguous from ingest - straight out of its buffer.
        lut = _colormap_lut(m["cmap"])
        flat = m["flat"]
        scene.add_colormapped_image(flat, w, h, m["vmin"], m["vmax"], lut,
                                    m["origin"] == "upper", rx, ry, rw, rh,
                                    m.get("norm_code", "linear"))

    def _draw_errorbar(self, scene, m: dict, proj: "_Proj") -> None:
        """Draw one errorbar mark.

        Takes the whole :class:`_Proj` rather than bare ``sx``/``sy`` closures:
        the connecting line and the markers go through the Rust fast paths,
        which need the affine coefficients *and* the scale codes. Deriving the
        coefficients here by sampling ``sx(0.0)``/``sx(1.0)`` (as this used to)
        is only valid on a linear axis - under a log scale ``sx(0.0)`` is
        ``-inf``, which poisoned the coefficients and made the line and markers
        vanish, leaving bare whiskers.
        """
        sx, sy = proj.sx, proj.sy
        color, w, cap = m["color"], m["width"], m["capsize"]
        ax, bx, ay, by = proj.coeffs
        xc, yc = proj.xcode, proj.ycode
        if _draws_line(m["linestyle"]) and len(m["xs"]) >= 2:
            scene.add_line_xform(m["xs"], m["ys"], ax, bx, ay, by, color, w,
                                 _dash_for(m["linestyle"]), "round", "round",
                                 True, 0.1, xc, yc)
        for i, (x, y) in enumerate(zip(m["xs"], m["ys"])):
            X, Y = sx(x), sy(y)
            if m["yerr"]:
                e = m["yerr"][i]
                ytop, ybot = sy(y + e), sy(y - e)
                scene.add_path([(X, ybot), (X, ytop)], stroke_color=color, stroke_width=w)
                if cap > 0:
                    scene.add_path([(X - cap, ytop), (X + cap, ytop)], stroke_color=color, stroke_width=w)
                    scene.add_path([(X - cap, ybot), (X + cap, ybot)], stroke_color=color, stroke_width=w)
            if m["xerr"]:
                e = m["xerr"][i]
                xleft, xright = sx(x - e), sx(x + e)
                scene.add_path([(xleft, Y), (xright, Y)], stroke_color=color, stroke_width=w)
                if cap > 0:
                    scene.add_path([(xleft, Y - cap), (xleft, Y + cap)], stroke_color=color, stroke_width=w)
                    scene.add_path([(xright, Y - cap), (xright, Y + cap)], stroke_color=color, stroke_width=w)
        if m["marker"]:
            scene.add_markers_xform(m["xs"], m["ys"], ax, bx, ay, by, m["marker"],
                                    m["markersize"], color, None, 1.0, xc, yc)

    # -- colorbar -----------------------------------------------------------

    def _draw_colorbar(self, scene, layout) -> None:
        t = self._theme
        _TICK_LABEL_SIZE = t.tick_label_size
        _AXIS_LABEL_SIZE = t.axis_label_size
        _SPINE = t.spine_color
        _BLACK = t.text_color
        cb = self._colorbar
        cmap = cb["cmap"]
        vmin, vmax = cb["vmin"], cb["vmax"]
        plot = layout.plot
        band = layout.cbar

        # Strip aligned vertically with the plot area.
        strip_x = band.x + _CBAR_GAP
        strip_y = plot.y
        strip_h = plot.h
        strip_w = _CBAR_WIDTH

        # Vertical gradient: N rows x 1 col, row 0 = top = vmax.
        n = 256
        buf = bytearray(n * 4)
        denom = n - 1
        for i in range(n):
            frac = 1.0 - i / denom
            r, g, b, a = cmap(frac)
            o = i * 4
            buf[o] = r
            buf[o + 1] = g
            buf[o + 2] = b
            buf[o + 3] = a
        scene.add_image(bytes(buf), 1, n, strip_x, strip_y, strip_w, strip_h)

        # Thin border around the strip.
        scene.add_path(
            [(strip_x, strip_y), (strip_x + strip_w, strip_y),
             (strip_x + strip_w, strip_y + strip_h), (strip_x, strip_y + strip_h)],
            close=True, stroke_color=_SPINE, stroke_width=0.8,
        )

        # Ticks + labels to the right of the strip. A norm (e.g. LogNorm) drives
        # both the tick values and their fractional positions on the strip.
        t_asc, t_desc, _ = scene.font_vmetrics(_TICK_LABEL_SIZE)
        span = (vmax - vmin) or 1.0
        norm = cb.get("norm")
        for value, label in _colorbar_ticks(cb):
            frac = norm(value) if norm is not None else (value - vmin) / span
            ty = strip_y + strip_h - frac * strip_h
            scene.add_path(
                [(strip_x + strip_w, ty), (strip_x + strip_w + _CBAR_TICK_LEN, ty)],
                stroke_color=_SPINE, stroke_width=1.0,
            )
            baseline = ty + (t_asc - t_desc) / 2.0
            _text(scene, strip_x + strip_w + _CBAR_TICK_LEN + _CBAR_TICK_GAP, baseline,
                           label, _TICK_LABEL_SIZE, _BLACK)

        # Rotated colorbar label at the band's right edge (reads bottom-to-top).
        if cb["label"]:
            a, d, _ = scene.font_vmetrics(_AXIS_LABEL_SIZE)
            tw = _tw(scene, cb["label"], _AXIS_LABEL_SIZE)
            pivot_x = band.x1 - d - 1.0
            pivot_y = strip_y + strip_h / 2.0
            scene.begin_group(0.0, -1.0, 1.0, 0.0, pivot_x, pivot_y)
            _text(scene, -tw / 2.0, 0.0, cb["label"], _AXIS_LABEL_SIZE, _BLACK)
            scene.end_group()

    # -- legend -------------------------------------------------------------

    def _legend_entries(self) -> list[dict]:
        """Labelled 2D marks, passed through with their kind intact so the glyph
        drawer can pick a swatch for bar/hist/fill and a rule for lines."""
        return [m for m in self._marks if m.get("label")]

    def _draw_legend(self, scene, px: float, py: float, pw: float, ph: float) -> None:
        entries = self._legend_entries()
        if not entries:
            return

        box_w, box_h, mt = _measure_legend(scene, entries, self._theme)
        inset = 6.0
        loc = self._legend["loc"]
        right = px + pw - inset - box_w
        left = px + inset
        top = py + inset
        bottom = py + ph - inset - box_h
        hcenter = px + (pw - box_w) / 2.0
        positions = {
            "best": (right, top),
            "upper right": (right, top),
            "upper left": (left, top),
            "lower right": (right, bottom),
            "lower left": (left, bottom),
            "upper center": (hcenter, top),
            "lower center": (hcenter, bottom),
        }
        bx, by = positions.get(loc, (right, top))
        _draw_legend_box(scene, entries, bx, by, mt)


# -- legend helpers (shared by per-axes and figure-level legends) -----------

def _measure_legend(scene, entries, theme=None):
    """Size a legend box for ``entries``. Returns ``(box_w, box_h, metrics)``
    where ``metrics`` is a dict reused by :func:`_draw_legend_box` so the box is
    measured and drawn from one source of truth (lets the figure layout reserve
    exactly the column width the box will occupy)."""
    t = _theme.get(theme)
    size = t.legend_size
    a, desc, _ = scene.font_vmetrics(size)
    row_h = a + desc
    row_gap = row_h * 0.55
    glyph_w = 22.0
    glyph_gap = 5.0
    pad = 6.0
    label_w = max(_tw(scene, m["label"], size) for m in entries)
    box_w = pad * 2.0 + glyph_w + glyph_gap + label_w
    n = len(entries)
    box_h = pad * 2.0 + n * row_h + (n - 1) * row_gap
    mt = {
        "size": size, "ascent": a, "row_h": row_h, "row_gap": row_gap,
        "glyph_w": glyph_w, "glyph_gap": glyph_gap, "pad": pad,
        "box_w": box_w, "box_h": box_h,
        "bg": t.legend_facecolor, "border": t.legend_edgecolor, "text_color": t.text_color,
    }
    return box_w, box_h, mt


def _draw_legend_box(scene, entries, bx: float, by: float, mt: dict) -> None:
    """Draw the legend frame, glyphs and labels with top-left corner ``(bx, by)``."""
    box_w, box_h, pad = mt["box_w"], mt["box_h"], mt["pad"]
    scene.add_path(
        [(bx, by), (bx + box_w, by), (bx + box_w, by + box_h), (bx, by + box_h)],
        fill_color=mt["bg"], close=True,
        stroke_color=mt["border"], stroke_width=0.8,
    )
    y = by + pad
    for m in entries:
        gx0 = bx + pad
        gx1 = gx0 + mt["glyph_w"]
        gcy = y + mt["row_h"] / 2.0
        _draw_legend_glyph(scene, m, gx0, gx1, gcy, mt["size"])
        _text(scene, gx1 + mt["glyph_gap"], y + mt["ascent"], m["label"], mt["size"],
              mt["text_color"])
        y += mt["row_h"] + mt["row_gap"]


#: Legend kinds drawn as a filled swatch rather than a line or marker.
_LEGEND_SWATCH_KINDS = ("bar", "barh", "hist", "fill")


def _draw_legend_glyph(scene, m: dict, x0: float, x1: float, cy: float,
                       size: float) -> None:
    """Draw one legend key. ``size`` is the theme's legend type size, so the
    swatch scales with the box the caller measured (they used to disagree: the
    box was measured at ``theme.legend_size`` and the swatch drawn at a fixed
    9 pt, which showed up under ``themes.presentation``)."""
    kind = m["kind"]
    color = m["color"]
    cx = (x0 + x1) / 2.0
    if kind in _LEGEND_SWATCH_KINDS:
        h = size * 0.85
        fill = _with_alpha(color, m["alpha"]) if kind == "fill" else color
        scene.add_path(
            [(x0 + 2.0, cy - h / 2.0), (x1 - 2.0, cy - h / 2.0),
             (x1 - 2.0, cy + h / 2.0), (x0 + 2.0, cy + h / 2.0)],
            fill_color=fill, close=True,
        )
    elif kind == "scatter":
        _draw_marker(scene, cx, cy, m["markersize"], m["marker"],
                     facecolor=color, edgecolor=m["edgecolor"], edgewidth=m["edgewidth"])
    elif kind == "errorbar":
        if _draws_line(m["linestyle"]):
            scene.add_path([(x0 + 1.0, cy), (x1 - 1.0, cy)], stroke_color=color,
                           stroke_width=m["width"], cap="round")
        scene.add_path([(cx, cy - 3.0), (cx, cy + 3.0)], stroke_color=color, stroke_width=m["width"])
        if m["marker"]:
            _draw_marker(scene, cx, cy, m["markersize"], m["marker"], facecolor=color)
    else:  # line, and any future kind that carries a stroke
        # ``.get`` rather than ``[]``: an unknown kind should degrade to a plain
        # rule, never raise mid-render. ``barh`` used to land here and die on
        # the missing "linestyle" key.
        linestyle = m.get("linestyle", "solid")
        if _draws_line(linestyle):
            scene.add_path([(x0 + 1.0, cy), (x1 - 1.0, cy)], stroke_color=color,
                           stroke_width=m.get("width", 1.5), cap="round",
                           dash=_dash_for(linestyle))
        if m.get("marker"):
            _draw_marker(scene, cx, cy, m.get("markersize", 5.0), m["marker"],
                         facecolor=color)


def _grid_xyz(X, Y, Z):
    """Normalize surface inputs to 2D grids ``(gx, gy, gz, nrows, ncols)``.

    ``Z`` is a 2D ``nrows x ncols`` grid. ``X``/``Y`` may each be 2D grids of
    the same shape, or 1D (``X`` length ncols, ``Y`` length nrows), in which
    case they are broadcast.
    """
    gz = [[float(v) for v in row] for row in Z]
    nr = len(gz)
    nc = len(gz[0]) if gz else 0

    def is_2d(a) -> bool:
        return len(a) > 0 and isinstance(a[0], (list, tuple))

    if is_2d(X):
        gx = [[float(v) for v in row] for row in X]
    else:
        col = [float(v) for v in X]
        gx = [list(col) for _ in range(nr)]
    if is_2d(Y):
        gy = [[float(v) for v in row] for row in Y]
    else:
        rowv = [float(v) for v in Y]
        gy = [[rowv[i]] * nc for i in range(nr)]
    return gx, gy, gz, nr, nc


class Axes3D(_AxesBase):
    """A 3D axes. Marks (scatter/plot/surface) are projected to 2D paths by an
    orthographic camera and depth-sorted, then drawn through the normal IR."""

    # A 3D cell is filled by the projection, so there is no reliably clear
    # corner to search for; pin one instead.
    _LEGEND_DEFAULT_LOC = "upper right"
    _MARKS_ATTR = "_marks3"

    def __init__(self, theme: Theme | None = None) -> None:
        self._init_common(theme)
        self._marks3: list[dict] = []
        self._xlabel: str | None = None
        self._ylabel: str | None = None
        self._zlabel: str | None = None
        self._xlim: tuple[float, float] | None = None
        self._ylim: tuple[float, float] | None = None
        self._zlim: tuple[float, float] | None = None
        self._elev = 30.0
        self._azim = -60.0

    # -- public API ---------------------------------------------------------

    def scatter(self, xs, ys, zs, *, label: str | None = None, color=None,
                markersize: float | None = None, alpha: float = 1.0,
                marker: str = "o", edgecolor=None, size: float | None = None) -> "Axes3D":
        """Scatter 3D points at ``(xs, ys, zs)``.

        ``markersize`` is a diameter in points; ``size`` is the matplotlib-style
        area in pt² (see :meth:`Axes.scatter`)."""
        self._marks3.append({
            "kind": "scatter",
            "xs": [float(x) for x in xs],
            "ys": [float(y) for y in ys],
            "zs": [float(z) for z in zs],
            "label": label,
            "color": self._mark_color(color, alpha),
            "markersize": self._marker_diameter(markersize, size),
            "marker": marker,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
        })
        return self

    def plot(self, xs, ys, zs, *, label: str | None = None, color=None,
             linewidth: float = 1.5, alpha: float = 1.0,
             linestyle: str = "solid") -> "Axes3D":
        """Draw a 3D polyline through ``(xs, ys, zs)``."""
        self._marks3.append({
            "kind": "line",
            "xs": [float(x) for x in xs],
            "ys": [float(y) for y in ys],
            "zs": [float(z) for z in zs],
            "label": label,
            "color": self._next_color(color),
            "width": float(linewidth),
            "linestyle": linestyle,
        })
        return self

    def surface(self, X, Y, Z, *, cmap="viridis", label: str | None = None) -> "Axes3D":
        """Draw a colormapped surface over the grid ``(X, Y, Z)``."""
        gx, gy, gz, nr, nc = _grid_xyz(X, Y, Z)
        zflat = [v for row in gz for v in row]
        self._marks3.append({
            "kind": "surface",
            "gx": gx,
            "gy": gy,
            "gz": gz,
            "nr": nr,
            "nc": nc,
            "xflat": [v for row in gx for v in row],
            "yflat": [v for row in gy for v in row],
            "zflat": zflat,
            "zmin": min(zflat) if zflat else 0.0,
            "zmax": max(zflat) if zflat else 1.0,
            "cmap": _colormaps.get_cmap(cmap),
            "label": label,
        })
        return self

    def bar3d(self, x, y, z, dx, dy, dz, *, color=None, label: str | None = None) -> "Axes3D":
        """Draw 3D bars (boxes): base corners ``(x, y, z)`` with sizes
        ``(dx, dy, dz)`` (each a scalar or per-bar array)."""
        xs = [float(v) for v in x]
        n = len(xs)
        self._marks3.append({
            "kind": "bar3d", "xs": xs, "ys": [float(v) for v in y],
            "zs": [float(v) for v in z], "dx": _as_seq(dx, n), "dy": _as_seq(dy, n),
            "dz": _as_seq(dz, n), "color": self._next_color(color), "label": label,
        })
        return self

    def plot_wireframe(self, X, Y, Z, *, color=None, linewidth: float = 0.8) -> "Axes3D":
        """Draw the grid ``(X, Y, Z)`` as a wireframe (row + column lines)."""
        gx, gy, gz, nr, nc = _grid_xyz(X, Y, Z)
        self._marks3.append({
            "kind": "wireframe", "gx": gx, "gy": gy, "gz": gz, "nr": nr, "nc": nc,
            "xflat": [v for row in gx for v in row],
            "yflat": [v for row in gy for v in row],
            "zflat": [v for row in gz for v in row],
            "color": self._next_color(color), "width": float(linewidth),
        })
        return self

    def contour3d(self, X, Y, Z, *, levels=None, cmap="viridis",
                  linewidth: float = 1.5) -> "Axes3D":
        """Draw contour lines of the grid ``(X, Y, Z)`` at their z-heights
        (marching squares in Rust); each level colored from ``cmap``."""
        gx, gy, gz, nr, nc = _grid_xyz(X, Y, Z)
        flat = [v for row in gz for v in row]
        lvls = _auto_levels(flat, levels)
        segs = _core.contour_lines(flat, nc, nr, lvls)
        cm = _colormaps.get_cmap(cmap)
        lo, hi = (min(lvls), max(lvls)) if lvls else (0.0, 1.0)
        span = (hi - lo) or 1.0
        colors = [cm((lv - lo) / span) for lv in lvls]
        self._marks3.append({
            "kind": "contour3d", "segs": segs, "gx": gx, "gy": gy, "levels": lvls,
            "colors": colors, "width": float(linewidth),
            "xflat": [v for row in gx for v in row],
            "yflat": [v for row in gy for v in row], "zflat": flat,
        })
        return self

    def plot_trisurf(self, x, y, z, *, triangles=None, cmap="viridis",
                     label: str | None = None) -> "Axes3D":
        """Surface over scattered points ``(x, y, z)``: Delaunay-triangulate the
        ``(x, y)`` plane (unless ``triangles`` index-triples are given) and shade
        each facet by mean z."""
        xs = [float(v) for v in x]
        ys = [float(v) for v in y]
        zs = [float(v) for v in z]
        tris = triangles if triangles is not None else _delaunay(list(zip(xs, ys)))
        self._marks3.append({
            "kind": "trisurf", "xs": xs, "ys": ys, "zs": zs,
            "tris": [tuple(t) for t in tris], "cmap": _colormaps.get_cmap(cmap),
            "zmin": min(zs) if zs else 0.0, "zmax": max(zs) if zs else 1.0,
            "xflat": xs, "yflat": ys, "zflat": zs, "label": label,
        })
        return self

    def quiver3d(self, x, y, z, u, v, w, *, length: float = 1.0, color=None,
                 linewidth: float = 1.5) -> "Axes3D":
        """Draw 3D arrows ``(u, v, w)`` rooted at ``(x, y, z)``, scaled by
        ``length``."""
        self._marks3.append({
            "kind": "quiver3d", "xs": [float(v) for v in x], "ys": [float(v) for v in y],
            "zs": [float(v) for v in z], "us": [float(v) for v in u],
            "vs": [float(v) for v in v], "ws": [float(v) for v in w],
            "length": float(length), "color": self._next_color(color), "width": float(linewidth),
        })
        # Autoscale should include arrow tips.
        self._marks3[-1]["xflat"] = [px + length * uu for px, uu in
                                     zip(self._marks3[-1]["xs"], self._marks3[-1]["us"])] + self._marks3[-1]["xs"]
        self._marks3[-1]["yflat"] = [py + length * vv for py, vv in
                                     zip(self._marks3[-1]["ys"], self._marks3[-1]["vs"])] + self._marks3[-1]["ys"]
        self._marks3[-1]["zflat"] = [pz + length * ww for pz, ww in
                                     zip(self._marks3[-1]["zs"], self._marks3[-1]["ws"])] + self._marks3[-1]["zs"]
        return self

    def voxels(self, filled, *, color=None, edgecolor=None) -> "Axes3D":
        """Draw a 3D boolean occupancy grid ``filled[i][j][k]`` as unit cubes."""
        color = self._next_color(color)
        cells = []
        for i, plane in enumerate(filled):
            for j, row in enumerate(plane):
                for k, on in enumerate(row):
                    if on:
                        cells.append((i, j, k))
        self._marks3.append({
            "kind": "voxels", "cells": cells, "color": color,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
            "xflat": [0.0] + [c[0] + 1 for c in cells],
            "yflat": [0.0] + [c[1] + 1 for c in cells],
            "zflat": [0.0] + [c[2] + 1 for c in cells],
        })
        return self

    # matplotlib-style aliases.
    scatter3d = scatter
    plot3d = plot

    def set(self, *, title=None, xlabel=None, ylabel=None, zlabel=None,
            xlim=None, ylim=None, zlim=None, elev=None, azim=None) -> "Axes3D":
        if title is not None:
            self._title = title
        if xlabel is not None:
            self._xlabel = xlabel
        if ylabel is not None:
            self._ylabel = ylabel
        if zlabel is not None:
            self._zlabel = zlabel
        if xlim is not None:
            self._xlim = (float(xlim[0]), float(xlim[1]))
        if ylim is not None:
            self._ylim = (float(ylim[0]), float(ylim[1]))
        if zlim is not None:
            self._zlim = (float(zlim[0]), float(zlim[1]))
        if elev is not None:
            self._elev = float(elev)
        if azim is not None:
            self._azim = float(azim)
        return self

    # -- Figure protocol ----------------------------------------------------

    def _ranges(self):
        # 3D axes don't participate in 2D shared-range unification.
        return ((0.0, 1.0), (0.0, 1.0))

    def _bands(self, scene, xr, yr):
        title_h = 0.0
        if self._title:
            a, d = _th(scene, self._title, self._theme.title_size)
            title_h = a + d + _TITLE_GAP
        return (title_h, 0.0, 0.0, 0.0, 0.0, 0.0), [], []

    def _limits(self):
        xs: list[float] = []
        ys: list[float] = []
        zs: list[float] = []
        for m in self._marks3:
            k = m["kind"]
            if k in ("scatter", "line"):
                xs += m["xs"]
                ys += m["ys"]
                zs += m["zs"]
            elif k == "bar3d":
                xs += m["xs"] + [a + b for a, b in zip(m["xs"], m["dx"])]
                ys += m["ys"] + [a + b for a, b in zip(m["ys"], m["dy"])]
                zs += m["zs"] + [a + b for a, b in zip(m["zs"], m["dz"])]
            elif k == "voxels":
                for i, j, kk in m["cells"]:
                    xs += [i, i + 1]
                    ys += [j, j + 1]
                    zs += [kk, kk + 1]
            elif "xflat" in m:
                xs += m["xflat"]
                ys += m["yflat"]
                zs += m["zflat"]
        if not xs:
            xs = ys = zs = [0.0, 1.0]
        xr = self._xlim or _data_range(xs)
        yr = self._ylim or _data_range(ys)
        zr = self._zlim or _data_range(zs)
        return xr, yr, zr

    def _draw(self, scene, layout, xr, yr, xticks, yticks) -> None:
        t = self._theme
        _TICK_LABEL_SIZE = t.tick_label_size
        _AXIS_LABEL_SIZE = t.axis_label_size
        _TITLE_SIZE = t.title_size
        _BLACK = t.text_color
        plot = layout.plot
        cam = _threed.Camera3D(self._elev, self._azim)
        (xmin, xmax), (ymin, ymax), (zmin, zmax) = self._limits()
        xspan = (xmax - xmin) or 1.0
        yspan = (ymax - ymin) or 1.0
        zspan = (zmax - zmin) or 1.0

        def norm(x, y, z):
            return ((x - xmin) / xspan - 0.5, (y - ymin) / yspan - 0.5, (z - zmin) / zspan - 0.5)

        # Fit the projected unit cube into the plot rect, preserving aspect.
        sxs, sys = [], []
        for c in _threed.CUBE_CORNERS:
            s = cam.view(c)
            sxs.append(s[0])
            sys.append(s[1])
        bw = (max(sxs) - min(sxs)) or 1.0
        bh = (max(sys) - min(sys)) or 1.0
        scale = min(plot.w / bw, plot.h / bh) * _CUBE_FILL
        ccx = plot.x + plot.w / 2.0
        ccy = plot.y + plot.h / 2.0
        scx = (min(sxs) + max(sxs)) / 2.0
        scy = (min(sys) + max(sys)) / 2.0

        def to_dev(sx, sy):
            return (ccx + (sx - scx) * scale, ccy - (sy - scy) * scale)

        def projn(p):
            s = cam.view(p)
            dx, dy = to_dev(s[0], s[1])
            return (dx, dy, s[2])

        def proj(x, y, z):
            return projn(norm(x, y, z))

        center_dev = to_dev(0.0, 0.0)

        def depth_n(p):
            return cam.view(p)[2]

        # Back walls = the farther plane of each axis-aligned pair (smaller depth).
        z_back = -0.5 if depth_n((0.0, 0.0, -0.5)) < depth_n((0.0, 0.0, 0.5)) else 0.5
        x_back = -0.5 if depth_n((-0.5, 0.0, 0.0)) < depth_n((0.5, 0.0, 0.0)) else 0.5
        y_back = -0.5 if depth_n((0.0, -0.5, 0.0)) < depth_n((0.0, 0.5, 0.0)) else 0.5

        def axis_ticks(vmin, vmax):
            span = (vmax - vmin) or 1.0
            out = []
            for val, lab in _core.nice_ticks(vmin, vmax, 5):
                frac = (val - vmin) / span
                if -1e-9 <= frac <= 1.0 + 1e-9:
                    out.append((frac - 0.5, lab))
            return out

        xt = axis_ticks(xmin, xmax)
        yt = axis_ticks(ymin, ymax)
        zt = axis_ticks(zmin, zmax)

        # 1. Back panes + gridlines.
        def quad(p0, p1, p2, p3, fill, stroke=None):
            pts = [projn(p0)[:2], projn(p1)[:2], projn(p2)[:2], projn(p3)[:2]]
            scene.add_path(pts, fill_color=fill, close=True, stroke_color=stroke,
                           stroke_width=0.8 if stroke else 1.0)

        def gridline(p0, p1):
            scene.add_path([projn(p0)[:2], projn(p1)[:2]], stroke_color=_GRID_3D, stroke_width=0.6)

        quad((-0.5, -0.5, z_back), (0.5, -0.5, z_back), (0.5, 0.5, z_back), (-0.5, 0.5, z_back),
             _PANE_FILL, _PANE_EDGE)
        for nx, _ in xt:
            gridline((nx, -0.5, z_back), (nx, 0.5, z_back))
        for ny, _ in yt:
            gridline((-0.5, ny, z_back), (0.5, ny, z_back))

        quad((x_back, -0.5, -0.5), (x_back, 0.5, -0.5), (x_back, 0.5, 0.5), (x_back, -0.5, 0.5),
             _PANE_FILL, _PANE_EDGE)
        for ny, _ in yt:
            gridline((x_back, ny, -0.5), (x_back, ny, 0.5))
        for nz, _ in zt:
            gridline((x_back, -0.5, nz), (x_back, 0.5, nz))

        quad((-0.5, y_back, -0.5), (0.5, y_back, -0.5), (0.5, y_back, 0.5), (-0.5, y_back, 0.5),
             _PANE_FILL, _PANE_EDGE)
        for nx, _ in xt:
            gridline((nx, y_back, -0.5), (nx, y_back, 0.5))
        for nz, _ in zt:
            gridline((-0.5, y_back, nz), (0.5, y_back, nz))

        # 2. Data marks: project every primitive to (depth, draw_fn) and paint
        #    them in one global back-to-front order so surfaces, lines, bars and
        #    points that interpenetrate occlude each other correctly (a single
        #    depth sort across all marks, not per-mark).
        prims: list[tuple[float, "callable"]] = []

        def add_poly(pts3, fill, stroke=None, sw=1.0):
            if len(pts3) < 3:
                return
            depth = sum(p[2] for p in pts3) / len(pts3)
            dev = [(p[0], p[1]) for p in pts3]
            prims.append((depth, lambda: scene.add_path(
                dev, fill_color=fill, close=True, stroke_color=stroke,
                stroke_width=sw if stroke else 1.0)))

        def add_seg(a3, b3, color, w, dash=None):
            prims.append(((a3[2] + b3[2]) / 2.0, lambda: scene.add_path(
                [(a3[0], a3[1]), (b3[0], b3[1])], stroke_color=color,
                stroke_width=w, cap="round", join="round", dash=dash)))

        def add_point(p3, d, marker, fc, ec):
            prims.append((p3[2], lambda: _draw_marker(
                scene, p3[0], p3[1], d, marker, facecolor=fc, edgecolor=ec)))

        def box_faces(x0, y0, z0, x1, y1, z1, fill, edge):
            c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                 (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
            cp = [proj(*v) for v in c]
            for a, b, cc, dd in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
                                 (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)):
                add_poly([cp[a], cp[b], cp[cc], cp[dd]], fill, edge, 0.6)

        for m in self._marks3:
            k = m["kind"]
            if k == "surface":
                gx, gy, gz = m["gx"], m["gy"], m["gz"]
                zmin, zmax, cm = m["zmin"], m["zmax"], m["cmap"]
                zspd = (zmax - zmin) or 1.0
                for r in range(m["nr"] - 1):
                    for cc in range(m["nc"] - 1):
                        corners = [proj(gx[r][cc], gy[r][cc], gz[r][cc]),
                                   proj(gx[r][cc + 1], gy[r][cc + 1], gz[r][cc + 1]),
                                   proj(gx[r + 1][cc + 1], gy[r + 1][cc + 1], gz[r + 1][cc + 1]),
                                   proj(gx[r + 1][cc], gy[r + 1][cc], gz[r + 1][cc])]
                        zc = (gz[r][cc] + gz[r][cc + 1] + gz[r + 1][cc + 1] + gz[r + 1][cc]) / 4.0
                        add_poly(corners, cm((zc - zmin) / zspd), None, 1.0)
            elif k == "trisurf":
                cm, zmin, zmax = m["cmap"], m["zmin"], m["zmax"]
                zspd = (zmax - zmin) or 1.0
                for a, b, cc in m["tris"]:
                    pa = proj(m["xs"][a], m["ys"][a], m["zs"][a])
                    pb = proj(m["xs"][b], m["ys"][b], m["zs"][b])
                    pc = proj(m["xs"][cc], m["ys"][cc], m["zs"][cc])
                    zc = (m["zs"][a] + m["zs"][b] + m["zs"][cc]) / 3.0
                    add_poly([pa, pb, pc], cm((zc - zmin) / zspd),
                             _WHITE, 0.4)
            elif k == "line":
                pr = [proj(x, y, z) for x, y, z in zip(m["xs"], m["ys"], m["zs"])]
                for i in range(len(pr) - 1):
                    add_seg(pr[i], pr[i + 1], m["color"], m["width"],
                            _dash_for(m["linestyle"]))
            elif k == "wireframe":
                gx, gy, gz = m["gx"], m["gy"], m["gz"]
                grid = [[proj(gx[r][c], gy[r][c], gz[r][c]) for c in range(m["nc"])]
                        for r in range(m["nr"])]
                for r in range(m["nr"]):
                    for c in range(m["nc"] - 1):
                        add_seg(grid[r][c], grid[r][c + 1], m["color"], m["width"])
                for c in range(m["nc"]):
                    for r in range(m["nr"] - 1):
                        add_seg(grid[r][c], grid[r + 1][c], m["color"], m["width"])
            elif k == "contour3d":
                gx, gy = m["gx"], m["gy"]
                for li, x0, y0, x1, y1 in m["segs"]:
                    lv = m["levels"][li]
                    a = proj(_bilinear_grid(gx, y0, x0), _bilinear_grid(gy, y0, x0), lv)
                    b = proj(_bilinear_grid(gx, y1, x1), _bilinear_grid(gy, y1, x1), lv)
                    add_seg(a, b, m["colors"][li] if li < len(m["colors"]) else m["colors"][-1],
                            m["width"])
            elif k == "bar3d":
                for i in range(len(m["xs"])):
                    box_faces(m["xs"][i], m["ys"][i], m["zs"][i],
                              m["xs"][i] + m["dx"][i], m["ys"][i] + m["dy"][i],
                              m["zs"][i] + m["dz"][i], m["color"], _darker(m["color"]))
            elif k == "voxels":
                for i, j, kk in m["cells"]:
                    box_faces(float(i), float(j), float(kk), i + 1.0, j + 1.0, kk + 1.0,
                              m["color"], m["edgecolor"] or _darker(m["color"]))
            elif k == "quiver3d":
                L = m["length"]
                for i in range(len(m["xs"])):
                    base = proj(m["xs"][i], m["ys"][i], m["zs"][i])
                    tip = proj(m["xs"][i] + L * m["us"][i], m["ys"][i] + L * m["vs"][i],
                               m["zs"][i] + L * m["ws"][i])
                    add_seg(base, tip, m["color"], m["width"])
                    add_point(tip, 3.0, "o", m["color"], None)
            elif k == "scatter":
                d = m["markersize"]
                for x, y, z in zip(m["xs"], m["ys"], m["zs"]):
                    add_point(proj(x, y, z), d, m["marker"], m["color"], m["edgecolor"])

        prims.sort(key=lambda p: p[0])  # back (small depth) to front
        for _depth, draw in prims:
            draw()

        # 3. Tick labels + axis labels (on top, offset radially outward).
        def place(anchor, text, size, outward):
            dx, dy, _ = projn(anchor)
            vx, vy = dx - center_dev[0], dy - center_dev[1]
            vlen = math.hypot(vx, vy) or 1.0
            dx += vx / vlen * outward
            dy += vy / vlen * outward
            tw = _tw(scene, text, size)
            a, dd, _ = scene.font_vmetrics(size)
            _text(scene, dx - tw / 2.0, dy + (a - dd) / 2.0, text, size, _BLACK)

        # x/y tick labels along the bottom-front edges; z along the leftmost edge.
        x_edge_y = max((-0.5, 0.5), key=lambda yy: projn((0.0, yy, z_back))[1])
        y_edge_x = max((-0.5, 0.5), key=lambda xx: projn((xx, 0.0, z_back))[1])
        z_edge = min(((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)),
                     key=lambda c: projn((c[0], c[1], 0.0))[0])

        for nx, lab in xt:
            place((nx, x_edge_y, z_back), lab, _TICK_LABEL_SIZE, 9.0)
        for ny, lab in yt:
            place((y_edge_x, ny, z_back), lab, _TICK_LABEL_SIZE, 9.0)
        for nz, lab in zt:
            place((z_edge[0], z_edge[1], nz), lab, _TICK_LABEL_SIZE, 9.0)

        if self._xlabel:
            place((0.0, x_edge_y, z_back), self._xlabel, _AXIS_LABEL_SIZE, 26.0)
        if self._ylabel:
            place((y_edge_x, 0.0, z_back), self._ylabel, _AXIS_LABEL_SIZE, 26.0)
        if self._zlabel:
            place((z_edge[0], z_edge[1], 0.0), self._zlabel, _AXIS_LABEL_SIZE, 30.0)

        # Title in its reserved band.
        title_font = _font(t.title_weight)
        label_font = _font(t.axis_label_weight)
        if self._title:
            a, _d = _th(scene, self._title, _TITLE_SIZE, title_font)
            tw = _tw(scene, self._title, _TITLE_SIZE, title_font)
            _text(scene, plot.x + (plot.w - tw) / 2.0, layout.title.y + a, self._title,
                  _TITLE_SIZE, _BLACK, title_font)

        # Auto-legend for labelled line/scatter marks, inset in the plot rect.
        if self._legend is not None:
            entries = self._legend_entries()
            if entries:
                box_w, box_h, mt = _measure_legend(scene, entries, self._theme)
                inset = 6.0
                px, py, pw, ph = plot.x, plot.y, plot.w, plot.h
                corners = {
                    "upper right": (px + pw - inset - box_w, py + inset),
                    "upper left": (px + inset, py + inset),
                    "lower right": (px + pw - inset - box_w, py + ph - inset - box_h),
                    "lower left": (px + inset, py + ph - inset - box_h),
                }
                bx, by = corners.get(self._legend["loc"], corners["upper right"])
                _draw_legend_box(scene, entries, bx, by, mt)

    def _draw_surface(self, scene, m: dict, proj) -> None:
        gx, gy, gz = m["gx"], m["gy"], m["gz"]
        nr, nc = m["nr"], m["nc"]
        cm = m["cmap"]
        zmin, zspan = m["zmin"], (m["zmax"] - m["zmin"]) or 1.0
        faces = []
        for i in range(nr - 1):
            for j in range(nc - 1):
                p00 = proj(gx[i][j], gy[i][j], gz[i][j])
                p01 = proj(gx[i][j + 1], gy[i][j + 1], gz[i][j + 1])
                p11 = proj(gx[i + 1][j + 1], gy[i + 1][j + 1], gz[i + 1][j + 1])
                p10 = proj(gx[i + 1][j], gy[i + 1][j], gz[i + 1][j])
                depth = (p00[2] + p01[2] + p11[2] + p10[2]) / 4.0
                zc = (gz[i][j] + gz[i][j + 1] + gz[i + 1][j + 1] + gz[i + 1][j]) / 4.0
                color = cm((zc - zmin) / zspan)
                faces.append((depth, [p00[:2], p01[:2], p11[:2], p10[:2]], color))
        faces.sort(key=lambda f: f[0])  # back to front
        for _, pts, color in faces:
            scene.add_path(pts, fill_color=color, close=True, stroke_color=color, stroke_width=0.4)

    def _interactive_payload(self) -> dict:
        """Serialize this 3D axes into a JSON-able dict for the in-browser
        renderer (``_html3d``). Coordinates are pre-normalized into the
        ``[-0.5, 0.5]^3`` cube (same as :meth:`_draw`'s ``norm``) so the camera
        is all the JS has to apply; surface face colours are pre-sampled from the
        colormap (depth/order are recomputed per frame). Ticks and theme colours
        come along so the page reproduces the static look."""
        (xmin, xmax), (ymin, ymax), (zmin, zmax) = self._limits()
        xspan, yspan, zspan = (xmax - xmin) or 1.0, (ymax - ymin) or 1.0, (zmax - zmin) or 1.0

        def nrm(x, y, z):
            return [(x - xmin) / xspan - 0.5, (y - ymin) / yspan - 0.5, (z - zmin) / zspan - 0.5]

        def ticks(vmin, vmax):
            span = (vmax - vmin) or 1.0
            out = []
            for val, lab in _core.nice_ticks(vmin, vmax, 5):
                frac = (val - vmin) / span
                if -1e-9 <= frac <= 1.0 + 1e-9:
                    out.append([frac - 0.5, lab])
            return out

        marks: list[dict] = []
        for m in self._marks3:
            if m["kind"] == "scatter":
                marks.append({
                    "kind": "scatter",
                    "pts": [nrm(x, y, z) for x, y, z in zip(m["xs"], m["ys"], m["zs"])],
                    "color": list(m["color"]),
                    "edgecolor": list(m["edgecolor"]) if m["edgecolor"] else None,
                    "d": m["markersize"],
                    "marker": m["marker"],
                })
            elif m["kind"] == "line":
                marks.append({
                    "kind": "line",
                    "pts": [nrm(x, y, z) for x, y, z in zip(m["xs"], m["ys"], m["zs"])],
                    "color": list(m["color"]),
                    "width": m["width"],
                    "dash": _dash_for(m["linestyle"]),
                })
            elif m["kind"] == "surface":
                gx, gy, gz, nr, nc = m["gx"], m["gy"], m["gz"], m["nr"], m["nc"]
                cm = m["cmap"]
                zmn, zsp = m["zmin"], (m["zmax"] - m["zmin"]) or 1.0
                verts = [nrm(gx[i][j], gy[i][j], gz[i][j]) for i in range(nr) for j in range(nc)]
                facecolors = []
                for i in range(nr - 1):
                    for j in range(nc - 1):
                        zc = (gz[i][j] + gz[i][j + 1] + gz[i + 1][j + 1] + gz[i + 1][j]) / 4.0
                        r, g, b, _a = cm((zc - zmn) / zsp)
                        facecolors.append([r, g, b])
                marks.append({"kind": "surface", "nr": nr, "nc": nc,
                              "verts": verts, "facecolors": facecolors})

        legend = None
        if self._legend is not None:
            entries = self._legend_entries()
            if entries:
                legend = {
                    "loc": self._legend.get("loc", "upper right"),
                    "entries": [{
                        "kind": e["kind"], "label": e["label"], "color": list(e["color"]),
                        "marker": e.get("marker"),
                        "dash": _dash_for(e.get("linestyle", "solid")),
                    } for e in entries],
                }

        t = self._theme
        return {
            "title": self._title, "xlabel": self._xlabel,
            "ylabel": self._ylabel, "zlabel": self._zlabel,
            "elev": self._elev, "azim": self._azim,
            "xticks": ticks(xmin, xmax), "yticks": ticks(ymin, ymax), "zticks": ticks(zmin, zmax),
            "marks": marks, "legend": legend,
            "theme": {
                "grid": list(_GRID_3D), "pane_fill": list(_PANE_FILL), "pane_edge": list(_PANE_EDGE),
                "text": list(t.text_color), "tick_size": t.tick_label_size,
                "axis_size": t.axis_label_size, "title_size": t.title_size, "cube_fill": _CUBE_FILL,
            },
        }


def _theta_zero(loc) -> float:
    """Resolve a ``theta_zero_location`` to the angle (radians) drawn at
    ``theta == 0``. Accepts a number (radians) or ``"E"``/``"N"``/``"W"``/``"S"``."""
    if isinstance(loc, (int, float)):
        return float(loc)
    return {"E": 0.0, "N": math.pi / 2.0, "W": math.pi, "S": -math.pi / 2.0}.get(
        str(loc).upper(), 0.0)


class PolarAxes(_AxesBase):
    """A polar axes: ``plot(theta, r)`` and ``scatter(theta, r)``.

    Angles are in **radians**, measured counter-clockwise from the positive
    x-axis (East), matching matplotlib's default; change this with
    ``set(theta_zero_location=...)`` / ``set(theta_direction=...)``. Create one
    with ``subplots(projection="polar")`` or ``add_subplot(spec,
    projection="polar")``.
    """

    # A polar plot fills its cell; no corner search is meaningful.
    _LEGEND_DEFAULT_LOC = "upper right"

    def __init__(self, theme: Theme | None = None) -> None:
        self._init_common(theme)
        self._marks: list[dict] = []
        self._xlabel: str | None = None  # kept for _accessible_text() compatibility
        self._ylabel: str | None = None
        self._rmin = 0.0
        self._rmax: float | None = None
        self._rticks: list[float] | None = None
        self._thetagrids_deg: list[float] | None = None  # spoke angles, degrees
        self._theta_offset = 0.0  # angle (rad) drawn at theta == 0
        self._theta_dir = 1  # +1 counter-clockwise (default), -1 clockwise
        self._rlabel_deg = 22.5  # angle (deg) along which radial labels sit

    # -- public API ---------------------------------------------------------

    def plot(self, theta, r, *, label: str | None = None, color=None,
             linewidth: float | None = None, alpha: float = 1.0,
             linestyle: str = "solid",
             marker: str | None = None, markersize: float = 5.0) -> "PolarAxes":
        """Line through polar points ``(theta, r)`` (``theta`` in radians)."""
        self._marks.append({
            "kind": "line",
            "theta": [float(t) for t in theta],
            "r": [float(v) for v in r],
            "label": label,
            "color": self._mark_color(color, alpha),
            "width": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle,
            "marker": marker,
            "markersize": float(markersize),
        })
        return self

    def scatter(self, theta, r, *, label: str | None = None, color=None,
                markersize: float | None = None, alpha: float = 1.0,
                marker: str = "o", edgecolor=None,
                size: float | None = None) -> "PolarAxes":
        """Scatter polar points ``(theta, r)`` (``theta`` in radians).

        ``markersize`` is a diameter in points; ``size`` is the matplotlib-style
        area in pt² (see :meth:`Axes.scatter`)."""
        self._marks.append({
            "kind": "scatter",
            "theta": [float(t) for t in theta],
            "r": [float(v) for v in r],
            "label": label,
            "color": self._mark_color(color, alpha),
            "markersize": self._marker_diameter(markersize, size),
            "marker": marker,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
        })
        return self

    def set(self, *, title=None, rmin=None, rmax=None, rticks=None, thetagrids=None,
            theta_zero_location=None, theta_direction=None,
            rlabel_position=None) -> "PolarAxes":
        """Set polar options: ``title``; radial limits ``rmin``/``rmax``; explicit
        ``rticks`` (radii) and ``thetagrids`` (spoke angles, degrees); the zero
        location (``"E"``/``"N"``/``"W"``/``"S"`` or radians); the ``theta_direction``
        (``1`` counter-clockwise or ``-1`` clockwise); and ``rlabel_position`` (the
        angle in degrees along which radial tick labels are placed)."""
        if title is not None:
            self._title = title
        if rmin is not None:
            self._rmin = float(rmin)
        if rmax is not None:
            self._rmax = float(rmax)
        if rticks is not None:
            self._rticks = [float(v) for v in rticks]
        if thetagrids is not None:
            self._thetagrids_deg = [float(v) for v in thetagrids]
        if theta_zero_location is not None:
            self._theta_offset = _theta_zero(theta_zero_location)
        if theta_direction is not None:
            self._theta_dir = -1 if theta_direction in (-1, "clockwise", "cw") else 1
        if rlabel_position is not None:
            self._rlabel_deg = float(rlabel_position)
        return self

    # matplotlib-style convenience setters (thin wrappers over set()).
    def set_title(self, title: str) -> "PolarAxes":
        return self.set(title=title)

    def set_rmax(self, rmax: float) -> "PolarAxes":
        return self.set(rmax=rmax)

    def set_rlim(self, rmin: float, rmax: float) -> "PolarAxes":
        return self.set(rmin=rmin, rmax=rmax)

    def set_rticks(self, rticks) -> "PolarAxes":
        return self.set(rticks=rticks)

    def set_thetagrids(self, angles) -> "PolarAxes":
        return self.set(thetagrids=angles)

    def set_theta_zero_location(self, loc) -> "PolarAxes":
        return self.set(theta_zero_location=loc)

    def set_theta_direction(self, direction) -> "PolarAxes":
        return self.set(theta_direction=direction)

    # -- drawing contract (mirrors Axes / Axes3D) ---------------------------

    def _rlimits(self) -> tuple[float, float]:
        rs = [v for m in self._marks for v in m["r"]]
        rmax = self._rmax if self._rmax is not None else (max(rs) if rs else 1.0)
        rmin = self._rmin
        if rmax <= rmin:
            rmax = rmin + 1.0
        return rmin, rmax

    def _ranges(self):
        # Polar opts out of 2D shared-range unification.
        return ((0.0, 1.0), (0.0, 1.0))

    def _bands(self, scene, xr, yr):
        title_h = 0.0
        if self._title:
            a, d = _th(scene, self._title, self._theme.title_size)
            title_h = a + d + _TITLE_GAP
        return (title_h, 0.0, 0.0, 0.0, 0.0, 0.0), [], []

    def _draw(self, scene, layout, xr, yr, xticks, yticks) -> None:
        t = self._theme
        plot = layout.plot
        # Reserve a ring inside the plot rect for the theta tick labels drawn just
        # outside the outer circle, so the whole dial fits the cell.
        label_pad = t.tick_label_size * 1.7
        cx = plot.x + plot.w / 2.0
        cy = plot.y + plot.h / 2.0
        R = max(1.0, min(plot.w, plot.h) / 2.0 - label_pad)
        rmin, rmax = self._rlimits()
        rspan = (rmax - rmin) or 1.0

        def to_dev(theta, r):
            a = self._theta_offset + self._theta_dir * theta
            rr = (r - rmin) / rspan * R
            # Screen y grows downward, so negate sin to keep angles counter-clockwise.
            return (cx + rr * math.cos(a), cy - rr * math.sin(a))

        spokes = (self._thetagrids_deg if self._thetagrids_deg is not None
                  else [i * 45.0 for i in range(8)])
        if self._rticks is not None:
            rgrid = [(v, f"{v:g}") for v in self._rticks]
        else:
            rgrid = list(_core.nice_ticks(rmin, rmax, 5))
        rgrid = [(v, lab) for (v, lab) in rgrid if rmin < v <= rmax + 1e-9]

        # 1. Radial spokes (theta gridlines) from the centre to the rim.
        for deg in spokes:
            x1, y1 = to_dev(math.radians(deg), rmax)
            scene.add_path([(cx, cy), (x1, y1)], stroke_color=t.grid_color,
                           stroke_width=t.grid_width)
        # 2. Concentric r-circles at each radial tick.
        for rv, _lab in rgrid:
            pts = [to_dev(2.0 * math.pi * k / 96.0, rv) for k in range(97)]
            scene.add_path(pts, stroke_color=t.grid_color, stroke_width=t.grid_width)
        # 3. Outer spine circle at rmax.
        rim = [to_dev(2.0 * math.pi * k / 128.0, rmax) for k in range(129)]
        scene.add_path(rim, stroke_color=_SPINE, stroke_width=1.0)

        # 4. Theta tick labels just outside the rim, centred on their spoke.
        for deg in spokes:
            a = self._theta_offset + self._theta_dir * math.radians(deg)
            lx = cx + (R + label_pad * 0.4) * math.cos(a)
            ly = cy - (R + label_pad * 0.4) * math.sin(a)
            lab = f"{deg:g}°"
            w = _tw(scene, lab, t.tick_label_size)
            asc, desc = _th(scene, lab, t.tick_label_size)
            _text(scene, lx - w / 2.0, ly + (asc - desc) / 2.0, lab,
                  t.tick_label_size, t.text_color)
        # 5. Radial tick labels along the rlabel spoke.
        ra = self._theta_offset + self._theta_dir * math.radians(self._rlabel_deg)
        for rv, lab in rgrid:
            rr = (rv - rmin) / rspan * R
            lx = cx + rr * math.cos(ra) + 2.0
            ly = cy - rr * math.sin(ra)
            _text(scene, lx, ly, lab, t.tick_label_size, t.text_color)

        # 6. Data marks, projected through the polar map.
        for m in self._marks:
            dev = [to_dev(th, rv) for th, rv in zip(m["theta"], m["r"])]
            if m["kind"] == "line":
                if _draws_line(m["linestyle"]) and len(dev) >= 2:
                    scene.add_path(dev, stroke_color=m["color"], stroke_width=m["width"],
                                   dash=_dash_for(m["linestyle"]), cap="round", join="round")
                if m.get("marker"):
                    for x, y in dev:
                        _draw_marker(scene, x, y, m["markersize"], m["marker"], m["color"])
            else:  # scatter
                d = m["markersize"]
                for x, y in dev:
                    _draw_marker(scene, x, y, d, m["marker"], m["color"],
                                 edgecolor=m["edgecolor"])

        # 7. Title in its reserved band.
        if self._title:
            a, _d = _th(scene, self._title, t.title_size)
            tw = _tw(scene, self._title, t.title_size)
            _text(scene, plot.x + (plot.w - tw) / 2.0, layout.title.y + a, self._title,
                  t.title_size, t.text_color)

        # 8. Auto-legend for labelled marks, inset in the plot rect.
        if self._legend is not None:
            entries = self._legend_entries()
            if entries:
                box_w, box_h, mt = _measure_legend(scene, entries, t)
                inset = 6.0
                px, py, pw, ph = plot.x, plot.y, plot.w, plot.h
                corners = {
                    "upper right": (px + pw - inset - box_w, py + inset),
                    "upper left": (px + inset, py + inset),
                    "lower right": (px + pw - inset - box_w, py + ph - inset - box_h),
                    "lower left": (px + inset, py + ph - inset - box_h),
                }
                bx, by = corners.get(self._legend["loc"], corners["upper right"])
                _draw_legend_box(scene, entries, bx, by, mt)


def _axes_class(projection: str | None):
    """Resolve a ``projection`` string to the axes class that implements it."""
    if projection == "3d":
        return Axes3D
    if projection == "polar":
        return PolarAxes
    return Axes


class Figure:
    """A figure: an output canvas holding a grid of [`Axes`].

    ``figsize`` is the ``(width, height)`` of the canvas in **points** by default
    (``units="pt"``). Sizing in points lets you reason about a plot directly
    against its font scale — e.g. a 480x360 pt figure with a 10 pt font. Pass
    ``units="in"``, ``"cm"`` or ``"mm"`` to give the size in another unit (a
    single journal column is ~252 pt; Nature's widths are 89 mm / 183 mm).
    """

    def __init__(self, figsize: tuple[float, float] = (480, 360), nrows: int = 1,
                 ncols: int = 1, sharex: bool = False, sharey: bool = False,
                 projection: str | None = None, theme=None, units: str = "pt",
                 width_ratios=None, height_ratios=None) -> None:
        self.figsize = figsize          # raw, as given (back-compat / repr)
        self.units = units
        self.size_pt = _figsize_to_points(figsize, units)  # resolved, canonical
        self.nrows = nrows
        self.ncols = ncols
        self.sharex = sharex
        self.sharey = sharey
        self.theme: Theme = _theme.get(theme)
        self.suptitle: str | None = None
        self._legend: dict | None = None
        # Relative column widths / row heights. Normalised in the Rust solver, so
        # only the proportions matter; `None` means an even grid.
        self._width_ratios = None if width_ratios is None else [float(v) for v in width_ratios]
        self._height_ratios = (
            None if height_ratios is None else [float(v) for v in height_ratios])
        make = _axes_class(projection)
        self.axes = [make(self.theme) for _ in range(nrows * ncols)]
        # Spanning placement (GridSpec / subplot_mosaic): one
        # (row, col, rowspan, colspan) per axes, or None for a uniform grid.
        self._spans: list[tuple[int, int, int, int]] | None = None

    def set(self, *, suptitle: str | None = None) -> "Figure":
        if suptitle is not None:
            self.suptitle = suptitle
        return self

    def add_gridspec(self, nrows: int, ncols: int, *,
                     width_ratios=None, height_ratios=None) -> "GridSpec":
        """Switch this figure to spanning-subplot mode over an ``nrows`` x
        ``ncols`` grid and return a :class:`GridSpec`. Populate it with
        :meth:`add_subplot`; existing auto-created axes are cleared.

        ``width_ratios``/``height_ratios`` weight the columns and rows (see
        :func:`subplots`)."""
        self.nrows = nrows
        self.ncols = ncols
        self.axes = []
        self._spans = []
        if width_ratios is not None:
            self._width_ratios = [float(v) for v in width_ratios]
        if height_ratios is not None:
            self._height_ratios = [float(v) for v in height_ratios]
        return GridSpec(nrows, ncols)

    def add_subplot(self, spec, *, projection: str | None = None) -> "Axes":
        """Add an axes at a :class:`GridSpec` slice (e.g. ``gs[0, :]`` or
        ``gs[1:, 0]``). Returns the new axes."""
        if self._spans is None:
            self._spans = []
        r0, c0, rs, cs = spec
        ax = _axes_class(projection)(self.theme)
        self.axes.append(ax)
        self._spans.append((r0, c0, rs, cs))
        return ax

    def _has_3d(self) -> bool:
        """True if any axes is a 3D axes (a figure's axes are homogeneous)."""
        return any(isinstance(ax, Axes3D) for ax in self.axes)

    def legend(self, *, loc: str = "right") -> "Figure":
        """Enable a single figure-level legend, collecting the labeled marks of
        every axes into one box placed in a reserved column to the right of the
        grid. Unlike :meth:`Axes.legend`, this is laid out as its own region and
        so can never overlap the data. ``loc`` currently supports ``"right"``."""
        self._legend = {"loc": loc}
        return self

    def _figure_legend_entries(self) -> list[dict]:
        """Labelled marks across every axes, de-duplicated by label so a series
        shared between panels appears once in the figure legend.

        Routed through each axes' own ``_legend_entries``, so 3D and polar
        panels contribute too - they used to be skipped because this read
        ``_marks`` directly and 3D keeps its marks in ``_marks3``."""
        entries: list[dict] = []
        seen: set[str] = set()
        for ax in self.axes:
            for m in ax._legend_entries():
                if m["label"] not in seen:
                    seen.add(m["label"])
                    entries.append(m)
        return entries

    def colorbar(self, mappable: "_Mappable", *, label: str | None = None) -> "Figure":
        """Attach a colorbar for ``mappable`` (from :meth:`Axes.imshow` or a
        colormapped :meth:`Axes.scatter`) in a reserved band to the right of its
        axes. The tick scale follows the mappable's ``norm`` (e.g. log ticks for
        a :class:`~pyplotrs.norms.LogNorm`)."""
        mappable.ax._colorbar = {
            "cmap": mappable.cmap,
            "vmin": mappable.vmin,
            "vmax": mappable.vmax,
            "label": label,
            "norm": mappable.norm,
        }
        return self

    def _build_scene(self, capture: list | None = None) -> "_core.Scene":
        width, height = self.size_pt
        scene = _core.Scene(width, height)
        if capture is not None:
            # Build through a proxy that records $...$ math runs (for MathJax
            # HTML) and drops their baked glyphs; everything else is unchanged.
            from ._htmlmath import _MathCapture
            scene = _MathCapture(scene, capture)

        # Per-axes data ranges, optionally unified for shared axes.
        ranges = [ax._ranges() for ax in self.axes]
        if self.sharex and ranges:
            xlo = min(r[0][0] for r in ranges)
            xhi = max(r[0][1] for r in ranges)
            ranges = [((xlo, xhi), r[1]) for r in ranges]
        if self.sharey and ranges:
            ylo = min(r[1][0] for r in ranges)
            yhi = max(r[1][1] for r in ranges)
            ranges = [(r[0], (ylo, yhi)) for r in ranges]

        # Measure bands + locate ticks for every axes (pre-layout).
        bands, xticks, yticks = [], [], []
        for ax, (xr, yr) in zip(self.axes, ranges):
            b, xt, yt = ax._bands(scene, xr, yr)
            bands.append(b)
            xticks.append(xt)
            yticks.append(yt)

        _SUPTITLE_SIZE = self.theme.suptitle_size
        suptitle_h = 0.0
        suptitle_font = _font(self.theme.suptitle_weight)
        if self.suptitle:
            a, d = _th(scene, self.suptitle, _SUPTITLE_SIZE, suptitle_font)
            suptitle_h = a + d + _TITLE_GAP * 1.5

        # Figure-level legend: measure its box up front so the layout can reserve
        # exactly the right-hand column it needs (never an overlay).
        fig_entries: list[dict] = []
        legend_mt: dict | None = None
        legend_w = 0.0
        if self._legend is not None:
            fig_entries = self._figure_legend_entries()
            if fig_entries:
                box_w, _box_h, legend_mt = _measure_legend(scene, fig_entries, self.theme)
                legend_w = _LEGEND_COL_GAP_L + box_w + _LEGEND_COL_GAP_R

        layout = _core.solve_layout(
            width, height, self.nrows, self.ncols, bands,
            outer_margin=_OUTER_MARGIN,
            hspace=_HSPACE if self.nrows > 1 else 0.0,
            wspace=_WSPACE if self.ncols > 1 else 0.0,
            suptitle_h=suptitle_h,
            legend_w=legend_w,
            spans=self._spans,
            width_ratios=self._width_ratios,
            height_ratios=self._height_ratios,
        )

        for ax, axl, (xr, yr), xt, yt in zip(self.axes, layout.axes, ranges, xticks, yticks):
            ax._draw(scene, axl, xr, yr, xt, yt)
            # Twin/secondary axes and insets overlay the host's cell.
            if getattr(ax, "_has_extras", lambda: False)():
                ax._draw_extras(scene, axl, xr, yr)

        if self.suptitle:
            a, _d = _th(scene, self.suptitle, _SUPTITLE_SIZE, suptitle_font)
            tw = _tw(scene, self.suptitle, _SUPTITLE_SIZE, suptitle_font)
            st = layout.suptitle
            _text(scene, st.x + (st.w - tw) / 2.0, st.y + a, self.suptitle,
                  _SUPTITLE_SIZE, self.theme.text_color, suptitle_font)

        if legend_mt is not None:
            lr = layout.legend
            bx = lr.x + _LEGEND_COL_GAP_L
            by = lr.y + max(0.0, (lr.h - legend_mt["box_h"]) / 2.0)
            _draw_legend_box(scene, fig_entries, bx, by, legend_mt)

        return scene

    def _accessible_text(self) -> tuple[str, str]:
        """A ``(title, alt)`` pair describing this figure for tagged PDF, derived
        from the suptitle and per-axes titles/labels when not given explicitly."""
        parts: list[str] = []
        if self.suptitle:
            parts.append(self.suptitle)
        for ax in self.axes:
            if getattr(ax, "_title", None):
                parts.append(ax._title)
            xl, yl = getattr(ax, "_xlabel", None), getattr(ax, "_ylabel", None)
            if xl and yl:
                parts.append(f"{yl} versus {xl}")
        title = self.suptitle or next((p for p in parts), "figure")
        alt = "; ".join(parts) if parts else "figure"
        return title, alt

    def _repr_png_(self) -> bytes:
        """Rich inline display in Jupyter/IPython: a bare ``fig`` in a notebook
        cell renders as a PNG (like matplotlib's inline backend). Works for 2D,
        polar and 3D figures alike (3D shows its projected static view; use
        ``save("*.html")`` for the interactive 3D viewer)."""
        return self._build_scene().to_png(_INLINE_DPI)

    def save(self, path: str, *, dpi: float = 200.0, tagged: bool = False,
             title: str | None = None, alt: str | None = None) -> None:
        """Save to ``path``; the format is inferred from the extension
        (``.pdf``, ``.svg``, ``.png``, or ``.html``/``.htm``).

        ``.html`` writes a single self-contained page with the figure inlined as
        vector SVG (real selectable text, embedded fonts, nothing fetched at view
        time) — handy for dropping a chart straight into a web page or report.
        If any label contains ``$...$`` **math**, that math is re-rendered by an
        inlined copy of **MathJax** (SVG output) so it is selectable and copyable
        as LaTeX/MathML (right-click → *Show Math As*); the page stays fully
        offline. For a **3D figure** the ``.html`` is instead a dependency-free
        Canvas2D viewer you can orbit (drag), zoom (scroll) and pan (shift-drag).

        ``dpi`` controls the resolution of raster (``.png``) output and is
        recorded in the file's physical-size metadata. PDF, SVG and HTML are
        resolution-independent and ignore it.

        ``tagged=True`` (``.pdf`` only) writes a tagged, accessible PDF: the
        whole chart becomes one ``Figure`` structure element with ``alt`` text
        (auto-derived from the titles/labels when omitted) so screen readers can
        announce it, plus a document ``title`` and language. For ``.html`` the
        same auto-derived ``title``/``alt`` label the page and the inline SVG
        (``role="img"``), and ``title``/``alt`` may be overridden here too."""
        path_str = str(path)
        ext = path_str.rsplit(".", 1)[-1].lower() if "." in path_str else ""
        if ext in ("html", "htm"):
            auto_title, auto_alt = self._accessible_text()
            if self._has_3d():
                from ._html3d import figure_to_interactive_html
                doc = figure_to_interactive_html(self, title or auto_title, alt or auto_alt)
            else:
                # Build through the capture proxy: if any label carries $...$,
                # render the math with MathJax (selectable/copyable, offline);
                # otherwise inline the baked-vector SVG as before.
                placements: list = []
                svg = self._build_scene(capture=placements).to_svg()
                if placements:
                    from ._htmlmath import figure_to_math_html
                    doc = figure_to_math_html(svg, placements, self.size_pt,
                                              title or auto_title, alt or auto_alt)
                else:
                    doc = _svg_to_html(svg, title or auto_title, alt or auto_alt)
            with open(path_str, "w", encoding="utf-8") as f:
                f.write(doc)
            return

        scene = self._build_scene()
        if ext == "pdf":
            if tagged:
                auto_title, auto_alt = self._accessible_text()
                data = scene.to_pdf(True, title or auto_title, alt or auto_alt)
            else:
                data = scene.to_pdf()
            with open(path_str, "wb") as f:
                f.write(data)
        elif ext == "svg":
            with open(path_str, "w", encoding="utf-8") as f:
                f.write(scene.to_svg())
        elif ext == "png":
            with open(path_str, "wb") as f:
                f.write(scene.to_png(dpi))
        else:
            raise ValueError(
                f"Unsupported file extension for {path_str!r}; "
                "expected .pdf, .svg, .png, or .html"
            )


def subplots(nrows: int = 1, ncols: int = 1, *, figsize: tuple[float, float] = (480, 360),
             sharex: bool = False, sharey: bool = False, projection: str | None = None,
             theme=None, units: str = "pt", width_ratios=None, height_ratios=None):
    """Create a [`Figure`] with an ``nrows`` x ``ncols`` grid of axes.

    ``figsize`` is the canvas ``(width, height)`` in **points** by default, so a
    plot is sized directly against its font scale; pass ``units="in"``, ``"cm"``
    or ``"mm"`` for another unit. ``projection="3d"`` makes every axes an
    [`Axes3D`]. ``theme`` is a [`Theme`] (or preset name like ``"nature"``); it
    flows to every axes. Returns ``(fig, ax)`` for a 1x1 grid,
    ``(fig, [ax, ...])`` when one dimension is 1, and ``(fig, [[ax, ...], ...])``
    otherwise (row-major).

    ``width_ratios`` / ``height_ratios`` give relative column widths and row
    heights, e.g. ``width_ratios=[2, 1]`` for a wide panel beside a narrow one.
    Only the proportions matter (``[2, 1]`` and ``[0.5, 0.25]`` are the same),
    and the gutters stay a fixed size - weighting changes the panels, not the
    space between them.
    """
    fig = Figure(figsize=figsize, nrows=nrows, ncols=ncols, sharex=sharex, sharey=sharey,
                 projection=projection, theme=theme, units=units,
                 width_ratios=width_ratios, height_ratios=height_ratios)
    if nrows == 1 and ncols == 1:
        return fig, fig.axes[0]
    if nrows == 1 or ncols == 1:
        return fig, list(fig.axes)
    grid = [[fig.axes[r * ncols + c] for c in range(ncols)] for r in range(nrows)]
    return fig, grid


def subplot_mosaic(mosaic, *, figsize: tuple[float, float] = (480, 360),
                   theme=None, units: str = "pt"):
    """Build a figure of spanning axes from an ASCII ``mosaic`` layout.

    ``mosaic`` is a multi-line string (or a list of equal-length rows) whose
    repeated labels mark the cells each axes spans, e.g.::

        \"\"\"
        AB
        AC
        \"\"\"

    gives ``A`` spanning both rows of column 0, with ``B``/``C`` stacked at the
    right. ``"."`` marks an empty cell. Returns ``(fig, {label: axes})``. Each
    label's cells must form a solid rectangle.
    """
    if isinstance(mosaic, str):
        rows = [list(line) for line in mosaic.splitlines() if line.strip()]
    else:
        rows = [list(r) for r in mosaic]
    nrows = len(rows)
    ncols = max((len(r) for r in rows), default=0)
    # Bounding box (min/max row & col) of each label's occupied cells.
    boxes: dict[str, list[int]] = {}
    order: list[str] = []
    for r, row in enumerate(rows):
        for c, label in enumerate(row):
            if label == ".":
                continue
            if label not in boxes:
                boxes[label] = [r, c, r, c]
                order.append(label)
            else:
                b = boxes[label]
                b[0], b[1] = min(b[0], r), min(b[1], c)
                b[2], b[3] = max(b[2], r), max(b[3], c)

    fig = Figure(figsize=figsize, nrows=nrows, ncols=ncols, theme=theme, units=units)
    fig.axes = [Axes(fig.theme) for _ in order]
    spans = []
    for label in order:
        r0, c0, r1, c1 = boxes[label]
        spans.append((r0, c0, r1 - r0 + 1, c1 - c0 + 1))
    fig._spans = spans
    return fig, {label: fig.axes[i] for i, label in enumerate(order)}


class GridSpec:
    """A lightweight grid geometry for spanning subplots. Create with a figure's
    row/column count, then slice it (NumPy-style) to place an axes across a
    range of rows/columns via :meth:`Figure.add_subplot`."""

    def __init__(self, nrows: int, ncols: int) -> None:
        self.nrows = nrows
        self.ncols = ncols

    def __getitem__(self, key) -> tuple[int, int, int, int]:
        return self._resolve(key)

    def _resolve(self, key) -> tuple[int, int, int, int]:
        rk, ck = key if isinstance(key, tuple) else (key, slice(None))

        def span(k, n):
            if isinstance(k, slice):
                start, stop, _ = k.indices(n)
                return start, max(stop - start, 1)
            k = k if k >= 0 else k + n
            return k, 1

        r0, rs = span(rk, self.nrows)
        c0, cs = span(ck, self.ncols)
        return r0, c0, rs, cs
