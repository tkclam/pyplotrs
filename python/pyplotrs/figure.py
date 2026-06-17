"""pyplotrs Figure/Axes API (Phase 1b).

Layout is solved in a single pass by the Rust ``pyplotrs-layout`` engine using
*pre-measured* real text extents: every band (title, axis labels, tick labels)
is reserved space sized from shaped text, so labels can never overlap the plot
and there is no draw-measure-adjust loop. Axis ticks come from the Rust "nice
numbers" locator. Data is drawn clipped to the plot area, and the y-axis label
is rotated via an affine group.

Phase 1b adds the core 2D mark vocabulary - line, scatter (marker shape
library), bar, hist, fill_between, errorbar - and an auto-legend whose glyphs
mirror the actual mark styles.
"""

from __future__ import annotations

import html
import math
from typing import Sequence

from . import _pyplotrs_core as _core
from . import colormaps as _colormaps
from . import mathtext as _mathtext
from . import theme as _theme
from . import threed as _threed
from .theme import Theme


def _tw(scene, text, size) -> float:
    """Math-aware text width (drop-in for ``scene.measure_text``)."""
    return _mathtext.measure(scene, text, size)[0]


def _th(scene, text, size) -> tuple[float, float]:
    """Math-aware ``(ascent, depth)`` for a string at ``size``."""
    _w, a, d = _mathtext.measure(scene, text, size)
    return a, d


def _text(scene, x, baseline, text, size, color) -> None:
    """Math-aware text draw (drop-in for ``scene.add_text``)."""
    _mathtext.draw(scene, x, baseline, text, size, color)

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


def _resolve_color(color) -> tuple[int, int, int, int]:
    """Resolve a colour against the *default* palette (used where no theme is in
    scope). Theme-aware sites use ``self._theme.resolve`` so ``"C0"`` follows the
    active palette."""
    return _theme.parse_color(color, _COLOR_CYCLE)


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


def _finite(values: Sequence[float]) -> list[float]:
    """The finite (non-NaN, non-inf) members of ``values``.

    Autoscaling ignores non-finite data — as matplotlib does — so a single
    ``NaN``/``inf`` (common in real datasets with gaps) can't collapse an axis
    to ``(-inf, inf)`` or an order-dependent range."""
    return [v for v in values if math.isfinite(v)]


def _data_range(values: Sequence[float], pad: float = _DATA_PAD) -> tuple[float, float]:
    finite = _finite(values)
    if not finite:
        return (0.0, 1.0)
    lo, hi = min(finite), max(finite)
    if lo == hi:
        lo -= 0.5
        hi += 0.5
    span = hi - lo
    return lo - span * pad, hi + span * pad


def _xform_coeffs(sx, sy) -> tuple[float, float, float, float]:
    """Recover the linear data->device transform ``(ax, bx, ay, by)`` from the
    affine scale closures, so the per-point mapping can run in Rust:
    ``dx = ax*x + bx``, ``dy = ay*y + by``."""
    bx = sx(0.0)
    by = sy(0.0)
    return sx(1.0) - bx, bx, sy(1.0) - by, by


def _colormap_lut(cmap) -> bytes:
    """A 256-entry RGBA lookup table sampled from ``cmap`` (1024 bytes)."""
    out = bytearray(256 * 4)
    for i in range(256):
        r, g, b, a = cmap(i / 255.0)
        o = i * 4
        out[o] = r
        out[o + 1] = g
        out[o + 2] = b
        out[o + 3] = a
    return bytes(out)


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
                ha: str = "left", va: str = "baseline") -> None:
    """Draw ``s`` (math-aware) anchored at device ``(dx, dy)`` with the given
    horizontal/vertical alignment. Coordinates are y-down device points."""
    tw = _tw(scene, s, size)
    a, d = _th(scene, s, size)
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
    _text(scene, dx, baseline, s, size, color)


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
    """Handle returned by :meth:`Axes.imshow`, consumed by
    :meth:`Figure.colorbar` to build a matching color scale."""

    def __init__(self, ax: "Axes", cmap, vmin: float, vmax: float) -> None:
        self.ax = ax
        self.cmap = cmap
        self.vmin = vmin
        self.vmax = vmax


class Axes:
    """A single set of axes: a coordinate system plus a stack of marks."""

    def __init__(self, theme: Theme | None = None) -> None:
        self._marks: list[dict] = []
        self._annotations: list[dict] = []
        self._cidx = 0  # next palette index for auto-colored marks
        self._theme: Theme = _theme.get(theme)
        self._legend: dict | None = None
        self._colorbar: dict | None = None
        self._title: str | None = None
        self._xlabel: str | None = None
        self._ylabel: str | None = None
        # View limits, populated during layout; None => auto from data.
        self._xlim: tuple[float, float] | None = None
        self._ylim: tuple[float, float] | None = None

    # -- styling helpers ----------------------------------------------------

    def _next_color(self, color):
        if color is None:
            palette = self._theme.palette
            c = palette[self._cidx % len(palette)]
            self._cidx += 1
            return c
        return self._theme.resolve(color)

    # -- public API: marks --------------------------------------------------

    def line(self, xs, ys, *, label: str | None = None, color=None, width: float | None = None,
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
            "xs": [float(x) for x in xs],
            "ys": [float(y) for y in ys],
            "label": label,
            "color": self._next_color(color),
            "width": self._theme.line_width if width is None else float(width),
            "linestyle": linestyle,
            "marker": marker,
            "markersize": float(markersize),
            "simplify": bool(simplify),
        })
        return self

    def scatter(self, xs, ys, *, label: str | None = None, color=None, size: float = 36.0,
                marker: str = "o", edgecolor=None, edgewidth: float = 1.0) -> "Axes":
        """Scatter markers at ``(xs, ys)``. ``size`` is marker area in pt²
        (so the drawn diameter is ``sqrt(size)``), matching matplotlib's ``s``."""
        self._marks.append({
            "kind": "scatter",
            "xs": [float(x) for x in xs],
            "ys": [float(y) for y in ys],
            "label": label,
            "color": self._next_color(color),
            "size": float(size),
            "marker": marker,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
            "edgewidth": float(edgewidth),
        })
        return self

    def bar(self, x, height, *, width: float = 0.8, bottom=0.0, color=None,
            label: str | None = None, edgecolor=None) -> "Axes":
        """Draw vertical bars of the given ``height`` at positions ``x``."""
        xs = [float(v) for v in x]
        heights = [float(v) for v in height]
        self._marks.append({
            "kind": "bar",
            "xs": xs,
            "heights": heights,
            "bottoms": _as_seq(bottom, len(xs)),
            "width": float(width),
            "color": self._next_color(color),
            "label": label,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
        })
        return self

    def hist(self, data, *, bins: int = 10, color=None, label: str | None = None,
             range=None, density: bool = False) -> "Axes":
        """Bin ``data`` into ``bins`` equal-width bins and draw the histogram."""
        vals = [float(v) for v in data]
        if not vals:
            vals = [0.0, 1.0]
        lo, hi = (float(range[0]), float(range[1])) if range else (min(vals), max(vals))
        if lo == hi:
            hi = lo + 1.0
        bins = max(int(bins), 1)
        width = (hi - lo) / bins
        edges = [lo + width * i for i in _irange(bins + 1)]
        counts = [0.0] * bins
        for v in vals:
            if v < lo or v > hi:
                continue
            idx = int((v - lo) / width)
            if idx >= bins:
                idx = bins - 1
            counts[idx] += 1.0
        if density:
            total = len(vals) * width
            if total:
                counts = [c / total for c in counts]
        self._marks.append({
            "kind": "hist",
            "edges": edges,
            "counts": counts,
            "color": self._next_color(color),
            "label": label,
        })
        return self

    def fill_between(self, xs, y1, y2=0.0, *, color=None, alpha: float = 0.3,
                     label: str | None = None) -> "Axes":
        """Fill the band between ``y1`` and ``y2`` across ``xs``."""
        xs = [float(x) for x in xs]
        y1 = [float(y) for y in y1]
        self._marks.append({
            "kind": "fill",
            "xs": xs,
            "y1": y1,
            "y2": _as_seq(y2, len(xs)),
            "color": self._next_color(color),
            "alpha": float(alpha),
            "label": label,
        })
        return self

    def errorbar(self, xs, ys, *, yerr=None, xerr=None, color=None, label: str | None = None,
                 marker: str | None = "o", markersize: float = 5.0, width: float = 1.5,
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
            "color": self._next_color(color),
            "label": label,
            "marker": marker,
            "markersize": float(markersize),
            "width": float(width),
            "capsize": float(capsize),
            "linestyle": linestyle,
        })
        return self

    def imshow(self, data, *, cmap="viridis", vmin: float | None = None,
               vmax: float | None = None, extent=None, origin: str = "upper") -> "_Mappable":
        """Display 2D ``data`` as a colormapped image.

        ``data`` is a sequence of equal-length rows. ``cmap`` is a colormap
        name (see :mod:`pyplotrs.colormaps`) or a ``Colormap``. ``extent`` is
        ``(x0, x1, y0, y1)`` in data coordinates (default ``(0, ncols, 0,
        nrows)``); ``origin`` is ``"upper"`` (row 0 at top) or ``"lower"``.
        Returns a handle for :meth:`Figure.colorbar`.
        """
        rows = [[float(v) for v in row] for row in data]
        h = len(rows)
        w = len(rows[0]) if rows else 0
        flat = [v for row in rows for v in row if math.isfinite(v)]
        lo = float(vmin) if vmin is not None else (min(flat) if flat else 0.0)
        hi = float(vmax) if vmax is not None else (max(flat) if flat else 1.0)
        cm = _colormaps.get_cmap(cmap)
        if extent is None:
            extent = (0.0, float(w), 0.0, float(h))
        else:
            extent = (float(extent[0]), float(extent[1]), float(extent[2]), float(extent[3]))
        self._marks.append({
            "kind": "image",
            "rows": rows,
            "w": w,
            "h": h,
            "cmap": cm,
            "vmin": lo,
            "vmax": hi,
            "extent": extent,
            "origin": origin,
        })
        return _Mappable(self, cm, lo, hi)

    # -- public API: chrome -------------------------------------------------

    def legend(self, *, loc: str = "best") -> "Axes":
        """Enable an auto-legend. ``loc`` is one of ``best`` / ``upper right`` /
        ``upper left`` / ``lower right`` / ``lower left`` / ``upper center`` /
        ``lower center``."""
        self._legend = {"loc": loc}
        return self

    # -- annotations --------------------------------------------------------

    def text(self, x, y, s, *, color=None, fontsize: float | None = None,
             ha: str = "left", va: str = "baseline") -> "Axes":
        """Draw ``s`` at data coordinates ``(x, y)``.

        ``ha`` is ``left``/``center``/``right``; ``va`` is
        ``baseline``/``bottom``/``center``/``top``. ``s`` may contain ``$...$``
        math. ``color`` defaults to the theme text colour."""
        self._annotations.append({
            "kind": "text", "x": float(x), "y": float(y), "s": str(s),
            "color": self._theme.text_color if color is None else self._theme.resolve(color),
            "size": None if fontsize is None else float(fontsize), "ha": ha, "va": va,
        })
        return self

    def annotate(self, text, xy, *, xytext=None, color=None, fontsize: float | None = None,
                 arrow: bool = True, ha: str = "left", va: str = "bottom") -> "Axes":
        """Annotate the data point ``xy`` with ``text`` placed at ``xytext``
        (defaults to ``xy``), optionally drawing a callout arrow from the text to
        the point. All coordinates are in data space."""
        xy = (float(xy[0]), float(xy[1]))
        self._annotations.append({
            "kind": "annotate", "s": str(text), "xy": xy,
            "xytext": xy if xytext is None else (float(xytext[0]), float(xytext[1])),
            "color": self._theme.text_color if color is None else self._theme.resolve(color),
            "size": None if fontsize is None else float(fontsize),
            "arrow": bool(arrow), "ha": ha, "va": va,
        })
        return self

    def set(self, *, title=None, xlabel=None, ylabel=None, xlim=None, ylim=None) -> "Axes":
        """Set any combination of title, axis labels, and view limits."""
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
        return self

    # -- layout helpers -----------------------------------------------------

    def _ranges(self) -> tuple[tuple[float, float], tuple[float, float]]:
        xs_all: list[float] = []
        ys_all: list[float] = []
        has_bar = False
        has_image = False
        for m in self._marks:
            k = m["kind"]
            if k in ("line", "scatter"):
                xs_all += m["xs"]
                ys_all += m["ys"]
            elif k == "bar":
                has_bar = True
                hw = m["width"] / 2.0
                for x in m["xs"]:
                    xs_all += [x - hw, x + hw]
                for b, h in zip(m["bottoms"], m["heights"]):
                    ys_all += [b, b + h]
            elif k == "hist":
                has_bar = True
                xs_all += [m["edges"][0], m["edges"][-1]]
                ys_all += m["counts"]
                ys_all.append(0.0)
            elif k == "fill":
                xs_all += m["xs"]
                ys_all += m["y1"]
                ys_all += m["y2"]
            elif k == "errorbar":
                xs_all += m["xs"]
                ys_all += m["ys"]
                if m["yerr"]:
                    for y, e in zip(m["ys"], m["yerr"]):
                        ys_all += [y - e, y + e]
                if m["xerr"]:
                    for x, e in zip(m["xs"], m["xerr"]):
                        xs_all += [x - e, x + e]
            elif k == "image":
                has_image = True
                x0, x1, y0, y1 = m["extent"]
                xs_all += [x0, x1]
                ys_all += [y0, y1]

        if not xs_all:
            xs_all, ys_all = [0.0, 1.0], [0.0, 1.0]

        # Images set tight limits exactly at their extent (no data margin).
        if self._xlim:
            xr = self._xlim
        elif has_image:
            fx = _finite(xs_all) or [0.0, 1.0]
            xr = (min(fx), max(fx))
        else:
            xr = _data_range(xs_all)

        if self._ylim:
            yr = self._ylim
        elif has_image:
            fy = _finite(ys_all) or [0.0, 1.0]
            yr = (min(fy), max(fy))
        elif has_bar:
            fy = _finite(ys_all) or [0.0, 1.0]
            lo, hi = min(fy), max(fy)
            if lo >= 0.0:
                yr = (0.0, hi + (hi or 1.0) * _DATA_PAD)
            else:
                yr = _data_range(ys_all)
        else:
            yr = _data_range(ys_all)
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

        xticks = _core.nice_ticks(xr[0], xr[1], 7)
        yticks = _core.nice_ticks(yr[0], yr[1], 6)

        x_tick_h = _TICK_LENGTH + _TICK_LABEL_GAP + tick_label_h
        y_label_w = max((_tw(scene, lbl, _TICK_LABEL_SIZE) for _, lbl in yticks), default=0.0)
        y_tick_w = _TICK_LENGTH + _TICK_LABEL_GAP + y_label_w

        title_h = 0.0
        if self._title:
            a, d = _th(scene, self._title, _TITLE_SIZE)
            title_h = a + d + _TITLE_GAP
        xlabel_h = 0.0
        if self._xlabel:
            a, d = _th(scene, self._xlabel, _AXIS_LABEL_SIZE)
            xlabel_h = a + d + _AXIS_LABEL_GAP
        ylabel_w = 0.0
        if self._ylabel:
            a, d = _th(scene, self._ylabel, _AXIS_LABEL_SIZE)
            ylabel_w = a + d + _AXIS_LABEL_GAP

        cbar_w = 0.0
        if self._colorbar:
            cb = self._colorbar
            cbticks = _core.nice_ticks(cb["vmin"], cb["vmax"], 6)
            max_lbl = max(
                (_tw(scene, lbl, _TICK_LABEL_SIZE) for _, lbl in cbticks),
                default=0.0,
            )
            cbar_w = _CBAR_GAP + _CBAR_WIDTH + _CBAR_TICK_LEN + _CBAR_TICK_GAP + max_lbl
            if cb["label"]:
                a, d, _ = scene.font_vmetrics(_AXIS_LABEL_SIZE)
                cbar_w += a + d + _AXIS_LABEL_GAP

        bands = (title_h, xlabel_h, ylabel_w, x_tick_h, y_tick_w, cbar_w)
        return bands, xticks, yticks

    # -- drawing ------------------------------------------------------------

    def _draw(self, scene: "_core.Scene", layout, xr, yr, xticks, yticks) -> None:
        plot = layout.plot
        px, py, pw, ph = plot.x, plot.y, plot.w, plot.h
        (xmin, xmax), (ymin, ymax) = xr, yr
        xspan = (xmax - xmin) or 1.0
        yspan = (ymax - ymin) or 1.0

        def sx(x: float) -> float:
            return px + (x - xmin) / xspan * pw

        def sy(y: float) -> float:
            return py + ph - (y - ymin) / yspan * ph

        # Theme: locals shadow the module defaults (sizes/colours) for this axes.
        t = self._theme
        _TICK_LABEL_SIZE = t.tick_label_size
        _AXIS_LABEL_SIZE = t.axis_label_size
        _TITLE_SIZE = t.title_size
        _SPINE = t.spine_color
        _BLACK = t.text_color
        sw = t.spine_width

        # Axes background fill (behind everything in the plot area).
        if t.axes_facecolor is not None:
            scene.add_path(
                [(px, py), (px + pw, py), (px + pw, py + ph), (px, py + ph)],
                fill_color=t.axes_facecolor, close=True,
            )

        # Gridlines at tick positions, behind the data.
        if t.grid:
            for value, _label in xticks:
                x = sx(value)
                scene.add_path([(x, py), (x, py + ph)],
                               stroke_color=t.grid_color, stroke_width=t.grid_width)
            for value, _label in yticks:
                y = sy(value)
                scene.add_path([(px, y), (px + pw, y)],
                               stroke_color=t.grid_color, stroke_width=t.grid_width)

        # Spines (despining is per-theme: only the listed edges are drawn).
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
            self._draw_mark(scene, m, sx, sy)
        scene.end_group()

        t_asc, t_desc, _ = scene.font_vmetrics(_TICK_LABEL_SIZE)

        # X ticks + labels.
        for value, label in xticks:
            x = sx(value)
            scene.add_path(
                [(x, py + ph), (x, py + ph + _TICK_LENGTH)],
                stroke_color=_SPINE,
                stroke_width=sw,
            )
            tw = _tw(scene, label, _TICK_LABEL_SIZE)
            baseline = py + ph + _TICK_LENGTH + _TICK_LABEL_GAP + t_asc
            _text(scene, x - tw / 2.0, baseline, label, _TICK_LABEL_SIZE, _BLACK)

        # Y ticks + labels (right-aligned, vertically centered on the tick).
        for value, label in yticks:
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

        # Title, centered over the plot area.
        if self._title:
            a, _d = _th(scene, self._title, _TITLE_SIZE)
            tw = _tw(scene, self._title, _TITLE_SIZE)
            baseline = layout.title.y + a
            _text(scene, px + (pw - tw) / 2.0, baseline, self._title, _TITLE_SIZE, _BLACK)

        # X-axis label, centered over the plot area.
        if self._xlabel:
            a, _d = _th(scene, self._xlabel, _AXIS_LABEL_SIZE)
            tw = _tw(scene, self._xlabel, _AXIS_LABEL_SIZE)
            baseline = layout.xlabel.y + a
            _text(scene, px + (pw - tw) / 2.0, baseline, self._xlabel, _AXIS_LABEL_SIZE, _BLACK)

        # Y-axis label, rotated 90deg CCW, centered on the plot area's height.
        if self._ylabel:
            a, d, _ = scene.font_vmetrics(_AXIS_LABEL_SIZE)
            tw = _tw(scene, self._ylabel, _AXIS_LABEL_SIZE)
            band = layout.ylabel
            pivot_x = band.x + band.w / 2.0 - (d - a) / 2.0
            pivot_y = py + ph / 2.0
            # Affine = translate(pivot) * rotate(-90deg): (x,y) -> (y+px, -x+py).
            scene.begin_group(0.0, -1.0, 1.0, 0.0, pivot_x, pivot_y)
            _text(scene, -tw / 2.0, 0.0, self._ylabel, _AXIS_LABEL_SIZE, _BLACK)
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
                _place_text(scene, sx(tx), sy(ty), an["s"], size, color, an["ha"], an["va"])
            else:  # plain text
                _place_text(scene, sx(an["x"]), sy(an["y"]), an["s"], size, color,
                            an["ha"], an["va"])

    def _draw_mark(self, scene, m: dict, sx, sy) -> None:
        kind = m["kind"]
        if kind == "line":
            # Fast path: map + build the polyline in Rust (no per-point Python).
            ax, bx, ay, by = _xform_coeffs(sx, sy)
            if _draws_line(m["linestyle"]) and len(m["xs"]) >= 2:
                scene.add_line_xform(m["xs"], m["ys"], ax, bx, ay, by, m["color"],
                                     m["width"], _dash_for(m["linestyle"]), "round", "round",
                                     m.get("simplify", True), 0.1)
            if m["marker"]:
                scene.add_markers_xform(m["xs"], m["ys"], ax, bx, ay, by, m["marker"],
                                        m["markersize"], m["color"], None, 1.0)
        elif kind == "scatter":
            ax, bx, ay, by = _xform_coeffs(sx, sy)
            scene.add_markers_xform(m["xs"], m["ys"], ax, bx, ay, by, m["marker"],
                                    math.sqrt(m["size"]), m["color"], m["edgecolor"],
                                    m["edgewidth"])
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
                               stroke_color=_WHITE, stroke_width=0.75)
        elif kind == "fill":
            top = [(sx(x), sy(a)) for x, a in zip(m["xs"], m["y1"])]
            bot = [(sx(x), sy(b)) for x, b in zip(reversed(m["xs"]), reversed(m["y2"]))]
            poly = top + bot
            if len(poly) >= 3:
                scene.add_path(poly, fill_color=_with_alpha(m["color"], m["alpha"]), close=True)
        elif kind == "errorbar":
            self._draw_errorbar(scene, m, sx, sy)
        elif kind == "image":
            self._draw_image(scene, m, sx, sy)

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

        rows = m["rows"]
        # 256-entry RGBA LUT built once from the colormap; the per-pixel lookup
        # (the hot loop) runs in Rust via add_colormapped_image.
        lut = _colormap_lut(m["cmap"])
        flat = [v for row in rows for v in row]
        scene.add_colormapped_image(flat, w, h, m["vmin"], m["vmax"], lut,
                                    m["origin"] == "upper", rx, ry, rw, rh)

    def _draw_errorbar(self, scene, m: dict, sx, sy) -> None:
        color, w, cap = m["color"], m["width"], m["capsize"]
        ax, bx, ay, by = _xform_coeffs(sx, sy)
        if _draws_line(m["linestyle"]) and len(m["xs"]) >= 2:
            scene.add_line_xform(m["xs"], m["ys"], ax, bx, ay, by, color, w,
                                 _dash_for(m["linestyle"]), "round", "round")
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
                                    m["markersize"], color, None, 1.0)

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

        # Ticks + labels to the right of the strip.
        t_asc, t_desc, _ = scene.font_vmetrics(_TICK_LABEL_SIZE)
        span = (vmax - vmin) or 1.0
        for value, label in _core.nice_ticks(vmin, vmax, 6):
            frac = (value - vmin) / span
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

    def _draw_legend(self, scene, px: float, py: float, pw: float, ph: float) -> None:
        entries = _legend_entries(self._marks)
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

def _legend_entries(marks) -> list[dict]:
    """The labeled marks eligible for a legend, in insertion order."""
    return [m for m in marks if m.get("label")]


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
        _draw_legend_glyph(scene, m, gx0, gx1, gcy)
        _text(scene, gx1 + mt["glyph_gap"], y + mt["ascent"], m["label"], mt["size"],
              mt["text_color"])
        y += mt["row_h"] + mt["row_gap"]


def _draw_legend_glyph(scene, m: dict, x0: float, x1: float, cy: float) -> None:
    kind = m["kind"]
    color = m["color"]
    cx = (x0 + x1) / 2.0
    if kind in ("bar", "hist", "fill"):
        h = _LEGEND_SIZE * 0.85
        fill = _with_alpha(color, m["alpha"]) if kind == "fill" else color
        scene.add_path(
            [(x0 + 2.0, cy - h / 2.0), (x1 - 2.0, cy - h / 2.0),
             (x1 - 2.0, cy + h / 2.0), (x0 + 2.0, cy + h / 2.0)],
            fill_color=fill, close=True,
        )
    elif kind == "scatter":
        _draw_marker(scene, cx, cy, math.sqrt(m["size"]), m["marker"],
                     facecolor=color, edgecolor=m["edgecolor"], edgewidth=m["edgewidth"])
    elif kind == "errorbar":
        if _draws_line(m["linestyle"]):
            scene.add_path([(x0 + 1.0, cy), (x1 - 1.0, cy)], stroke_color=color,
                           stroke_width=m["width"], cap="round")
        scene.add_path([(cx, cy - 3.0), (cx, cy + 3.0)], stroke_color=color, stroke_width=m["width"])
        if m["marker"]:
            _draw_marker(scene, cx, cy, m["markersize"], m["marker"], facecolor=color)
    else:  # line
        if _draws_line(m["linestyle"]):
            scene.add_path([(x0 + 1.0, cy), (x1 - 1.0, cy)], stroke_color=color,
                           stroke_width=m["width"], cap="round", dash=_dash_for(m["linestyle"]))
        if m["marker"]:
            _draw_marker(scene, cx, cy, m["markersize"], m["marker"], facecolor=color)


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


class Axes3D:
    """A 3D axes. Marks (scatter/plot/surface) are projected to 2D paths by an
    orthographic camera and depth-sorted, then drawn through the normal IR."""

    def __init__(self, theme: Theme | None = None) -> None:
        self._marks3: list[dict] = []
        self._cidx = 0
        self._theme: Theme = _theme.get(theme)
        self._legend: dict | None = None
        self._title: str | None = None
        self._xlabel: str | None = None
        self._ylabel: str | None = None
        self._zlabel: str | None = None
        self._xlim: tuple[float, float] | None = None
        self._ylim: tuple[float, float] | None = None
        self._zlim: tuple[float, float] | None = None
        self._elev = 30.0
        self._azim = -60.0

    def _next_color(self, color):
        if color is None:
            palette = self._theme.palette
            c = palette[self._cidx % len(palette)]
            self._cidx += 1
            return c
        return self._theme.resolve(color)

    # -- public API ---------------------------------------------------------

    def scatter(self, xs, ys, zs, *, label: str | None = None, color=None, size: float = 36.0,
                marker: str = "o", edgecolor=None) -> "Axes3D":
        """Scatter 3D points at ``(xs, ys, zs)``."""
        self._marks3.append({
            "kind": "scatter",
            "xs": [float(x) for x in xs],
            "ys": [float(y) for y in ys],
            "zs": [float(z) for z in zs],
            "label": label,
            "color": self._next_color(color),
            "size": float(size),
            "marker": marker,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
        })
        return self

    def plot(self, xs, ys, zs, *, label: str | None = None, color=None, width: float = 1.5,
             linestyle: str = "solid") -> "Axes3D":
        """Draw a 3D polyline through ``(xs, ys, zs)``."""
        self._marks3.append({
            "kind": "line",
            "xs": [float(x) for x in xs],
            "ys": [float(y) for y in ys],
            "zs": [float(z) for z in zs],
            "label": label,
            "color": self._next_color(color),
            "width": float(width),
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

    # matplotlib-style aliases.
    scatter3d = scatter
    plot3d = plot

    def legend(self, *, loc: str = "upper right") -> "Axes3D":
        """Enable an auto-legend for labelled line/scatter marks. ``loc`` is one
        of ``upper right`` / ``upper left`` / ``lower right`` / ``lower left``."""
        self._legend = {"loc": loc}
        return self

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
            if m["kind"] in ("scatter", "line"):
                xs += m["xs"]
                ys += m["ys"]
                zs += m["zs"]
            elif m["kind"] == "surface":
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

        # 2. Data marks (surfaces, then lines, then points on top).
        for m in self._marks3:
            if m["kind"] == "surface":
                self._draw_surface(scene, m, proj)
        for m in self._marks3:
            if m["kind"] == "line":
                poly = [proj(x, y, z)[:2] for x, y, z in zip(m["xs"], m["ys"], m["zs"])]
                if len(poly) >= 2:
                    scene.add_path(poly, stroke_color=m["color"], stroke_width=m["width"],
                                   cap="round", join="round", dash=_dash_for(m["linestyle"]))
        for m in self._marks3:
            if m["kind"] == "scatter":
                d = math.sqrt(m["size"])
                order = sorted(
                    (proj(x, y, z) for x, y, z in zip(m["xs"], m["ys"], m["zs"])),
                    key=lambda t: t[2],
                )
                for dx, dy, _ in order:
                    _draw_marker(scene, dx, dy, d, m["marker"], facecolor=m["color"],
                                 edgecolor=m["edgecolor"])

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
        if self._title:
            a, _d = _th(scene, self._title, _TITLE_SIZE)
            tw = _tw(scene, self._title, _TITLE_SIZE)
            _text(scene, plot.x + (plot.w - tw) / 2.0, layout.title.y + a, self._title,
                           _TITLE_SIZE, _BLACK)

        # Auto-legend for labelled line/scatter marks, inset in the plot rect.
        if self._legend is not None:
            entries = self._legend3_entries()
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

    def _legend3_entries(self) -> list[dict]:
        """Normalize labelled 3D marks into 2D-style legend entries so the shared
        legend box/glyph code can draw them. Surfaces (no single colour) are
        skipped."""
        out: list[dict] = []
        for m in self._marks3:
            if not m.get("label"):
                continue
            if m["kind"] == "scatter":
                out.append({"kind": "scatter", "label": m["label"], "color": m["color"],
                            "size": m["size"], "marker": m.get("marker", "o"),
                            "edgecolor": m.get("edgecolor"), "edgewidth": 1.0})
            elif m["kind"] == "line":
                out.append({"kind": "line", "label": m["label"], "color": m["color"],
                            "width": m.get("width", 1.5),
                            "linestyle": m.get("linestyle", "solid"),
                            "marker": None, "markersize": 5.0})
        return out

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
                    "d": math.sqrt(m["size"]),
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
            entries = self._legend3_entries()
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
                 projection: str | None = None, theme=None, units: str = "pt") -> None:
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
        make = Axes3D if projection == "3d" else Axes
        self.axes = [make(self.theme) for _ in range(nrows * ncols)]

    def set(self, *, suptitle: str | None = None) -> "Figure":
        if suptitle is not None:
            self.suptitle = suptitle
        return self

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
        """Labeled marks across all (2D) axes, de-duplicated by label so a
        series shared between panels appears once in the figure legend."""
        entries: list[dict] = []
        seen: set[str] = set()
        for ax in self.axes:
            for m in _legend_entries(getattr(ax, "_marks", [])):
                if m["label"] not in seen:
                    seen.add(m["label"])
                    entries.append(m)
        return entries

    def colorbar(self, mappable: "_Mappable", *, label: str | None = None) -> "Figure":
        """Attach a colorbar for ``mappable`` (from :meth:`Axes.imshow`) in a
        reserved band to the right of its axes."""
        mappable.ax._colorbar = {
            "cmap": mappable.cmap,
            "vmin": mappable.vmin,
            "vmax": mappable.vmax,
            "label": label,
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
        if self.suptitle:
            a, d = _th(scene, self.suptitle, _SUPTITLE_SIZE)
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
        )

        for ax, axl, (xr, yr), xt, yt in zip(self.axes, layout.axes, ranges, xticks, yticks):
            ax._draw(scene, axl, xr, yr, xt, yt)

        if self.suptitle:
            a, _d = _th(scene, self.suptitle, _SUPTITLE_SIZE)
            tw = _tw(scene, self.suptitle, _SUPTITLE_SIZE)
            st = layout.suptitle
            _text(scene, st.x + (st.w - tw) / 2.0, st.y + a, self.suptitle,
                           _SUPTITLE_SIZE, self.theme.text_color)

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
             theme=None, units: str = "pt"):
    """Create a [`Figure`] with an ``nrows`` x ``ncols`` grid of axes.

    ``figsize`` is the canvas ``(width, height)`` in **points** by default, so a
    plot is sized directly against its font scale; pass ``units="in"``, ``"cm"``
    or ``"mm"`` for another unit. ``projection="3d"`` makes every axes an
    [`Axes3D`]. ``theme`` is a [`Theme`] (or preset name like ``"nature"``); it
    flows to every axes. Returns ``(fig, ax)`` for a 1x1 grid,
    ``(fig, [ax, ...])`` when one dimension is 1, and ``(fig, [[ax, ...], ...])``
    otherwise (row-major).
    """
    fig = Figure(figsize=figsize, nrows=nrows, ncols=ncols, sharex=sharex, sharey=sharey,
                 projection=projection, theme=theme, units=units)
    if nrows == 1 and ncols == 1:
        return fig, fig.axes[0]
    if nrows == 1 or ncols == 1:
        return fig, list(fig.axes)
    grid = [[fig.axes[r * ncols + c] for c in range(ncols)] for r in range(nrows)]
    return fig, grid
