"""Artists: the marks drawn inside an axes.

Plotting methods such as ``Axes.line`` create these and return them, so a mark
can be adjusted after the fact::

    ln = ax.line(x, y)
    ln.color = ax.theme.color("C3")

Each artist reports the data range it covers (for autoscaling), draws itself,
and describes its legend key.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from . import _core
from ._canvas import NO_LINE, Canvas, HAlign, VAlign, dash
from ._data import Array, f64, union
from .colormaps import Colormap
from .colors import RGBA, with_alpha
from .norms import Norm
from .text import Label

if TYPE_CHECKING:
    from .scales import Scale

Range = tuple[float, float]


@dataclass
class View:
    """What an artist needs to draw: the data-to-device transform and the plot
    rectangle (device points, y down)."""

    tf: _core.Transform
    x: float
    y: float
    w: float
    h: float
    xlim: Range
    ylim: Range

    def fx(self, frac: float) -> float:
        """Device x of an axes fraction (0 = left)."""
        return self.x + frac * self.w

    def fy(self, frac: float) -> float:
        """Device y of an axes fraction (0 = bottom)."""
        return self.y + (1.0 - frac) * self.h


@dataclass
class Key:
    """How a legend entry is drawn."""

    kind: Literal["line", "marker", "patch", "errorbar"]
    color: RGBA
    linewidth: float = 1.2
    linestyle: str = "solid"
    marker: str | None = None
    markersize: float = 5.0
    edgecolor: RGBA | None = None


def _range(values: Array, scale: Scale) -> Range | None:
    return _core.finite_range(values, scale.code) if len(values) else None


def _ranges(scale: Scale, *columns: Array) -> Range | None:
    out = None
    for c in columns:
        out = union(out, _range(c, scale))
    return out


def _sample(n: int, k: int = 300) -> range:
    return range(0, n, max(1, n // k))


@dataclass(eq=False)
class Artist:
    """Base class for marks."""

    label: Label | None = field(default=None, kw_only=True)
    zorder: float = field(default=0.0, kw_only=True)
    #: Clip to the plot area.
    clip: bool = field(default=True, kw_only=True)

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        """The data range covered on each axis (``None`` if it covers none)."""
        return None, None

    def sticky(self) -> tuple[list[float], list[float]]:
        """Values the mark rests on (a bar's base): autoscale margins stop there."""
        return [], []

    def draw(self, canvas: Canvas, view: View) -> None:
        raise NotImplementedError

    def legend_key(self) -> Key | None:
        return None

    def footprint(self) -> tuple[list[float], list[float]]:
        """A sample of data points this mark covers, for legend placement."""
        return [], []


class Mappable:
    """A mark colored through a colormap; pass it to ``Figure.colorbar``."""

    cmap: Colormap
    norm: Norm
    alpha: float


# -- lines and points --------------------------------------------------------------


@dataclass(eq=False)
class Line(Artist):
    xs: Array = field(repr=False)
    ys: Array = field(repr=False)
    color: RGBA = (0, 0, 0, 255)
    linewidth: float = 1.2
    linestyle: str = "solid"
    marker: str | None = None
    markersize: float = 5.0
    simplify: bool = True

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        return _range(self.xs, xscale), _range(self.ys, yscale)

    def draw(self, canvas: Canvas, view: View) -> None:
        if self.linestyle not in NO_LINE and len(self.xs) >= 2:
            canvas.path(
                self.xs,
                self.ys,
                view.tf,
                stroke=self.color,
                width=self.linewidth,
                dash=dash(self.linestyle),
                cap="round",
                join="round",
                simplify=0.1 if self.simplify else None,
            )
        if self.marker:
            canvas.markers(
                self.xs, self.ys, view.tf, marker=self.marker, size=self.markersize, fill=self.color
            )

    def legend_key(self) -> Key:
        return Key("line", self.color, self.linewidth, self.linestyle, self.marker, self.markersize)

    def footprint(self) -> tuple[list[float], list[float]]:
        idx = _sample(len(self.xs))
        return [self.xs[i] for i in idx], [self.ys[i] for i in idx]


@dataclass(eq=False)
class Scatter(Artist, Mappable):
    xs: Array = field(repr=False)
    ys: Array = field(repr=False)
    color: RGBA = (0, 0, 0, 255)
    size: float = 5.0
    marker: str = "o"
    edgecolor: RGBA | None = None
    edgewidth: float = 1.0
    #: Per-point values colored through `cmap` and `norm` (optional).
    values: Array | None = field(default=None, repr=False)
    cmap: Colormap | None = None  # type: ignore[assignment]
    norm: Norm | None = None  # type: ignore[assignment]
    alpha: float = 1.0

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        return _range(self.xs, xscale), _range(self.ys, yscale)

    def draw(self, canvas: Canvas, view: View) -> None:
        fills = None
        if self.values is not None and self.cmap is not None and self.norm is not None:
            lut, code = self.norm.lut(self.cmap, self.alpha)
            fills = _core.map_colors(self.values, lut, *self.norm.limits, code)
        canvas.markers(
            self.xs,
            self.ys,
            view.tf,
            marker=self.marker,
            size=self.size,
            fill=self.color,
            fills=fills,
            edge=self.edgecolor,
            edge_width=self.edgewidth,
        )

    def legend_key(self) -> Key:
        return Key(
            "marker", self.color, marker=self.marker, markersize=self.size, edgecolor=self.edgecolor
        )

    footprint = Line.footprint  # type: ignore[assignment]


@dataclass(eq=False)
class Segments(Artist):
    """Independent straight segments (``hlines``, ``vlines``, ``eventplot``)."""

    x0: Array = field(repr=False)
    y0: Array = field(repr=False)
    x1: Array = field(repr=False)
    y1: Array = field(repr=False)
    color: RGBA = (0, 0, 0, 255)
    linewidth: float = 1.0
    linestyle: str = "solid"

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        return _ranges(xscale, self.x0, self.x1), _ranges(yscale, self.y0, self.y1)

    def draw(self, canvas: Canvas, view: View) -> None:
        canvas.segments(
            self.x0,
            self.y0,
            self.x1,
            self.y1,
            view.tf,
            color=self.color,
            width=self.linewidth,
            dash=dash(self.linestyle),
        )

    def legend_key(self) -> Key:
        return Key("line", self.color, self.linewidth, self.linestyle)

    def footprint(self) -> tuple[list[float], list[float]]:
        idx = _sample(len(self.x0))
        xs = [(self.x0[i] + self.x1[i]) / 2 for i in idx]
        return xs, [(self.y0[i] + self.y1[i]) / 2 for i in idx]


# -- areas -------------------------------------------------------------------------


@dataclass(eq=False)
class Rects(Artist):
    """Axis-aligned rectangles from ``(x0, y0)`` to ``(x1, y1)``: bars,
    histogram bins, mesh cells."""

    x0: Array = field(repr=False)
    y0: Array = field(repr=False)
    x1: Array = field(repr=False)
    y1: Array = field(repr=False)
    color: RGBA = (0, 0, 0, 255)
    edgecolor: RGBA | None = None
    linewidth: float = 0.75
    hatch: str | None = None
    #: Per-rectangle RGBA bytes, overriding `color`.
    fills: bytes | None = field(default=None, repr=False)
    sticky_x: list[float] = field(default_factory=list, repr=False)
    sticky_y: list[float] = field(default_factory=list, repr=False)

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        return _ranges(xscale, self.x0, self.x1), _ranges(yscale, self.y0, self.y1)

    def sticky(self) -> tuple[list[float], list[float]]:
        return self.sticky_x, self.sticky_y

    def draw(self, canvas: Canvas, view: View) -> None:
        canvas.rects(
            self.x0,
            self.y0,
            self.x1,
            self.y1,
            view.tf,
            fill=self.color,
            fills=self.fills,
            stroke=self.edgecolor,
            width=self.linewidth,
        )
        if self.hatch:
            tf = view.tf
            ink = self.edgecolor or canvas.theme.text_color
            for i in range(len(self.x0)):
                canvas.hatch(
                    tf.x(self.x0[i]),
                    tf.y(self.y0[i]),
                    tf.x(self.x1[i]),
                    tf.y(self.y1[i]),
                    self.hatch,
                    ink,
                    max(self.linewidth * 0.5, 0.5),
                )

    def legend_key(self) -> Key:
        return Key("patch", self.color, edgecolor=self.edgecolor)

    def footprint(self) -> tuple[list[float], list[float]]:
        xs, ys = [], []
        for i in _sample(len(self.x0), 100):
            for fx in (0.0, 0.5, 1.0):
                for fy in (0.0, 0.5, 1.0):
                    xs.append(self.x0[i] + (self.x1[i] - self.x0[i]) * fx)
                    ys.append(self.y0[i] + (self.y1[i] - self.y0[i]) * fy)
        return xs, ys


@dataclass(eq=False)
class Band(Artist):
    """The region between ``lo`` and ``hi`` along ``seq`` (``fill_between``).
    With ``vertical``, ``seq`` runs along y."""

    seq: Array = field(repr=False)
    lo: Array = field(repr=False)
    hi: Array = field(repr=False)
    color: RGBA = (0, 0, 0, 255)
    vertical: bool = False
    sticky_values: list[float] = field(default_factory=list, repr=False)

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        along = _range(self.seq, yscale if self.vertical else xscale)
        across = _ranges(xscale if self.vertical else yscale, self.lo, self.hi)
        return (across, along) if self.vertical else (along, across)

    def sticky(self) -> tuple[list[float], list[float]]:
        return (self.sticky_values, []) if self.vertical else ([], self.sticky_values)

    def draw(self, canvas: Canvas, view: View) -> None:
        canvas.band(self.seq, self.lo, self.hi, view.tf, fill=self.color, swap=self.vertical)

    def legend_key(self) -> Key:
        return Key("patch", self.color)

    def footprint(self) -> tuple[list[float], list[float]]:
        idx = _sample(len(self.seq), 100)
        s = [self.seq[i] for i in idx] * 3
        v = (
            [self.lo[i] for i in idx]
            + [self.hi[i] for i in idx]
            + [(self.lo[i] + self.hi[i]) / 2 for i in idx]
        )
        return (v, s) if self.vertical else (s, v)


@dataclass(eq=False)
class Polygons(Artist):
    """Closed polygons; polygon ``k`` takes the next ``counts[k]`` vertices."""

    xs: Array = field(repr=False)
    ys: Array = field(repr=False)
    counts: list[int] = field(repr=False)
    color: RGBA | None = (0, 0, 0, 255)
    edgecolor: RGBA | None = None
    linewidth: float = 1.0
    linestyle: str = "solid"
    hatch: str | None = None
    fills: bytes | None = field(default=None, repr=False)

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        return _range(self.xs, xscale), _range(self.ys, yscale)

    def draw(self, canvas: Canvas, view: View) -> None:
        if self.linestyle in ("solid", "-") or self.edgecolor is None:
            canvas.polygons(
                self.xs,
                self.ys,
                self.counts,
                view.tf,
                fill=self.color,
                fills=self.fills,
                stroke=self.edgecolor,
                width=self.linewidth,
            )
        else:  # dashed outlines: one path per polygon
            start = 0
            for n in self.counts:
                xs, ys = self.xs[start : start + n], self.ys[start : start + n]
                canvas.path(
                    xs,
                    ys,
                    view.tf,
                    fill=self.color,
                    close=True,
                    stroke=self.edgecolor,
                    width=self.linewidth,
                    dash=dash(self.linestyle),
                )
                start += n
        if self.hatch:
            tf, start = view.tf, 0
            for n in self.counts:
                dx = [tf.x(v) for v in self.xs[start : start + n]]
                dy = [tf.y(v) for v in self.ys[start : start + n]]
                canvas.hatch(
                    min(dx),
                    min(dy),
                    max(dx),
                    max(dy),
                    self.hatch,
                    self.edgecolor or canvas.theme.text_color,
                    outline=(dx, dy),
                )
                start += n

    def legend_key(self) -> Key:
        return Key("patch", self.color or (0, 0, 0, 0), edgecolor=self.edgecolor)

    def footprint(self) -> tuple[list[float], list[float]]:
        """Vertices plus points between each vertex and its polygon's center."""
        xs, ys, start = [], [], 0
        step = max(1, len(self.xs) // 300)
        for n in self.counts:
            px, py = self.xs[start : start + n], self.ys[start : start + n]
            start += n
            if not n:
                continue
            cx, cy = sum(px) / n, sum(py) / n
            for i in range(0, n, step):
                for f in (1.0, 0.66, 0.33):
                    xs.append(cx + (px[i] - cx) * f)
                    ys.append(cy + (py[i] - cy) * f)
        return xs, ys


# -- images ------------------------------------------------------------------------


def _image_rect(
    view: View, extent: tuple[float, float, float, float], origin: str
) -> tuple[float, float, float, float, bool, bool]:
    """Device ``(x, y, w, h)`` of an image and whether column 0 is on the left
    and row 0 on top. Row 0 sits at ``extent[3]`` for ``origin="upper"``, at
    ``extent[2]`` for ``"lower"``."""
    x0, x1, y0, y1 = extent
    row0, row_last = (y1, y0) if origin == "upper" else (y0, y1)
    left, right = view.tf.x(x0), view.tf.x(x1)
    first, last = view.tf.y(row0), view.tf.y(row_last)
    return (
        min(left, right),
        min(first, last),
        abs(right - left),
        abs(last - first),
        left <= right,
        first <= last,
    )


@dataclass(eq=False)
class Image(Artist, Mappable):
    """A grid of values colormapped into an image covering ``extent``
    (``x0, x1, y0, y1``). Row 0 is at the top when ``origin="upper"``."""

    values: Array = field(repr=False)
    width: int = 0
    height: int = 0
    extent: tuple[float, float, float, float] = (0.0, 1.0, 0.0, 1.0)
    cmap: Colormap = None  # type: ignore[assignment]
    norm: Norm = None  # type: ignore[assignment]
    origin: Literal["upper", "lower"] = "upper"
    alpha: float = 1.0

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        x0, x1, y0, y1 = self.extent
        return (min(x0, x1), max(x0, x1)), (min(y0, y1), max(y0, y1))

    def sticky(self) -> tuple[list[float], list[float]]:
        x0, x1, y0, y1 = self.extent
        return [x0, x1], [y0, y1]

    def draw(self, canvas: Canvas, view: View) -> None:
        if not (self.width and self.height):
            return
        x, y, w, h, col0_left, row0_top = _image_rect(view, self.extent, self.origin)
        lut, code = self.norm.lut(self.cmap, self.alpha)
        canvas.colormapped_image(
            self.values,
            self.width,
            self.height,
            lut,
            *self.norm.limits,
            x,
            y,
            w,
            h,
            norm=code,
            origin_upper=row0_top,
            flip_x=not col0_left,
        )

    def legend_key(self) -> Key:
        return Key("patch", self.cmap(0.5))


@dataclass(eq=False)
class RGBImage(Artist):
    """An RGBA image (``width * height * 4`` bytes, row 0 first) covering ``extent``."""

    rgba: bytes = field(repr=False)
    width: int = 0
    height: int = 0
    extent: tuple[float, float, float, float] = (0.0, 1.0, 0.0, 1.0)
    origin: Literal["upper", "lower"] = "upper"

    limits = Image.limits
    sticky = Image.sticky

    def draw(self, canvas: Canvas, view: View) -> None:
        if self.width and self.height:
            x, y, w, h, col0_left, row0_top = _image_rect(view, self.extent, self.origin)
            canvas.image(
                self.rgba,
                self.width,
                self.height,
                x,
                y,
                w,
                h,
                flip_x=not col0_left,
                flip_y=not row0_top,
            )


# -- composite marks -------------------------------------------------------------


@dataclass(eq=False)
class Group(Artist):
    """Several artists acting as one mark (one legend entry)."""

    children: list[Artist] = field(default_factory=list)
    key: Key | None = None

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        xr = yr = None
        for c in self.children:
            cx, cy = c.limits(xscale, yscale)
            xr, yr = union(xr, cx), union(yr, cy)
        return xr, yr

    def sticky(self) -> tuple[list[float], list[float]]:
        sx: list[float] = []
        sy: list[float] = []
        for c in self.children:
            a, b = c.sticky()
            sx += a
            sy += b
        return sx, sy

    def draw(self, canvas: Canvas, view: View) -> None:
        for c in self.children:
            c.draw(canvas, view)

    def legend_key(self) -> Key | None:
        if self.key is not None:
            return self.key
        return self.children[0].legend_key() if self.children else None

    def footprint(self) -> tuple[list[float], list[float]]:
        xs: list[float] = []
        ys: list[float] = []
        for c in self.children:
            a, b = c.footprint()
            xs += a
            ys += b
        return xs, ys


@dataclass(eq=False)
class ContourSet(Group, Mappable):
    """Contour lines or filled contours; colormapped, so it can have a colorbar."""

    levels: list[float] = field(default_factory=list)
    cmap: Colormap = None  # type: ignore[assignment]
    norm: Norm = None  # type: ignore[assignment]
    alpha: float = 1.0


@dataclass(eq=False)
class ErrorBars(Artist):
    """Points with error bars; caps are ``capsize`` points wide."""

    xs: Array = field(repr=False)
    ys: Array = field(repr=False)
    xerr: tuple[Array, Array] | None = field(default=None, repr=False)
    yerr: tuple[Array, Array] | None = field(default=None, repr=False)
    color: RGBA = (0, 0, 0, 255)
    linewidth: float = 1.0
    linestyle: str = "none"
    marker: str | None = "o"
    markersize: float = 4.0
    capsize: float = 2.0

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        def span(vals: Array, err: tuple[Array, Array] | None, scale: Scale) -> Range | None:
            if err is None:
                return _range(vals, scale)
            lo = f64([v - e for v, e in zip(vals, err[0], strict=True)])
            hi = f64([v + e for v, e in zip(vals, err[1], strict=True)])
            return _ranges(scale, vals, lo, hi)

        return span(self.xs, self.xerr, xscale), span(self.ys, self.yerr, yscale)

    def draw(self, canvas: Canvas, view: View) -> None:
        tf = view.tf
        if self.linestyle not in NO_LINE and len(self.xs) >= 2:
            canvas.path(
                self.xs,
                self.ys,
                tf,
                stroke=self.color,
                width=self.linewidth,
                dash=dash(self.linestyle),
                cap="round",
                join="round",
            )
        caps: tuple[list[float], ...] = ([], [], [], [])
        for err, vertical in ((self.yerr, True), (self.xerr, False)):
            if err is None:
                continue
            if vertical:
                lo = f64([v - e for v, e in zip(self.ys, err[0], strict=True)])
                hi = f64([v + e for v, e in zip(self.ys, err[1], strict=True)])
                canvas.segments(
                    self.xs, lo, self.xs, hi, tf, color=self.color, width=self.linewidth
                )
            else:
                lo = f64([v - e for v, e in zip(self.xs, err[0], strict=True)])
                hi = f64([v + e for v, e in zip(self.xs, err[1], strict=True)])
                canvas.segments(
                    lo, self.ys, hi, self.ys, tf, color=self.color, width=self.linewidth
                )
            if self.capsize > 0:
                c = self.capsize
                for i in range(len(self.xs)):
                    for end in (lo[i], hi[i]):
                        if vertical:
                            px, py = tf.x(self.xs[i]), tf.y(end)
                            seg = (px - c, py, px + c, py)
                        else:
                            px, py = tf.x(end), tf.y(self.ys[i])
                            seg = (px, py - c, px, py + c)
                        if all(math.isfinite(v) for v in seg):
                            for col, v in zip(caps, seg, strict=True):
                                col.append(v)
        if caps[0]:
            canvas.segments(*caps, color=self.color, width=self.linewidth)
        if self.marker:
            canvas.markers(
                self.xs, self.ys, tf, marker=self.marker, size=self.markersize, fill=self.color
            )

    def legend_key(self) -> Key:
        return Key(
            "errorbar", self.color, self.linewidth, self.linestyle, self.marker, self.markersize
        )

    footprint = Line.footprint  # type: ignore[assignment]


@dataclass(eq=False)
class Arrows(Artist):
    """Arrows from ``(x, y)`` to ``(x + u, y + v)`` (``quiver``)."""

    xs: Array = field(repr=False)
    ys: Array = field(repr=False)
    us: Array = field(repr=False)
    vs: Array = field(repr=False)
    color: RGBA = (0, 0, 0, 255)
    linewidth: float = 1.0
    head_length: float = 5.0
    head_width: float = 2.2

    def _ends(self) -> tuple[Array, Array]:
        return (
            f64([x + u for x, u in zip(self.xs, self.us, strict=True)]),
            f64([y + v for y, v in zip(self.ys, self.vs, strict=True)]),
        )

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        x1, y1 = self._ends()
        return _ranges(xscale, self.xs, x1), _ranges(yscale, self.ys, y1)

    def draw(self, canvas: Canvas, view: View) -> None:
        tf = view.tf
        x1, y1 = self._ends()
        for i in range(len(self.xs)):
            a, b, c, d = tf.x(self.xs[i]), tf.y(self.ys[i]), tf.x(x1[i]), tf.y(y1[i])
            if all(math.isfinite(v) for v in (a, b, c, d)):
                canvas.arrow(
                    a, b, c, d, self.color, self.linewidth, self.head_length, self.head_width
                )

    def legend_key(self) -> Key:
        return Key("line", self.color, self.linewidth)

    footprint = Line.footprint  # type: ignore[assignment]


@dataclass(eq=False)
class BoxPlot(Artist):
    """Box-and-whisker summaries at ``positions``."""

    positions: list[float] = field(repr=False)
    stats: list[dict[str, Any]] = field(repr=False)
    color: RGBA = (0, 0, 0, 255)
    width: float = 0.5
    showfliers: bool = True
    vertical: bool = True

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        hw = self.width / 2
        pos = f64([p + s for p in self.positions for s in (-hw, hw)])
        vals = [st[k] for st in self.stats for k in ("lo", "hi")]
        if self.showfliers:
            vals += [v for st in self.stats for v in st["fliers"]]
        pr, vr = (
            _range(pos, xscale if self.vertical else yscale),
            _range(f64(vals), yscale if self.vertical else xscale),
        )
        return (pr, vr) if self.vertical else (vr, pr)

    def draw(self, canvas: Canvas, view: View) -> None:
        hw, c = self.width / 2, self.color

        def xy(p: list[float], v: list[float]) -> tuple[Array, Array]:
            return (f64(p), f64(v)) if self.vertical else (f64(v), f64(p))

        pos = self.positions
        q1 = [s["q1"] for s in self.stats]
        q3 = [s["q3"] for s in self.stats]
        x0, y0 = xy([p - hw for p in pos], q1)
        x1, y1 = xy([p + hw for p in pos], q3)
        canvas.rects(x0, y0, x1, y1, view.tf, fill=with_alpha(c, 0.25), stroke=c, width=1.0)
        for key, width in (("med", 1.6),):
            med = [s[key] for s in self.stats]
            a, b = xy([p - hw for p in pos], med)
            e, f = xy([p + hw for p in pos], med)
            canvas.segments(a, b, e, f, view.tf, color=c, width=width)
        for edge, end in (("q1", "lo"), ("q3", "hi")):
            a, b = xy(pos, [s[edge] for s in self.stats])
            e, f = xy(pos, [s[end] for s in self.stats])
            canvas.segments(a, b, e, f, view.tf, color=c, width=1.0)
            a, b = xy([p - hw / 2 for p in pos], [s[end] for s in self.stats])
            e, f = xy([p + hw / 2 for p in pos], [s[end] for s in self.stats])
            canvas.segments(a, b, e, f, view.tf, color=c, width=1.0)
        if self.showfliers:
            fp = [p for p, s in zip(pos, self.stats, strict=True) for _ in s["fliers"]]
            fv = [v for s in self.stats for v in s["fliers"]]
            if fv:
                a, b = xy(fp, fv)
                canvas.markers(
                    a, b, view.tf, marker="o", size=4.0, fill=None, edge=c, edge_width=0.8
                )

    def legend_key(self) -> Key:
        return Key("patch", with_alpha(self.color, 0.25), edgecolor=self.color)


# -- guides ------------------------------------------------------------------------


@dataclass(eq=False)
class RefLine(Artist):
    """A horizontal (``axhline``) or vertical (``axvline``) line at a data
    value, spanning axes fractions ``lo..hi``."""

    value: float = 0.0
    vertical: bool = False
    lo: float = 0.0
    hi: float = 1.0
    color: RGBA = (0, 0, 0, 255)
    linewidth: float = 0.8
    linestyle: str = "solid"

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        v = (self.value, self.value)
        return (v, None) if self.vertical else (None, v)

    def draw(self, canvas: Canvas, view: View) -> None:
        if self.vertical:
            x = view.tf.x(self.value)
            pts = ([x], [view.fy(self.lo)], [x], [view.fy(self.hi)])
        else:
            y = view.tf.y(self.value)
            pts = ([view.fx(self.lo)], [y], [view.fx(self.hi)], [y])
        canvas.segments(*pts, color=self.color, width=self.linewidth, dash=dash(self.linestyle))

    def legend_key(self) -> Key:
        return Key("line", self.color, self.linewidth, self.linestyle)


@dataclass(eq=False)
class SpanBand(Artist):
    """A shaded band between two data values (``axhspan``, ``axvspan``)."""

    lo: float = 0.0
    hi: float = 1.0
    vertical: bool = False
    color: RGBA = (0, 0, 0, 64)

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        r = (min(self.lo, self.hi), max(self.lo, self.hi))
        return (r, None) if self.vertical else (None, r)

    def draw(self, canvas: Canvas, view: View) -> None:
        if self.vertical:
            a, b = view.tf.x(self.lo), view.tf.x(self.hi)
            canvas.rects([a], [view.y], [b], [view.y + view.h], fill=self.color)
        else:
            a, b = view.tf.y(self.lo), view.tf.y(self.hi)
            canvas.rects([view.x], [a], [view.x + view.w], [b], fill=self.color)

    def legend_key(self) -> Key:
        return Key("patch", self.color)


@dataclass(eq=False)
class AxLine(Artist):
    """An infinite straight line through ``p1`` and ``p2`` (in device space,
    so it stays straight on log axes)."""

    p1: tuple[float, float] = (0.0, 0.0)
    p2: tuple[float, float] = (1.0, 1.0)
    color: RGBA = (0, 0, 0, 255)
    linewidth: float = 0.8
    linestyle: str = "solid"

    def draw(self, canvas: Canvas, view: View) -> None:
        tf = view.tf
        ax, ay, bx, by = tf.x(self.p1[0]), tf.y(self.p1[1]), tf.x(self.p2[0]), tf.y(self.p2[1])
        dx, dy = bx - ax, by - ay
        if not all(math.isfinite(v) for v in (ax, ay, dx, dy)) or (dx == 0 and dy == 0):
            return
        # Extend far past the plot; the clip trims it.
        k = 4.0 * (view.w + view.h) / math.hypot(dx, dy)
        canvas.segments(
            [ax - k * dx],
            [ay - k * dy],
            [ax + k * dx],
            [ay + k * dy],
            color=self.color,
            width=self.linewidth,
            dash=dash(self.linestyle),
        )

    def legend_key(self) -> Key:
        return Key("line", self.color, self.linewidth, self.linestyle)


# -- text ----------------------------------------------------------------------------


@dataclass(eq=False)
class Text(Artist):
    """A label at ``(x, y)``, in data coordinates or, with ``coords="axes"``,
    as fractions of the plot area."""

    x: float = 0.0
    y: float = 0.0
    text: Label = ""
    size: float | None = None
    color: RGBA | None = None
    weight: str = "normal"
    style: str = "normal"
    ha: HAlign = "left"
    va: VAlign = "baseline"
    rotation: float = 0.0
    coords: Literal["data", "axes"] = "data"
    clip: bool = field(default=False, kw_only=True)

    def anchor(self, view: View) -> tuple[float, float]:
        if self.coords == "axes":
            return view.fx(self.x), view.fy(self.y)
        return view.tf.x(self.x), view.tf.y(self.y)

    def draw(self, canvas: Canvas, view: View) -> None:
        x, y = self.anchor(view)
        if math.isfinite(x) and math.isfinite(y):
            canvas.text(
                x,
                y,
                self.text,
                self.size or canvas.theme.axis_label_size,
                self.color,
                weight=self.weight,
                style=self.style,
                ha=self.ha,
                va=self.va,
                rotation=self.rotation,
            )


@dataclass(eq=False)
class Annotation(Text):
    """Text at ``xytext`` with an arrow pointing at ``xy`` (data coordinates)."""

    target: tuple[float, float] = (0.0, 0.0)
    arrow: bool = True
    arrowcolor: RGBA | None = None

    def draw(self, canvas: Canvas, view: View) -> None:
        if self.arrow:
            x0, y0 = self.anchor(view)
            x1, y1 = view.tf.x(self.target[0]), view.tf.y(self.target[1])
            ext = canvas.measure(
                self.text, self.size or canvas.theme.axis_label_size, self.weight, self.style
            )
            # Start the arrow at the edge of the text box, not inside it.
            cx = x0 + {"left": ext.width / 2, "center": 0.0, "right": -ext.width / 2}.get(
                self.ha, 0.0
            )
            cy = y0 + {
                "baseline": -(ext.ascent - ext.depth) / 2,
                "top": ext.height / 2,
                "bottom": -ext.height / 2,
                "center": 0.0,
            }.get(self.va, 0.0)
            dx, dy = x1 - cx, y1 - cy
            if all(math.isfinite(v) for v in (cx, cy, x1, y1)) and (dx or dy):
                hw, hh = ext.width / 2 + 2, ext.height / 2 + 2
                t = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf)
                if t < 1:
                    color = self.arrowcolor or canvas.theme.spine_color
                    canvas.arrow(
                        cx + dx * t,
                        cy + dy * t,
                        x1,
                        y1,
                        color,
                        max(canvas.theme.spine_width, 0.8),
                        6.0,
                        2.5,
                    )
        super().draw(canvas, view)

    def limits(self, xscale: Scale, yscale: Scale) -> tuple[Range | None, Range | None]:
        x, y = self.target
        return (x, x), (y, y)
