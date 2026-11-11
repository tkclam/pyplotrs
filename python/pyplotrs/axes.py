"""The 2D ``Axes``: a coordinate system holding marks.

Every plotting method returns the artist it adds. Styling of the axes itself
goes through one method, ``set``::

    ax.line(t, v, label="voltage")
    ax.set(xlabel="time (s)", ylabel="V", xlim=(0, 10), yscale="log")
    ax.legend()
"""

from __future__ import annotations

import math
from array import array
from collections.abc import Callable, Sequence
from numbers import Real
from typing import TYPE_CHECKING, Any, Literal

from . import _core
from . import _data as data
from . import colormaps as _colormaps
from . import norms as _norms
from . import scales as _scales
from . import ticker as _ticker
from ._axis import Axis, Range
from ._canvas import HAlign, VAlign, check_linestyle, check_marker
from ._frame import ColorbarSpec
from ._legend import LegendSpec
from .artists import (
    Annotation,
    Arrows,
    Artist,
    AxLine,
    Band,
    BoxPlot,
    Bracket,
    ContourSet,
    ErrorBars,
    Group,
    Image,
    Key,
    Line,
    Polygons,
    Rects,
    RefLine,
    RGBImage,
    ScaleBar,
    Scatter,
    Segments,
    SpanBand,
    Text,
    View,
    stars,
)
from .colors import RGBA, ColorLike, with_alpha
from .text import Label, as_label
from .theme import Theme

if TYPE_CHECKING:
    from .figure import Figure

Color = ColorLike | None
Cmap = str | _colormaps.Colormap
NormLike = _norms.Norm | str | None

_UNSET: Any = object()


class AxesBase:
    """What every kind of axes shares: a theme, a color cycle and marks."""

    def __init__(self, theme: Theme, figure: Figure | None = None) -> None:
        self.theme = theme
        self.figure = figure
        self.title: Label | None = None
        self._artists: list[Artist] = []
        self._legend: LegendSpec | None = None
        self._cycle = 0

    def _color(self, color: Color, alpha: float = 1.0) -> RGBA:
        """``color`` resolved against the theme, or the next palette color."""
        if color is None:
            palette = self.theme.palette
            c = palette[self._cycle % len(palette)]
            self._cycle += 1
        else:
            c = self.theme.color(color)
        return with_alpha(c, alpha)

    def _fills(self, name: str, color: Any, n: int, alpha: float) -> tuple[RGBA, bytes | None]:
        """One color for all ``n`` items, or a list of colors, one per item.

        Returns the main color (for the legend) and the per-item RGBA bytes.
        """
        if not isinstance(color, (list, tuple)) or all(isinstance(v, Real) for v in color):
            return self._color(color, alpha), None
        if len(color) != n:
            raise ValueError(f"{name}() got {len(color)} colors for {n} bars")
        rgba = [self._color(c, alpha) for c in color]
        return rgba[0], b"".join(bytes(c) for c in rgba)

    def _add(self, artist: Any, label: Any = None, zorder: float = 0.0) -> Any:
        artist.label = None if label is None else as_label(label)
        artist.zorder = float(zorder)
        self._artists.append(artist)
        return artist

    @property
    def artists(self) -> list[Artist]:
        """The marks in this axes, in the order they were added."""
        return list(self._artists)

    def legend(
        self,
        loc: str = "best",
        *,
        ncols: int = 1,
        title: Label | None = None,
        frameon: bool = True,
        fontsize: float | None = None,
    ) -> None:
        """Show a legend for every mark that has a ``label``.

        ``loc`` is ``"best"`` (the corner covering the least data) or a spot
        such as ``"upper left"`` or ``"lower center"``.
        """
        self._legend = LegendSpec(loc, ncols, title, frameon, fontsize)

    def get_title(self) -> Label | None:
        return self.title

    def __getattr__(self, name: str) -> Any:
        hint = MATPLOTLIB_HINTS.get(name)
        if hint:
            raise AttributeError(f"{type(self).__name__} has no {name!r}; {hint}")
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def __repr__(self) -> str:
        title = f" {self.title!r}" if self.title else ""
        n = len(self._artists)
        return f"<{type(self).__name__}{title} with {n} mark{'s' * (n != 1)}>"


MATPLOTLIB_HINTS = {
    "plot": "use line() for lines and scatter() for markers",
    "set_title": "use set(title=...)",
    "set_xlabel": "use set(xlabel=...)",
    "set_ylabel": "use set(ylabel=...)",
    "set_xlim": "use set(xlim=(lo, hi))",
    "set_ylim": "use set(ylim=(lo, hi))",
    "set_xscale": "use set(xscale=...)",
    "set_yscale": "use set(yscale=...)",
    "set_xticks": "use set(xticks=[...])",
    "set_yticks": "use set(yticks=[...])",
    "set_xticklabels": "use set(xticklabels=[...])",
    "set_yticklabels": "use set(yticklabels=[...])",
    "set_aspect": "use set(aspect='equal')",
    "grid": "use set(grid=True)",
    "semilogx": "use set(xscale='log') and line()",
    "semilogy": "use set(yscale='log') and line()",
    "loglog": "use set(xscale='log', yscale='log') and line()",
    "savefig": "use Figure.save(path)",
    "tick_params": "set tick style on the theme (tick_direction, tick_length)",
}


def _scalar_or_array(value: Any) -> bool:
    return isinstance(value, (int, float))


class Axes(AxesBase):
    """A 2D plot: an x axis, a y axis and the marks between them."""

    def __init__(self, theme: Theme, figure: Figure | None = None) -> None:
        super().__init__(theme, figure)
        self.xaxis = Axis(max_ticks=7)
        self.yaxis = Axis(max_ticks=6)
        self._colorbar: ColorbarSpec | None = None
        self._twins: list[tuple[Axes, str]] = []
        self._insets: list[tuple[Axes, tuple[float, float, float, float]]] = []
        self._host: Axes | None = None
        self._is_twin = False
        self._frame_on = True
        self._grid: bool | None = None
        self._aspect: str = "auto"
        self._xtickrotation: float | str = "auto"
        self._title_loc: Literal["left", "center", "right"] = "center"
        self._last_view: View | None = None

    # -- input handling ----------------------------------------------------------

    def _coords(self, values: Any, which: str) -> Any:
        """Coordinates as float64, switching the axis to a date or categorical
        scale when the data are datetimes or strings."""
        if data.is_numeric_buffer(values):
            return data.f64(values)
        if isinstance(values, (int, float)):
            return array("d", [float(values)])
        seq = values if isinstance(values, (list, tuple)) else list(values)
        axis = self.xaxis if which == "x" else self.yaxis
        if seq and _scales.is_datetime(seq[0]):
            if not isinstance(axis.scale, _scales.Date):
                axis.scale = _scales.Date()
            return array("d", [_scales.date2num(v) for v in seq])
        if any(isinstance(v, str) for v in seq):
            if not isinstance(axis.scale, _scales.Categorical):
                axis.scale = _scales.Categorical()
            cat = axis.scale
            assert isinstance(cat, _scales.Categorical)
            return array("d", [cat.position(v) for v in seq])
        return data.f64(seq)

    def _xy(self, mark: str, x: Any, y: Any) -> tuple[Any, Any]:
        if y is None:
            y, x = x, None
        ys = self._coords(y, "y")
        xs = array("d", range(len(ys))) if x is None else self._coords(x, "x")
        data.same_length(mark, x=xs, y=ys)
        return xs, ys

    # -- lines and points ----------------------------------------------------------

    def line(
        self,
        x: Any,
        y: Any = None,
        *,
        c: Any = None,
        color: Color = None,
        linewidth: float | None = None,
        linestyle: str = "solid",
        marker: str | None = None,
        markersize: float | None = None,
        cmap: Cmap = "viridis",
        norm: NormLike = None,
        vmin: float | None = None,
        vmax: float | None = None,
        alpha: float = 1.0,
        simplify: bool = True,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Line:
        """A line through the points. ``line(y)`` plots against 0, 1, 2, ...

        ``linestyle`` is ``"solid"``, ``"dashed"``, ``"dotted"``, ``"dashdot"``
        (or ``-``, ``--``, ``:``, ``-.``) or ``"none"``. ``marker`` (``o s ^ v
        D + x | _``) adds a marker at each point. NaN values leave gaps.
        ``simplify`` drops vertices that would not change the drawing.

        ``c`` gives each point a value, and the line is colored along its
        length through ``cmap`` and ``norm`` (a trajectory colored by time,
        say). Pass the result to ``Figure.colorbar`` to show the scale.
        """
        xs, ys = self._xy("line", x, y)
        values = cm = nrm = None
        if c is not None:
            values = data.f64(c)
            data.same_length("line", x=xs, c=values)
            cm = _colormaps.get(cmap)
            nrm = _norms.get(norm, vmin, vmax).autoscale(values)
            rgba = with_alpha(cm(0.5), alpha) if color is None else self._color(color, alpha)
        else:
            rgba = self._color(color, alpha)
        return self._add(
            Line(
                xs,
                ys,
                rgba,
                self.theme.line_width if linewidth is None else float(linewidth),
                check_linestyle(linestyle),
                check_marker(marker),
                self.theme.marker_size if markersize is None else float(markersize),
                simplify,
                values,
                cm,
                nrm,
                alpha,
            ),
            label,
            zorder,
        )

    def scatter(
        self,
        x: Any,
        y: Any,
        *,
        c: Any = None,
        color: Color = None,
        size: float | None = None,
        marker: str = "o",
        cmap: Cmap = "viridis",
        norm: NormLike = None,
        vmin: float | None = None,
        vmax: float | None = None,
        edgecolor: Color = None,
        edgewidth: float = 1.0,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Scatter:
        """Markers at the points. ``size`` is the marker diameter in points.

        ``c`` gives each point a value colored through ``cmap`` and ``norm``;
        the result can then be passed to ``Figure.colorbar``.
        """
        xs, ys = self._xy("scatter", x, y)
        values = cm = nrm = None
        if c is not None:
            values = data.f64(c)
            data.same_length("scatter", x=xs, c=values)
            cm = _colormaps.get(cmap)
            nrm = _norms.get(norm, vmin, vmax).autoscale(values)
            color = with_alpha(cm(0.5), alpha) if color is None else self._color(color, alpha)
        else:
            color = self._color(color, alpha)
        return self._add(
            Scatter(
                xs,
                ys,
                color,
                self.theme.marker_size if size is None else float(size),
                check_marker(marker) or "o",
                None if edgecolor is None else self.theme.color(edgecolor),
                float(edgewidth),
                values,
                cm,
                nrm,
                alpha,
            ),
            label,
            zorder,
        )

    def step(
        self, x: Any, y: Any, *, where: Literal["pre", "post", "mid"] = "pre", **kwargs: Any
    ) -> Line:
        """A staircase line; ``where`` says where the step happens between points."""
        xs, ys = self._xy("step", x, y)
        px, py = data.steps(xs, ys, where)
        return self.line(data.f64(px), data.f64(py), **kwargs)

    def stairs(
        self,
        values: Any,
        edges: Any = None,
        *,
        baseline: float | None = 0.0,
        fill: bool = False,
        color: Color = None,
        linewidth: float | None = None,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Artist:
        """A step outline over bins: ``values[i]`` spans ``edges[i]..edges[i+1]``.
        With ``fill``, the area down to ``baseline`` is filled."""
        vals = data.f64(values)
        edges = array("d", range(len(vals) + 1)) if edges is None else data.f64(edges)
        if len(edges) != len(vals) + 1:
            raise ValueError(
                f"stairs() needs len(edges) == len(values) + 1; got {len(edges)} and {len(vals)}"
            )
        px = [edges[0]]
        py = [vals[0] if baseline is None else baseline]
        for i, v in enumerate(vals):
            px += [edges[i], edges[i + 1]]
            py += [v, v]
        if baseline is not None:
            px.append(edges[-1])
            py.append(baseline)
        col = self._color(color, alpha)
        if fill:
            base = 0.0 if baseline is None else baseline
            art = Rects(
                edges[:-1],
                array("d", [base]) * len(vals),
                edges[1:],
                vals,
                col,
                col if col[3] == 255 else None,
                0.5,
                sticky_y=[base],
            )
            return self._add(art, label, zorder)
        lw = self.theme.line_width if linewidth is None else float(linewidth)
        return self._add(Line(data.f64(px), data.f64(py), col, lw, simplify=False), label, zorder)

    def stem(
        self,
        x: Any,
        y: Any = None,
        *,
        bottom: float = 0.0,
        color: Color = None,
        marker: str | None = "o",
        markersize: float | None = None,
        linewidth: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Group:
        """Vertical stems from ``bottom`` to each point, with a marker on top."""
        xs, ys = self._xy("stem", x, y)
        col = self._color(color)
        n = len(xs)
        stems = Segments(xs, array("d", [bottom]) * n, xs, ys, col, linewidth)
        parts: list[Artist] = [stems]
        if n:
            lo, hi = _core.finite_range(xs) or (0.0, 0.0)
            parts.append(
                Segments(
                    array("d", [lo]),
                    array("d", [bottom]),
                    array("d", [hi]),
                    array("d", [bottom]),
                    col,
                    linewidth,
                )
            )
        ms = self.theme.marker_size if markersize is None else markersize
        if marker:
            parts.append(
                Line(xs, ys, col, linestyle="none", marker=check_marker(marker), markersize=ms)
            )
        key = Key("line", col, linewidth, marker=marker, markersize=ms)
        return self._add(Group(parts, key), label, zorder)

    def errorbar(
        self,
        x: Any,
        y: Any,
        *,
        yerr: Any = None,
        xerr: Any = None,
        color: Color = None,
        marker: str | None = "o",
        markersize: float = 4.0,
        linestyle: str = "none",
        linewidth: float = 1.0,
        capsize: float = 2.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> ErrorBars:
        """Points with error bars. An error is a scalar, one value per point, or
        a ``(lower, upper)`` pair of those."""
        xs, ys = self._xy("errorbar", x, y)
        n = len(xs)

        def err(e: Any) -> tuple[Any, Any] | None:
            if e is None:
                return None
            if not _scalar_or_array(e) and len(e) == 2 and hasattr(e[0], "__len__"):
                return data.full(e[0], n), data.full(e[1], n)  # (lower, upper)
            full = data.full(e, n)
            return full, full

        return self._add(
            ErrorBars(
                xs,
                ys,
                err(xerr),
                err(yerr),
                self._color(color),
                float(linewidth),
                check_linestyle(linestyle),
                check_marker(marker),
                float(markersize),
                float(capsize),
            ),
            label,
            zorder,
        )

    # -- bars and areas ----------------------------------------------------------

    def bar(
        self,
        x: Any,
        height: Any,
        *,
        width: float = 0.6,
        bottom: Any = 0.0,
        color: Color | Sequence[ColorLike] = None,
        edgecolor: Color = None,
        hatch: str | None = None,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Rects:
        """Vertical bars. ``x`` may be category names. ``width`` is in data units.

        ``color`` is one color, or a list with one color per bar.
        """
        xs = self._coords(x, "x")
        n = len(xs)
        h = data.full(height, n)
        b = data.full(bottom, n)
        hw = width / 2
        fill, fills = self._fills("bar", color, n, alpha)
        return self._add(
            Rects(
                data.f64([v - hw for v in xs]),
                b,
                data.f64([v + hw for v in xs]),
                data.f64([p + q for p, q in zip(b, h, strict=True)]),
                fill,
                None if edgecolor is None else self.theme.color(edgecolor),
                0.75,
                hatch,
                fills,
                sticky_y=sorted(set(b)) if _scalar_or_array(bottom) else [],
            ),
            label,
            zorder,
        )

    def barh(
        self,
        y: Any,
        width: Any,
        *,
        height: float = 0.6,
        left: Any = 0.0,
        color: Color | Sequence[ColorLike] = None,
        edgecolor: Color = None,
        hatch: str | None = None,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Rects:
        """Horizontal bars. ``y`` may be category names. ``color`` is one color,
        or a list with one color per bar."""
        ys = self._coords(y, "y")
        n = len(ys)
        w = data.full(width, n)
        lft = data.full(left, n)
        hh = height / 2
        fill, fills = self._fills("barh", color, n, alpha)
        return self._add(
            Rects(
                lft,
                data.f64([v - hh for v in ys]),
                data.f64([p + q for p, q in zip(lft, w, strict=True)]),
                data.f64([v + hh for v in ys]),
                fill,
                None if edgecolor is None else self.theme.color(edgecolor),
                0.75,
                hatch,
                fills,
                sticky_x=sorted(set(lft)) if _scalar_or_array(left) else [],
            ),
            label,
            zorder,
        )

    def hist(
        self,
        values: Any,
        bins: int | Sequence[float] = 10,
        *,
        range: Range | None = None,
        density: bool = False,
        cumulative: bool = False,
        histtype: Literal["bar", "step"] = "bar",
        color: Color = None,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Rects | Line:
        """A histogram. ``bins`` is a count or the bin edges."""
        vals = data.f64(values)
        if isinstance(bins, int):
            edges, counts = _core.histogram(vals, bins, range, density)
        else:
            edges = sorted(float(b) for b in bins)
            counts = [0.0] * (len(edges) - 1)
            import bisect

            for v in vals:
                if edges[0] <= v <= edges[-1]:
                    counts[min(bisect.bisect_right(edges, v) - 1, len(counts) - 1)] += 1
            if density:
                total = sum(counts)
                counts = [
                    c / (total * (edges[i + 1] - edges[i])) if total else 0.0
                    for i, c in enumerate(counts)
                ]
        if cumulative:
            acc = 0.0
            for i, c in enumerate(counts):
                acc += c * ((edges[i + 1] - edges[i]) if density else 1.0)
                counts[i] = acc
        col = self._color(color, alpha)
        if histtype == "step":
            step = self.stairs(counts, edges, color=col, label=label, zorder=zorder)
            assert isinstance(step, Line)
            return step
        n = len(counts)
        return self._add(
            Rects(
                data.f64(edges[:-1]),
                array("d", [0.0]) * n,
                data.f64(edges[1:]),
                data.f64(counts),
                col,
                self.theme.background,
                0.5,
                sticky_y=[0.0],
            ),
            label,
            zorder,
        )

    def fill_between(
        self,
        x: Any,
        y1: Any,
        y2: Any = 0.0,
        *,
        color: Color = None,
        alpha: float = 0.3,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Band:
        """Shade the region between two curves (or a curve and a constant)."""
        xs = self._coords(x, "x")
        lo, hi = data.full(y1, len(xs)), data.full(y2, len(xs))
        sticky = [float(v) for v in (y1, y2) if _scalar_or_array(v)]
        return self._add(Band(xs, lo, hi, self._color(color, alpha), False, sticky), label, zorder)

    def fill_betweenx(
        self,
        y: Any,
        x1: Any,
        x2: Any = 0.0,
        *,
        color: Color = None,
        alpha: float = 0.3,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Band:
        """Shade between two curves that run along y."""
        ys = self._coords(y, "y")
        lo, hi = data.full(x1, len(ys)), data.full(x2, len(ys))
        sticky = [float(v) for v in (x1, x2) if _scalar_or_array(v)]
        return self._add(Band(ys, lo, hi, self._color(color, alpha), True, sticky), label, zorder)

    def stackplot(
        self,
        x: Any,
        *ys: Any,
        labels: Sequence[Label] | None = None,
        colors: Sequence[ColorLike] | None = None,
        alpha: float = 1.0,
        zorder: float = 0.0,
    ) -> list[Band]:
        """Stacked areas, one per series in ``ys``."""
        xs = self._coords(x, "x")
        base = array("d", [0.0]) * len(xs)
        out = []
        for i, series in enumerate(ys):
            top = data.f64([b + v for b, v in zip(base, data.full(series, len(xs)), strict=True)])
            col = self._color(colors[i] if colors else None, alpha)
            out.append(
                self._add(
                    Band(xs, base, top, col, False, [0.0]), labels[i] if labels else None, zorder
                )
            )
            base = top
        return out

    def boxplot(
        self,
        data_: Sequence[Any],
        *,
        positions: Sequence[float] | None = None,
        widths: float = 0.5,
        color: Color = None,
        whis: float = 1.5,
        showfliers: bool = True,
        vertical: bool = True,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> BoxPlot:
        """Box-and-whisker plots, one per dataset. A single flat sequence is one dataset."""
        sets = [data_] if data_ and _scalar_or_array(data_[0]) else list(data_)
        pos = (
            [float(p) for p in positions]
            if positions is not None
            else [float(i + 1) for i in range(len(sets))]
        )
        stats = [data.boxstats(s, whis) for s in sets]
        return self._add(
            BoxPlot(pos, stats, self._color(color), widths, showfliers, vertical), label, zorder
        )

    def violinplot(
        self,
        data_: Sequence[Any],
        *,
        positions: Sequence[float] | None = None,
        widths: float = 0.7,
        color: Color = None,
        bandwidth: float | None = None,
        points: int = 100,
        alpha: float = 0.5,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Polygons:
        """Kernel density outlines, one per dataset."""
        sets = [data_] if data_ and _scalar_or_array(data_[0]) else list(data_)
        pos = (
            [float(p) for p in positions]
            if positions is not None
            else [float(i + 1) for i in range(len(sets))]
        )
        col = self._color(color)
        xs, ys, counts = array("d"), array("d"), []
        for p, s in zip(pos, sets, strict=True):
            vals = data.f64(s)
            lo, hi = _core.finite_range(vals) or (0.0, 0.0)
            if hi <= lo:
                continue
            grid = [lo + (hi - lo) * i / (points - 1) for i in range(points)]
            dens = _core.gaussian_kde(vals, grid, bandwidth or 0.0)
            peak = max(dens) or 1.0
            half = [widths / 2 * d / peak for d in dens]
            xs.extend([p - h for h in half] + [p + h for h in reversed(half)])
            ys.extend(grid + grid[::-1])
            counts.append(2 * points)
        return self._add(Polygons(xs, ys, counts, with_alpha(col, alpha), col, 1.0), label, zorder)

    def pie(
        self,
        sizes: Sequence[float],
        *,
        labels: Sequence[Label] | None = None,
        colors: Sequence[ColorLike] | None = None,
        startangle: float = 90.0,
        autopct: str | Callable[[float], str] | None = None,
        radius: float = 1.0,
        counterclock: bool = True,
    ) -> Polygons:
        """A pie chart. Turns the frame off and keeps the aspect equal.
        ``labels`` name the wedges (and feed the legend); ``autopct`` (e.g.
        ``"{:.0f}%"``) writes each wedge's percentage inside it."""
        vals = [float(v) for v in sizes]
        total = sum(vals) or 1.0
        xs, ys, counts, fills = array("d"), array("d"), [], bytearray()
        angle = math.radians(startangle)
        sign = 1.0 if counterclock else -1.0
        for i, v in enumerate(vals):
            sweep = sign * 2 * math.pi * v / total
            n = max(2, int(abs(sweep) / (math.pi / 90)) + 1)
            xs.append(0.0)
            ys.append(0.0)
            for k in range(n + 1):
                a = angle + sweep * k / n
                xs.append(radius * math.cos(a))
                ys.append(radius * math.sin(a))
            counts.append(n + 2)
            col = self._color(colors[i] if colors else None)
            fills += bytes(col)
            mid = angle + sweep / 2
            if labels:
                c, s = math.cos(mid), math.sin(mid)
                ha = "left" if c > 0.1 else "right" if c < -0.1 else "center"
                self._add(
                    Text(
                        1.1 * radius * c,
                        1.1 * radius * s,
                        as_label(labels[i]),
                        self.theme.tick_label_size,
                        ha=ha,
                        va="center",
                    )
                )
            if autopct:
                pct = 100 * v / total
                txt = autopct.format(pct) if isinstance(autopct, str) else autopct(pct)
                dark = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2] < 128
                self._add(
                    Text(
                        0.6 * radius * math.cos(mid),
                        0.6 * radius * math.sin(mid),
                        txt,
                        self.theme.tick_label_size,
                        (255, 255, 255, 255) if dark else (0, 0, 0, 255),
                        ha="center",
                        va="center",
                    )
                )
            angle += sweep
        wedges = self._add(
            Polygons(xs, ys, counts, None, self.theme.background, 1.0, fills=bytes(fills))
        )
        # One legend entry per wedge.
        for i, lbl in enumerate(labels or []):
            r, g, b, a = fills[4 * i : 4 * i + 4]
            self._add(_LegendOnly(Key("patch", (r, g, b, a))), lbl)
        pad = 1.45 if labels else 1.05
        self._frame_on = False
        self._aspect = "equal"
        self.xaxis.limits = self.yaxis.limits = (-pad * radius, pad * radius)
        return wedges

    # -- fields and images ---------------------------------------------------------

    def imshow(
        self,
        z: Any,
        *,
        cmap: Cmap = "viridis",
        norm: NormLike = None,
        vmin: float | None = None,
        vmax: float | None = None,
        extent: tuple[float, float, float, float] | None = None,
        origin: Literal["upper", "lower"] = "upper",
        aspect: Literal["equal", "auto"] = "equal",
        alpha: float = 1.0,
        zorder: float = 0.0,
    ) -> Image | RGBImage:
        """An image of a 2D array, colormapped; or an RGB(A) image from an
        ``(h, w, 3|4)`` array of 0-255 integers or 0-1 floats.

        By default pixel centers sit on integer coordinates and row 0 is at the top.
        """
        rgb = _rgb_image(z)
        if rgb is not None:
            buf, w, h = rgb
            ext = extent or _default_extent(w, h, origin)
            self._image_axes(ext, aspect)
            return self._add(RGBImage(buf, w, h, ext, origin), None, zorder)
        values, w, h = data.grid(z)
        nrm = _norms.get(norm, vmin, vmax).autoscale(values)
        ext = extent or _default_extent(w, h, origin)
        self._image_axes(ext, aspect)
        return self._add(
            Image(values, w, h, ext, _colormaps.get(cmap), nrm, origin, alpha), None, zorder
        )

    def _image_axes(self, extent: tuple[float, float, float, float], aspect: str) -> None:
        """Fit the view to an image: no margins, equal aspect, and axes running
        the way the extent says (row 0 at the top for the default extent)."""
        if aspect == "equal":
            self._aspect = "equal"
        if not self._artists:
            self.xaxis.margin = self.yaxis.margin = 0.0
        self.xaxis.inverted = extent[1] < extent[0]
        self.yaxis.inverted = extent[3] < extent[2]

    def pcolormesh(
        self,
        *args: Any,
        cmap: Cmap = "viridis",
        norm: NormLike = None,
        vmin: float | None = None,
        vmax: float | None = None,
        alpha: float = 1.0,
        edgecolor: Color = None,
        zorder: float = 0.0,
    ) -> Image | Rects:
        """A colored grid. ``pcolormesh(Z)``, or ``pcolormesh(x, y, Z)`` with
        cell edges (length n+1) or centers (length n)."""
        xc, yc, values, w, h = _mesh_args(args)
        xe = xc if len(xc) == w + 1 else data.edges_from_centers(xc)
        ye = yc if len(yc) == h + 1 else data.edges_from_centers(yc)
        cm = _colormaps.get(cmap)
        nrm = _norms.get(norm, vmin, vmax).autoscale(values)
        lin = isinstance(self.xaxis.scale, _scales.Linear) and isinstance(
            self.yaxis.scale, _scales.Linear
        )
        if lin and data.is_uniform(xe) and data.is_uniform(ye) and edgecolor is None:
            self.xaxis.margin = self.yaxis.margin = 0.0
            return self._add(
                Image(values, w, h, (xe[0], xe[-1], ye[0], ye[-1]), cm, nrm, "lower", alpha),
                None,
                zorder,
            )
        lut, code = nrm.lut(cm, alpha)
        fills = _core.map_colors(values, lut, *nrm.limits, code)
        x0 = data.f64([xe[c] for _ in range(h) for c in range(w)])
        x1 = data.f64([xe[c + 1] for _ in range(h) for c in range(w)])
        y0 = data.f64([ye[r] for r in range(h) for _ in range(w)])
        y1 = data.f64([ye[r + 1] for r in range(h) for _ in range(w)])
        rects = Rects(
            x0,
            y0,
            x1,
            y1,
            (0, 0, 0, 255),
            None if edgecolor is None else self.theme.color(edgecolor),
            0.5,
            fills=fills,
            sticky_x=[xe[0], xe[-1]],
            sticky_y=[ye[0], ye[-1]],
        )
        _as_mappable(rects, cm, nrm, alpha)
        return self._add(rects, None, zorder)

    def contour(
        self,
        *args: Any,
        levels: int | Sequence[float] | None = None,
        colors: Any = None,
        cmap: Cmap | None = None,
        linewidth: float = 0.8,
        linestyle: str = "solid",
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> ContourSet:
        """Contour lines of ``Z`` (``contour(Z)`` or ``contour(x, y, Z)``).
        ``levels`` is a count hint (levels land on round numbers) or the values."""
        xc, yc, values, w, h = _mesh_args(args)
        lv = data.levels(values, levels, filled=False)
        cm = _colormaps.get(cmap or "viridis")
        nrm = _norms.Norm(min(lv), max(lv)) if lv else _norms.Norm(0.0, 1.0)
        if colors is None and cmap is None:
            line_colors = [self._color(None)] * len(lv)
        elif colors is not None:
            cs = [colors] if isinstance(colors, str) or _is_color_tuple(colors) else list(colors)
            line_colors = [self.theme.color(cs[i % len(cs)]) for i in range(len(lv))]
        else:
            line_colors = [cm(nrm(v)) for v in lv]
        children: list[Artist] = []
        for li, closed, pts in _core.contour_lines(values, w, h, data.f64(lv)):
            px = [data.interp(xc, p[0]) for p in pts]
            py = [data.interp(yc, p[1]) for p in pts]
            if closed:
                px.append(px[0])
                py.append(py[0])
            children.append(
                Line(
                    data.f64(px),
                    data.f64(py),
                    line_colors[li],
                    linewidth,
                    check_linestyle(linestyle),
                    simplify=False,
                )
            )
        cs_ = ContourSet(
            children,
            Key("line", line_colors[len(lv) // 2] if lv else (0, 0, 0, 255), linewidth),
            lv,
            cm,
            nrm,
        )
        return self._add(cs_, label, zorder)

    def contourf(
        self,
        *args: Any,
        levels: int | Sequence[float] | None = None,
        cmap: Cmap = "viridis",
        alpha: float = 1.0,
        upsample: int = 8,
        zorder: float = 0.0,
    ) -> ContourSet:
        """Filled contours of ``Z``, one color per band between levels."""
        xc, yc, values, w, h = _mesh_args(args)
        edges = data.levels(values, levels, filled=True)
        cm = _colormaps.get(cmap)
        nrm = _norms.BoundaryNorm(edges) if len(edges) >= 2 else _norms.Norm(0.0, 1.0)
        nb = max(len(edges) - 1, 1)
        band_lut = b"".join(bytes(with_alpha(cm((i + 0.5) / nb), alpha)) for i in range(nb))
        rgba, ow, oh = _core.contourf_image(
            values, w, h, data.f64(edges), band_lut, max(1, upsample)
        )
        self.xaxis.margin = self.yaxis.margin = 0.0
        img = RGBImage(rgba, ow, oh, (xc[0], xc[-1], yc[0], yc[-1]))
        cs_ = ContourSet([img], Key("patch", cm(0.5)), edges, cm, nrm, alpha)
        return self._add(cs_, None, zorder)

    def hist2d(
        self,
        x: Any,
        y: Any,
        *,
        bins: int | tuple[int, int] = 20,
        range: tuple[Range, Range] | None = None,
        cmap: Cmap = "viridis",
        norm: NormLike = None,
        vmin: float | None = None,
        vmax: float | None = None,
        zorder: float = 0.0,
    ) -> Image:
        """A 2D histogram shown as an image."""
        xs, ys = self._xy("hist2d", x, y)
        nx, ny = (bins, bins) if isinstance(bins, int) else bins
        (xlo, xhi), (ylo, yhi) = range or (
            _core.finite_range(xs) or (0, 1),
            _core.finite_range(ys) or (0, 1),
        )
        counts = data.f64(_core.hist2d(xs, ys, nx, ny, xlo, xhi, ylo, yhi))
        self.xaxis.margin = self.yaxis.margin = 0.0
        nrm = _norms.get(norm, vmin, vmax).autoscale(counts)
        return self._add(
            Image(counts, nx, ny, (xlo, xhi, ylo, yhi), _colormaps.get(cmap), nrm, "lower"),
            None,
            zorder,
        )

    def hexbin(
        self,
        x: Any,
        y: Any,
        *,
        gridsize: int = 30,
        cmap: Cmap = "viridis",
        norm: NormLike = None,
        vmin: float | None = None,
        vmax: float | None = None,
        mincount: int = 1,
        zorder: float = 0.0,
    ) -> Polygons:
        """Hexagonal binning of points, colored by count."""
        xs, ys = self._xy("hexbin", x, y)
        (xlo, xhi), (ylo, yhi) = _core.finite_range(xs) or (0, 1), _core.finite_range(ys) or (0, 1)
        cells, sx, sy = _core.hexbin(xs, ys, gridsize, xlo, xhi, ylo, yhi)
        cells = [c for c in cells if c[2] >= mincount]
        counts = data.f64([c[2] for c in cells])
        cm = _colormaps.get(cmap)
        nrm = _norms.get(norm, vmin, vmax).autoscale(counts)
        lut, code = nrm.lut(cm)
        fills = _core.map_colors(counts, lut, *nrm.limits, code)
        offsets = [
            (sx * math.cos(a), sy * math.sin(a) * 2 / 3)
            for a in (math.pi / 6 + k * math.pi / 3 for k in range(6))
        ]
        hx, hy = array("d"), array("d")
        for cx, cy, _ in cells:
            hx.extend(cx + ox for ox, _ in offsets)
            hy.extend(cy + oy for _, oy in offsets)
        poly = Polygons(hx, hy, [6] * len(cells), None, fills=fills)
        _as_mappable(poly, cm, nrm, 1.0)
        return self._add(poly, None, zorder)

    def quiver(
        self,
        x: Any,
        y: Any,
        u: Any,
        v: Any,
        *,
        scale: float = 1.0,
        color: Color = None,
        linewidth: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Arrows:
        """Arrows of ``(u, v) * scale`` (data units) starting at each ``(x, y)``.
        2D grids are flattened."""
        flat = [_flat(a) for a in (x, y, u, v)]
        xs, ys = self._coords(flat[0], "x"), self._coords(flat[1], "y")
        us = data.f64([s * scale for s in data.f64(flat[2])])
        vs = data.f64([s * scale for s in data.f64(flat[3])])
        data.same_length("quiver", x=xs, y=ys, u=us, v=vs)
        return self._add(Arrows(xs, ys, us, vs, self._color(color), linewidth), label, zorder)

    def streamplot(
        self,
        x: Any,
        y: Any,
        u: Any,
        v: Any,
        *,
        density: float = 1.0,
        color: Color = None,
        linewidth: float = 1.0,
        arrows: bool = True,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Group:
        """Streamlines of the vector field ``(u, v)`` on the grid ``x``, ``y``."""
        xc = [float(t) for t in (x[0] if data.is_2d(x) else x)]
        yc = [float(t) for t in ([r[0] for r in y] if data.is_2d(y) else y)]
        uu, w, h = data.grid(u, "u")
        vv, w2, h2 = data.grid(v, "v")
        if (w, h) != (w2, h2) or (len(xc), len(yc)) != (w, h):
            raise ValueError("streamplot() needs u and v of shape (len(y), len(x))")
        col = self._color(color)
        parts: list[Artist] = []
        heads = ([], [], [], [])
        for px, py in data.streamlines(xc, yc, data.rows(uu, w, h), data.rows(vv, w, h), density):
            parts.append(Line(data.f64(px), data.f64(py), col, linewidth, simplify=False))
            if arrows and len(px) > 4:
                m = len(px) // 2
                for col_, val in zip(
                    heads,
                    (px[m - 1], py[m - 1], px[m + 1] - px[m - 1], py[m + 1] - py[m - 1]),
                    strict=True,
                ):
                    col_.append(val)
        if heads[0]:
            norm = [math.hypot(a, b) or 1.0 for a, b in zip(heads[2], heads[3], strict=True)]
            tiny = 1e-6 * max(abs(xc[-1] - xc[0]), abs(yc[-1] - yc[0]))
            parts.append(
                Arrows(
                    data.f64(heads[0]),
                    data.f64(heads[1]),
                    data.f64([a / n * tiny for a, n in zip(heads[2], norm, strict=True)]),
                    data.f64([b / n * tiny for b, n in zip(heads[3], norm, strict=True)]),
                    col,
                    0.0,
                    5.0,
                    2.5,
                )
            )
        return self._add(Group(parts, Key("line", col, linewidth)), label, zorder)

    # -- guides and shapes ------------------------------------------------------

    def hlines(
        self,
        y: Any,
        xmin: Any,
        xmax: Any,
        *,
        color: Color = None,
        linewidth: float = 1.0,
        linestyle: str = "solid",
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Segments:
        """Horizontal lines at each ``y`` from ``xmin`` to ``xmax``."""
        ys = self._coords(y, "y")
        n = len(ys)
        return self._add(
            Segments(
                data.full(xmin, n),
                ys,
                data.full(xmax, n),
                ys,
                self._color(color),
                float(linewidth),
                check_linestyle(linestyle),
            ),
            label,
            zorder,
        )

    def vlines(
        self,
        x: Any,
        ymin: Any,
        ymax: Any,
        *,
        color: Color = None,
        linewidth: float = 1.0,
        linestyle: str = "solid",
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Segments:
        """Vertical lines at each ``x`` from ``ymin`` to ``ymax``."""
        xs = self._coords(x, "x")
        n = len(xs)
        return self._add(
            Segments(
                xs,
                data.full(ymin, n),
                xs,
                data.full(ymax, n),
                self._color(color),
                float(linewidth),
                check_linestyle(linestyle),
            ),
            label,
            zorder,
        )

    def eventplot(
        self,
        positions: Sequence[Any],
        *,
        orientation: Literal["horizontal", "vertical"] = "horizontal",
        lineoffsets: float = 1.0,
        linelengths: float = 0.8,
        colors: Any = None,
        linewidth: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Segments:
        """A raster of event times: row ``i`` of ``positions`` is drawn as ticks
        at height ``i * lineoffsets``. A flat sequence is a single row."""
        rows = [positions] if len(positions) and _scalar_or_array(positions[0]) else positions
        along, lo, hi = array("d"), array("d"), array("d")
        for i, row in enumerate(rows):
            r = data.f64(row)
            along.extend(r)
            c = i * lineoffsets
            lo.extend(array("d", [c - linelengths / 2]) * len(r))
            hi.extend(array("d", [c + linelengths / 2]) * len(r))
        col = self._color(colors)
        if orientation == "horizontal":
            art = Segments(along, lo, along, hi, col, float(linewidth))
        else:
            art = Segments(lo, along, hi, along, col, float(linewidth))
        return self._add(art, label, zorder)

    def axhline(
        self,
        y: float = 0.0,
        *,
        xmin: float = 0.0,
        xmax: float = 1.0,
        color: Color = None,
        linewidth: float | None = None,
        linestyle: str = "solid",
        label: Label | None = None,
        zorder: float = 1.0,
    ) -> RefLine:
        """A horizontal line across the axes at ``y`` (``xmin``/``xmax`` are axes fractions)."""
        col = self.theme.spine_color if color is None else self.theme.color(color)
        lw = self.theme.spine_width if linewidth is None else float(linewidth)
        return self._add(
            RefLine(float(y), False, xmin, xmax, col, lw, check_linestyle(linestyle)), label, zorder
        )

    def axvline(
        self,
        x: float = 0.0,
        *,
        ymin: float = 0.0,
        ymax: float = 1.0,
        color: Color = None,
        linewidth: float | None = None,
        linestyle: str = "solid",
        label: Label | None = None,
        zorder: float = 1.0,
    ) -> RefLine:
        """A vertical line across the axes at ``x`` (``ymin``/``ymax`` are axes fractions)."""
        col = self.theme.spine_color if color is None else self.theme.color(color)
        lw = self.theme.spine_width if linewidth is None else float(linewidth)
        return self._add(
            RefLine(float(x), True, ymin, ymax, col, lw, check_linestyle(linestyle)), label, zorder
        )

    def axhspan(
        self,
        ymin: float,
        ymax: float,
        *,
        color: Color = "gray",
        alpha: float = 0.2,
        label: Label | None = None,
        zorder: float = -1.0,
    ) -> SpanBand:
        """Shade the horizontal band between ``ymin`` and ``ymax``."""
        return self._add(
            SpanBand(float(ymin), float(ymax), False, self._color(color, alpha)), label, zorder
        )

    def axvspan(
        self,
        xmin: float,
        xmax: float,
        *,
        color: Color = "gray",
        alpha: float = 0.2,
        label: Label | None = None,
        zorder: float = -1.0,
    ) -> SpanBand:
        """Shade the vertical band between ``xmin`` and ``xmax``."""
        return self._add(
            SpanBand(float(xmin), float(xmax), True, self._color(color, alpha)), label, zorder
        )

    def axline(
        self,
        xy1: tuple[float, float],
        xy2: tuple[float, float] | None = None,
        *,
        slope: float | None = None,
        color: Color = None,
        linewidth: float | None = None,
        linestyle: str = "solid",
        label: Label | None = None,
        zorder: float = 1.0,
    ) -> AxLine:
        """An infinite line through ``xy1`` and ``xy2``, or through ``xy1`` with ``slope``."""
        if (xy2 is None) == (slope is None):
            raise ValueError("axline() needs exactly one of xy2 or slope")
        p2 = xy2 if xy2 is not None else (xy1[0] + 1.0, xy1[1] + float(slope))  # type: ignore[arg-type]
        col = self.theme.spine_color if color is None else self.theme.color(color)
        lw = self.theme.spine_width if linewidth is None else float(linewidth)
        return self._add(
            AxLine(
                (float(xy1[0]), float(xy1[1])),
                (float(p2[0]), float(p2[1])),
                col,
                lw,
                check_linestyle(linestyle),
            ),
            label,
            zorder,
        )

    def _shape(
        self,
        xs: list[float],
        ys: list[float],
        facecolor: Color,
        edgecolor: Color,
        linewidth: float,
        linestyle: str,
        hatch: str | None,
        alpha: float,
        label: Any,
        zorder: float,
    ) -> Polygons:
        fill = None if facecolor == "none" else self._color(facecolor, alpha)
        edge = None if edgecolor in (None, "none") else self.theme.color(edgecolor)
        return self._add(
            Polygons(
                data.f64(xs),
                data.f64(ys),
                [len(xs)],
                fill,
                edge,
                linewidth,
                check_linestyle(linestyle),
                hatch,
            ),
            label,
            zorder,
        )

    def polygon(
        self,
        points: Sequence[tuple[float, float]],
        *,
        facecolor: Color = None,
        edgecolor: Color = None,
        linewidth: float = 1.0,
        linestyle: str = "solid",
        hatch: str | None = None,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Polygons:
        """A filled polygon through ``points``. Use ``facecolor="none"`` for an outline."""
        return self._shape(
            [p[0] for p in points],
            [p[1] for p in points],
            facecolor,
            edgecolor,
            linewidth,
            linestyle,
            hatch,
            alpha,
            label,
            zorder,
        )

    def rectangle(
        self,
        xy: tuple[float, float],
        width: float,
        height: float,
        *,
        angle: float = 0.0,
        **kwargs: Any,
    ) -> Polygons:
        """A rectangle with corner ``xy``, rotated ``angle`` degrees about it."""
        a = math.radians(angle)
        c, s = math.cos(a), math.sin(a)
        corners = [(0, 0), (width, 0), (width, height), (0, height)]
        return self.polygon(
            [(xy[0] + px * c - py * s, xy[1] + px * s + py * c) for px, py in corners], **kwargs
        )

    def ellipse(
        self,
        xy: tuple[float, float],
        width: float,
        height: float,
        *,
        angle: float = 0.0,
        **kwargs: Any,
    ) -> Polygons:
        """An ellipse centered on ``xy``."""
        a = math.radians(angle)
        c, s = math.cos(a), math.sin(a)
        pts = []
        for k in range(96):
            t = 2 * math.pi * k / 96
            ex, ey = width / 2 * math.cos(t), height / 2 * math.sin(t)
            pts.append((xy[0] + ex * c - ey * s, xy[1] + ex * s + ey * c))
        return self.polygon(pts, **kwargs)

    def circle(self, xy: tuple[float, float], radius: float, **kwargs: Any) -> Polygons:
        """A circle in data units (round on screen only with ``aspect="equal"``)."""
        return self.ellipse(xy, 2 * radius, 2 * radius, **kwargs)

    def arrow(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
        *,
        color: Color = None,
        linewidth: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Arrows:
        """An arrow from ``(x, y)`` to ``(x + dx, y + dy)``."""
        col = self.theme.text_color if color is None else self.theme.color(color)
        return self._add(
            Arrows(_one(x), _one(y), _one(dx), _one(dy), col, linewidth, 7.0, 3.0),
            label,
            zorder,
        )

    # -- figure furniture ---------------------------------------------------------

    def scalebar(
        self,
        x: float | None = None,
        y: float | None = None,
        *,
        xlabel: Label | None = None,
        ylabel: Label | None = None,
        loc: str | tuple[float, float] = "lower right",
        color: Color = None,
        linewidth: float = 1.5,
        size: float | None = None,
        pad: float = 4.0,
        zorder: float = 3.0,
    ) -> ScaleBar:
        """Scale bars: a horizontal bar ``x`` data units long and/or a vertical
        bar ``y`` units tall, the usual stand-in for axes on traces and images::

            ax.scalebar(x=0.5, y=20, xlabel="500 ms", ylabel="20 mV")
            ax.set(frame=False)

        Labels default to the length; pass ``""`` for none. ``loc`` is a
        corner of the plot (``"lower right"``, ``"lower left"``, ``"upper
        right"``, ``"upper left"``), with the bars and their labels kept
        ``pad`` points inside it, or a data point ``(x, y)`` where the bars
        start and run right and up.
        """
        if x is None and y is None:
            raise ValueError("scalebar() needs a length for x, y or both")
        minus = self.theme.unicode_minus

        def lab(given: Label | None, length: float | None) -> Label | None:
            if length is None:
                return None
            return as_label(given) if given is not None else _ticker.plain(length, minus)

        return self._add(
            ScaleBar(
                _opt_float(x),
                _opt_float(y),
                lab(xlabel, x),
                lab(ylabel, y),
                loc if isinstance(loc, str) else (float(loc[0]), float(loc[1])),
                None if color is None else self.theme.color(color),
                float(linewidth),
                size,
                float(pad),
            ),
            None,
            zorder,
        )

    def bracket(
        self,
        x0: Any,
        x1: Any,
        text: Label | float = "*",
        *,
        y: float | None = None,
        color: Color = None,
        linewidth: float | None = None,
        size: float | None = None,
        tip: float = 3.0,
        zorder: float = 2.0,
    ) -> Bracket:
        """A bracket from ``x0`` to ``x1`` with ``text`` above it, marking a
        comparison between two groups::

            ax.bar(["ctrl", "drug"], [3.1, 4.5], yerr=[0.3, 0.4])
            ax.bracket("ctrl", "drug", p)

        ``text`` may be a p-value, shown as stars: ``*`` below 0.05, ``**``
        below 0.01, ``***`` below 0.001, ``****`` below 0.0001, else ``n.s.``

        Without ``y`` the bracket sits just above the highest mark between
        ``x0`` and ``x1``, including earlier brackets, so brackets added one
        after another stack without overlapping. Add it after the data.
        ``tip`` is the length of the end ticks in points.
        """
        a, b = (float(self._coords([v], "x")[0]) for v in (x0, x1))
        label = stars(float(text)) if isinstance(text, (int, float)) else as_label(text)
        scale = self.yaxis.scale
        yr = None
        for art in self._artists:
            if not isinstance(art, Bracket):
                yr = data.union(yr, art.limits(self.xaxis.scale, scale)[1])
        lo, hi = self.yaxis.view(yr)
        t_lo, t_hi = scale.transform(min(lo, hi)), scale.transform(max(lo, hi))
        span = (t_hi - t_lo) or 1.0
        if y is None:
            top = max(
                (p for art in self._artists if (p := art.peak(min(a, b), max(a, b))) is not None),
                default=None,
            )
            t_top = t_hi if top is None else scale.transform(top)
            y = scale.inverse(t_top + 0.05 * span)
        y = float(y)
        headroom = scale.inverse(scale.transform(y) + 0.09 * span) - y
        return self._add(
            Bracket(
                a,
                b,
                y,
                label,
                headroom,
                None if color is None else self.theme.color(color),
                self.theme.spine_width if linewidth is None else float(linewidth),
                size,
                float(tip),
            ),
            None,
            zorder,
        )

    # -- text ---------------------------------------------------------------------

    def text(
        self,
        x: float,
        y: float,
        s: Label,
        *,
        size: float | None = None,
        color: Color = None,
        weight: str = "normal",
        style: str = "normal",
        ha: HAlign = "left",
        va: VAlign = "baseline",
        rotation: float = 0.0,
        coords: Literal["data", "axes"] = "data",
        zorder: float = 2.0,
    ) -> Text:
        """Text at ``(x, y)``: data coordinates, or plot-area fractions with ``coords="axes"``."""
        return self._add(
            Text(
                float(x),
                float(y),
                as_label(s),
                size,
                None if color is None else self.theme.color(color),
                weight,
                style,
                ha,
                va,
                rotation,
                coords,
            ),
            None,
            zorder,
        )

    def annotate(
        self,
        s: Label,
        xy: tuple[float, float],
        xytext: tuple[float, float] | None = None,
        *,
        arrow: bool = True,
        size: float | None = None,
        color: Color = None,
        ha: HAlign = "center",
        va: VAlign = "center",
        zorder: float = 2.0,
    ) -> Annotation:
        """Text at ``xytext`` with an arrow pointing at ``xy`` (both data coordinates)."""
        tx, ty = xytext if xytext is not None else xy
        art = Annotation(
            float(tx),
            float(ty),
            as_label(s),
            size,
            None if color is None else self.theme.color(color),
            ha=ha,
            va=va,
            target=(float(xy[0]), float(xy[1])),
            arrow=arrow and xytext is not None,
        )
        return self._add(art, None, zorder)

    # -- axes settings ---------------------------------------------------------

    def set(
        self,
        *,
        title: Label | None = None,
        title_loc: Literal["left", "center", "right"] | None = None,
        xlabel: Label | None = None,
        ylabel: Label | None = None,
        xlim: Any = _UNSET,
        ylim: Any = _UNSET,
        xscale: Any = None,
        yscale: Any = None,
        xticks: Sequence[float] | None = None,
        yticks: Sequence[float] | None = None,
        xticklabels: Sequence[Label] | None = None,
        yticklabels: Sequence[Label] | None = None,
        xformatter: Any = None,
        yformatter: Any = None,
        xtickrotation: float | str | None = None,
        xminor: int | None = None,
        yminor: int | None = None,
        xmargin: float | None = None,
        ymargin: float | None = None,
        margin: float | None = None,
        xinverted: bool | None = None,
        yinverted: bool | None = None,
        grid: bool | None = None,
        xbreak: Any = _UNSET,
        ybreak: Any = _UNSET,
        aspect: Literal["auto", "equal"] | None = None,
        frame: bool | None = None,
    ) -> Axes:
        """Configure the axes. Every argument is optional; only the ones given change.

        * ``xlim=(lo, hi)`` pins the view (either end may be ``None`` to keep it
          automatic); ``xlim=None`` returns it to autoscaling.
        * ``xscale``: ``"linear"``, ``"log"``, ``"symlog"``, ``"logit"`` or a
          `pyplotrs.scales.Scale`.
        * ``xticks``/``xticklabels`` place ticks by hand; ``xformatter`` labels them
          (a format string like ``"{x:.0%}"``, a callable, or a `pyplotrs.ticker` formatter).
        * ``xminor=n`` draws ``n`` minor intervals per major one.
        * ``margin`` (or ``xmargin``/``ymargin``) is the autoscale padding as a
          fraction of the data span (default 0.05).
        * ``xtickrotation`` is an angle, or ``"auto"`` to rotate only when labels collide.
        * ``title_loc="left"`` aligns the title with the plot's left edge, the
          usual place for a panel letter: ``set(title=pp.bold("a"), title_loc="left")``.
        * ``frame=False`` hides spines, ticks and tick labels.
        * ``ybreak=(lo, hi)`` cuts ``lo..hi`` out of the y axis, drawing the
          rest as separate pieces with break marks on the spines (a list of
          pairs makes several cuts; ``None`` removes them). Each piece is sized
          by its data span. ``xbreak`` does the same along x.

        Returns the axes, so calls can be chained.
        """
        if title is not None:
            self.title = as_label(title)
        if title_loc is not None:
            if title_loc not in ("left", "center", "right"):
                raise ValueError(
                    f"title_loc must be 'left', 'center' or 'right', got {title_loc!r}"
                )
            self._title_loc = title_loc
        for axis, lab, lim, scale, ticks, labels, fmt, minor, mrg, inv in (
            (
                self.xaxis,
                xlabel,
                xlim,
                xscale,
                xticks,
                xticklabels,
                xformatter,
                xminor,
                xmargin,
                xinverted,
            ),
            (
                self.yaxis,
                ylabel,
                ylim,
                yscale,
                yticks,
                yticklabels,
                yformatter,
                yminor,
                ymargin,
                yinverted,
            ),
        ):
            if lab is not None:
                axis.label = as_label(lab)
            if lim is not _UNSET:
                axis.limits = None if lim is None else (_opt_float(lim[0]), _opt_float(lim[1]))
            if scale is not None:
                axis.scale = _scales.get(scale)
            if ticks is not None:
                axis.ticks = [float(v) for v in ticks]
            if labels is not None:
                axis.ticklabels = [as_label(s) for s in labels]
            if fmt is not None:
                axis.formatter = _ticker.get(fmt)
            if minor is not None:
                axis.minor = int(minor)
            if mrg is not None or margin is not None:
                value = float(mrg if mrg is not None else margin)  # type: ignore[arg-type]
                if not (-0.5 < value < math.inf):
                    raise ValueError(f"margin must be greater than -0.5, got {value}")
                axis.margin = value
            if inv is not None:
                axis.inverted = bool(inv)
        if xtickrotation is not None:
            self._xtickrotation = xtickrotation if xtickrotation == "auto" else float(xtickrotation)
        if grid is not None:
            self._grid = bool(grid)
        if aspect is not None:
            if aspect not in ("auto", "equal"):
                raise ValueError(f"aspect must be 'auto' or 'equal', got {aspect!r}")
            self._aspect = aspect
        if frame is not None:
            self._frame_on = bool(frame)
        for axis, cut in ((self.xaxis, xbreak), (self.yaxis, ybreak)):
            if cut is not _UNSET:
                axis.breaks = _breaks(cut)
        return self

    def axis(self, mode: Literal["on", "off", "equal", "auto"]) -> None:
        """``"off"`` hides the frame, ``"equal"`` makes data units equal on both axes."""
        if mode in ("on", "off"):
            self._frame_on = mode == "on"
        else:
            self.set(aspect=mode)

    # -- reading back -------------------------------------------------------------

    def _data_view(self) -> tuple[Range, Range]:
        """The view ranges from this axes' own data (before figure-wide sharing)."""
        xr = yr = None
        sx: list[float] = []
        sy: list[float] = []
        host = self._host
        xscale = host.xaxis.scale if host and self._twin_of == "x" else self.xaxis.scale
        yscale = host.yaxis.scale if host and self._twin_of == "y" else self.yaxis.scale
        for a in self._artists:
            ax_, ay_ = a.limits(xscale, yscale)
            xr, yr = data.union(xr, ax_), data.union(yr, ay_)
            s1, s2 = a.sticky()
            sx += s1
            sy += s2
        return self.xaxis.view(xr, sx), self.yaxis.view(yr, sy)

    _twin_of: str = ""

    def _views(self) -> tuple[Range, Range]:
        if self.figure is not None:
            return self.figure._view_of(self)
        return self._data_view()

    def get_xlim(self) -> Range:
        """The x range that will be shown (autoscaled unless pinned)."""
        return self._views()[0]

    def get_ylim(self) -> Range:
        return self._views()[1]

    def get_xlabel(self) -> Label | None:
        return self.xaxis.label

    def get_ylabel(self) -> Label | None:
        return self.yaxis.label

    def get_xscale(self) -> str:
        return self.xaxis.scale.name

    def get_yscale(self) -> str:
        return self.yaxis.scale.name

    def get_xticks(self) -> list[float]:
        return self.xaxis.locate_view(self.get_xlim(), self.theme.unicode_minus).values

    def get_yticks(self) -> list[float]:
        return self.yaxis.locate_view(self.get_ylim(), self.theme.unicode_minus).values

    def get_xticklabels(self) -> list[Label]:
        return self.xaxis.locate_view(self.get_xlim(), self.theme.unicode_minus).labels

    def get_yticklabels(self) -> list[Label]:
        return self.yaxis.locate_view(self.get_ylim(), self.theme.unicode_minus).labels

    # -- related axes -------------------------------------------------------------

    def _twin(self, which: str) -> Axes:
        twin = Axes(self.theme, None)
        twin._host, twin._twin_of, twin._is_twin = self, which, True
        twin._cycle = self._cycle  # keep cycling colors across both
        self._twins.append((twin, which))
        return twin

    def twinx(self) -> Axes:
        """A second y axis on the right, sharing this axes' x axis."""
        return self._twin("x")

    def twiny(self) -> Axes:
        """A second x axis on top, sharing this axes' y axis."""
        return self._twin("y")

    def inset_axes(self, bounds: tuple[float, float, float, float]) -> Axes:
        """A small axes inside this one; ``bounds`` is ``(x, y, width, height)``
        as fractions of the plot area, from the lower left."""
        inset = Axes(self.theme, None)
        self._insets.append((inset, tuple(float(b) for b in bounds)))  # type: ignore[arg-type]
        return inset


class _LegendOnly(Artist):
    """An invisible artist that only contributes a legend entry."""

    def __init__(self, key: Key) -> None:
        self.key = key
        self.label = None
        self.zorder = 0.0
        self.clip = True

    def draw(self, canvas: Any, view: View) -> None:
        pass

    def legend_key(self) -> Key:
        return self.key


def _one(v: float) -> Any:
    return array("d", [float(v)])


def _breaks(value: Any) -> list[tuple[float, float]]:
    """``(lo, hi)``, a list of them, or ``None``, as sorted ranges."""
    if value is None:
        return []
    pairs = [value] if len(value) == 2 and all(isinstance(v, Real) for v in value) else value
    out = []
    for pair in pairs:
        if len(pair) != 2:
            raise ValueError(f"an axis break is a pair (lo, hi), got {pair!r}")
        lo, hi = sorted((float(pair[0]), float(pair[1])))
        if not lo < hi:
            raise ValueError(f"an axis break needs lo < hi, got {pair!r}")
        out.append((lo, hi))
    return sorted(out)


def _opt_float(v: Any) -> float | None:
    return None if v is None else float(v)


def _default_extent(w: int, h: int, origin: str) -> tuple[float, float, float, float]:
    """Pixel centers on integers; for ``"upper"`` the y axis runs downward."""
    if origin == "upper":
        return (-0.5, w - 0.5, h - 0.5, -0.5)
    return (-0.5, w - 0.5, -0.5, h - 0.5)


def _is_color_tuple(c: Any) -> bool:
    return isinstance(c, tuple) and len(c) in (3, 4) and all(isinstance(v, (int, float)) for v in c)


def _flat(a: Any) -> Any:
    if data.is_2d(a):
        values, _, _ = data.grid(a)
        return values
    return a


def _mesh_args(args: tuple[Any, ...]) -> tuple[list[float], list[float], Any, int, int]:
    """``(Z)`` or ``(x, y, Z)`` as x coordinates, y coordinates and the grid."""
    if len(args) == 1:
        values, w, h = data.grid(args[0])
        return [float(i) for i in range(w)], [float(i) for i in range(h)], values, w, h
    if len(args) != 3:
        raise TypeError("expected (Z) or (x, y, Z)")
    x, y, z = args
    values, w, h = data.grid(z)
    xc = [float(v) for v in (data.f64(x[0]) if data.is_2d(x) else data.f64(x))]
    yc = [float(v) for v in (data.f64([r[0] for r in y]) if data.is_2d(y) else data.f64(y))]
    if len(xc) not in (w, w + 1) or len(yc) not in (h, h + 1):
        raise ValueError(
            f"x and y must match Z's shape {h}x{w} (as centers or edges); "
            f"got {len(xc)} x and {len(yc)} y values"
        )
    return xc, yc, values, w, h


def _rgb_image(z: Any) -> tuple[bytes, int, int] | None:
    """``(rgba, w, h)`` if ``z`` is an ``(h, w, 3|4)`` image, else None."""
    shape = getattr(z, "shape", None)
    if shape is not None:
        if len(shape) != 3:
            return None
        h, w, c = shape
        flat = z.reshape(-1)
        is_float = getattr(z.dtype, "kind", "") == "f"
        vals = (flat * 255.0 if is_float else flat).clip(0, 255).astype("uint8").tolist()
    else:
        try:
            first = z[0][0]
        except (TypeError, IndexError):
            return None
        if not hasattr(first, "__len__"):
            return None
        h, w, c = len(z), len(z[0]), len(first)
        is_float = any(isinstance(v, float) for v in first)
        vals = [
            min(255, max(0, round(v * 255 if is_float else v)))
            for row in z
            for px in row
            for v in px
        ]
    if c not in (3, 4):
        raise ValueError(f"an RGB image needs 3 or 4 channels, got {c}")
    if c == 3:
        out = bytearray()
        for i in range(0, len(vals), 3):
            out += bytes((vals[i], vals[i + 1], vals[i + 2], 255))
        return bytes(out), w, h
    return bytes(vals), w, h


def _as_mappable(artist: Any, cmap: _colormaps.Colormap, norm: _norms.Norm, alpha: float) -> None:
    artist.cmap, artist.norm, artist.alpha = cmap, norm, alpha
