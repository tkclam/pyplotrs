"""The 2D :class:`Axes`: a coordinate system plus a stack of marks.

Also holds :class:`_AxesBase` - the contract every axes kind shares (colour
cycling, the mark ordering rule, legends, the ``get_*`` readers) - and
:class:`_Mappable`, the handle a colormapped mark returns for
:meth:`Figure.colorbar`.
"""

from __future__ import annotations

import math
from array import array

from . import _pyplotrs_core as _core
from . import colormaps as _colormaps
from . import norms as _norms
from . import scales as _scales
from . import ticker as _ticker
from . import theme as _theme
from .theme import Theme

from ._const import (
    _AXIS_LABEL_GAP,
    _CBAR_GAP,
    _CBAR_TICK_GAP,
    _CBAR_TICK_LEN,
    _CBAR_WIDTH,
    _DATA_PAD,
    _ELLIPSE_N,
    _LEGEND_PROBE_POINTS,
    _TICK_LABEL_GAP,
    _TICK_LENGTH,
    _TITLE_GAP,
)
from ._util import (
    _RangeAcc,
    _as_seq,
    _auto_levels,
    _boxstats,
    _clip_segment,
    _concat,
    _edges_from_centers,
    _field_args,
    _flatten2d,
    _interp_coord,
    _is_2d,
    _is_uniform,
    _patch_bbox,
    _step_points,
    _streamlines,
    _subdivide,
    _to_f64,
    _to_f64_grid,
    _with_alpha,
)
from ._draw import (
    _colorbar_ticks,
    _colormap_lut,
    _dash_for,
    _draw_arrow,
    _draw_hatch,
    _draw_legend_box,
    _draw_marker,
    _draws_line,
    _font,
    _measure_legend,
    _place_text,
    _rgba_values,
    _text,
    _th,
    _tw,
)
from ._layout import _Proj, _Rect, _layout_cell

#: Alias so methods taking a ``range=`` keyword can still reach the builtin.
_irange = range


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

    def _ordered_marks(self, marks=None) -> list[dict]:
        """Marks in draw order: ascending ``zorder``, then insertion order.

        The sort is stable, so marks sharing a ``zorder`` - which is all of them
        by default - keep the order they were added in. Insertion order stays
        the primary model, as it is the one you can read off the code; ``zorder``
        is the escape hatch for when a mark has to sit above something added
        after it.
        """
        seq = self._marks if marks is None else marks
        return sorted(seq, key=lambda m: m.get("zorder", 0.0))

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

    def get_title(self) -> str | None:
        """This axes' title, or ``None``. Lives on the base class because all
        three axes kinds have one - the rest of the getters are per-kind."""
        return self._title

    def get_legend_handles_labels(self) -> tuple[list[dict], list[str]]:
        """``(handles, labels)`` for the labelled marks, in draw order.

        A handle is the mark's own dict: pyplotrs has no Artist objects, and
        the mark *is* what the legend key gets drawn from."""
        entries = self._legend_entries()
        return list(entries), [e["label"] for e in entries]

    def legend(self, *, loc: str | None = None, ncol: int = 1,
               title: str | None = None, frameon: bool = True,
               fontsize: float | None = None):
        """Enable an auto-legend over this axes' labelled marks.

        ``loc`` is ``best`` / ``upper right`` / ``upper left`` / ``lower right``
        / ``lower left`` / ``upper center`` / ``lower center``; ``None`` uses
        this axes class's default. ``best`` picks the corner that overlaps the
        data least.

        ``ncol`` lays the keys out in that many columns, filled down then
        across - the usual fix for a legend tall enough to crowd the data.
        ``title`` puts a heading above the keys, ``frameon=False`` drops the
        box and its background, and ``fontsize`` overrides ``theme.legend_size``
        for this legend only.
        """
        self._legend = {
            "loc": self._LEGEND_DEFAULT_LOC if loc is None else loc,
            "ncol": int(ncol), "title": title, "frameon": bool(frameon),
            "fontsize": None if fontsize is None else float(fontsize),
        }
        return self

    def _legend_entries(self) -> list[dict]:
        """The labelled marks to draw legend keys for.

        3D and polar marks carry projection-specific fields, so they are
        normalized here into the line/scatter shapes the shared glyph drawer
        understands. Colormapped kinds (surface, trisurf, contour3d) carry no
        single data colour, so they store a representative swatch colour (their
        colormap's midpoint, or the middle level) at mark-construction time for
        exactly this purpose. :class:`Axes` overrides this to pass its marks
        through untouched, since its glyph drawer has real branches for
        bar/hist/fill swatches that this normalization would flatten into plain
        rules.
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
                            "linewidth": m.get("linewidth", 1.5),
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
        # Autoscale margin as a fraction of the data span; None => _DATA_PAD.
        self._xmargin: float | None = None
        self._ymargin: float | None = None
        # Descending view without pinning numbers (see ``_ranges``).
        self._xinverted = False
        self._yinverted = False
        # Minor ticks. Non-linear scales subdivide on their own; on a linear
        # axis there is no canonical subdivision, so it is opt-in and the count
        # is how many minor intervals fill one major one.
        self._xminor: int = 0
        self._yminor: int = 0
        # Per-axes tick styling, overriding the theme when not None.
        self._tick_direction: str = "out"
        self._tick_length: float | None = None
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
        # Width a secondary y axis on the right claimed out of the shared cbar
        # band, recomputed by `_bands` on every render.
        self._sec_right_w: float = 0.0
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
             markersize: float = 5.0, simplify: bool = True, zorder: float = 0.0) -> "Axes":
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
            "zorder": float(zorder),
            "kind": "line",
            "xs": self._coords(xs, "x"),
            "ys": self._coords(ys, "y"),
            "label": label,
            "color": self._mark_color(color, alpha),
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle,
            "marker": marker,
            "markersize": float(markersize),
            "simplify": bool(simplify),
        })
        return self

    def semilogx(self, xs, ys, **kwargs) -> "Axes":
        """:meth:`line` with the x-axis log-scaled - matplotlib's ``ax.semilogx``.

        A thin wrapper: ``ax.set(xscale="log")`` then ``ax.line(xs, ys, **kwargs)``.
        """
        self.set(xscale="log")
        return self.line(xs, ys, **kwargs)

    def semilogy(self, xs, ys, **kwargs) -> "Axes":
        """:meth:`line` with the y-axis log-scaled - matplotlib's ``ax.semilogy``."""
        self.set(yscale="log")
        return self.line(xs, ys, **kwargs)

    def loglog(self, xs, ys, **kwargs) -> "Axes":
        """:meth:`line` with both axes log-scaled - matplotlib's ``ax.loglog``."""
        self.set(xscale="log", yscale="log")
        return self.line(xs, ys, **kwargs)

    def scatter(self, xs, ys, *, label: str | None = None, color=None,
                markersize: float | None = None, alpha: float = 1.0,
                marker: str = "o", edgecolor=None, edgewidth: float = 1.0,
                size: float | None = None,
                c=None, cmap="viridis", norm=None, vmin: float | None = None,
                vmax: float | None = None, zorder: float = 0.0):
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
            "zorder": float(zorder),
            "kind": "scatter",
            "xs": xs,
            "ys": ys,
            "label": label,
            # A colormapped scatter's per-point colours replace this, but it is
            # still the legend swatch and the fallback, so it must follow the theme.
            "color": (self._mark_color(color, alpha) if c is None
                      else self._theme.text_color),
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
            alpha: float = 1.0, label: str | None = None, edgecolor=None, zorder: float = 0.0) -> "Axes":
        """Draw vertical bars of the given ``height`` at positions ``x``. ``x``
        may be strings (categories), which set a categorical x-axis."""
        xs = self._coords(x, "x")
        heights = [float(v) for v in height]
        self._marks.append({
            "zorder": float(zorder),
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
             label: str | None = None, range=None, density: bool = False, zorder: float = 0.0) -> "Axes":
        """Bin ``data`` into ``bins`` equal-width bins and draw the histogram.

        The binning loop runs in Rust (``_core.histogram``), matching what
        ``hist2d`` already did."""
        vals = _to_f64(data)
        if not len(vals):
            vals = array("d", (0.0, 1.0))
        span = (float(range[0]), float(range[1])) if range else None
        edges, counts = _core.histogram(vals, max(int(bins), 1), span, bool(density))
        self._marks.append({
            "zorder": float(zorder),
            "kind": "hist",
            "edges": edges,
            "counts": counts,
            "color": self._mark_color(color, alpha),
            "label": label,
        })
        return self

    def fill_between(self, xs, y1, y2=0.0, *, color=None, alpha: float = 0.3,
                     label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Fill the band between ``y1`` and ``y2`` across ``xs``."""
        xs = self._coords(xs, "x")
        self._marks.append({
            "zorder": float(zorder),
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
                      label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Fill the band between ``x1`` and ``x2`` across ``ys`` - the transpose
        of :meth:`fill_between`, for bands around a horizontal profile."""
        ys = self._coords(ys, "y")
        self._marks.append({
            "zorder": float(zorder),
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
               label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Horizontal line segments at each ``y``, spanning ``xmin`` to ``xmax``
        in **data** coordinates.

        Unlike :meth:`axhline`, which spans a fraction of the axes and is a
        guide, these are data and participate in autoscaling. Each argument may
        be a scalar or a sequence; scalars broadcast."""
        return self._add_lines("h", y, xmin, xmax, color, linewidth, linestyle, label,
                               alpha, zorder)

    def vlines(self, x, ymin, ymax, *, color=None, linewidth: float | None = None,
               alpha: float = 1.0, linestyle: str = "solid",
               label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Vertical line segments at each ``x``, spanning ``ymin`` to ``ymax`` in
        **data** coordinates (see :meth:`hlines`)."""
        return self._add_lines("v", x, ymin, ymax, color, linewidth, linestyle, label,
                               alpha, zorder)

    def _add_lines(self, orient, pos, lo, hi, color, linewidth, linestyle, label,
                   alpha=1.0, zorder: float = 0.0) -> "Axes":
        """Shared body of :meth:`hlines` / :meth:`vlines`."""
        pos = _to_f64(pos if hasattr(pos, "__len__") else [pos])
        n = len(pos)
        lo = _to_f64(_as_seq(lo, n))
        hi = _to_f64(_as_seq(hi, n))
        self._marks.append({
            "zorder": float(zorder),
            "kind": "lines", "orient": orient, "pos": pos, "lo": lo, "hi": hi,
            "color": self._mark_color(color, alpha),
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle, "label": label,
        })
        return self

    def errorbar(self, xs, ys, *, yerr=None, xerr=None, color=None, label: str | None = None,
                 marker: str | None = "o", markersize: float = 5.0,
                 linewidth: float | None = None, alpha: float = 1.0,
                 capsize: float = 3.0, linestyle: str = "solid", zorder: float = 0.0) -> "Axes":
        """Plot ``(xs, ys)`` with symmetric ``yerr``/``xerr`` error bars."""
        xs = [float(x) for x in xs]
        ys = [float(y) for y in ys]
        n = len(xs)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "errorbar",
            "xs": xs,
            "ys": ys,
            "yerr": _as_seq(yerr, n) if yerr is not None else None,
            "xerr": _as_seq(xerr, n) if xerr is not None else None,
            "color": self._mark_color(color, alpha),
            "label": label,
            "marker": marker,
            "markersize": float(markersize),
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
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
             alpha: float = 1.0, label: str | None = None, edgecolor=None, zorder: float = 0.0) -> "Axes":
        """Horizontal bars of the given ``width`` at vertical positions ``y``.
        ``y`` may be strings (categories), which set a categorical y-axis."""
        ys = self._coords(y, "y")
        self._marks.append({
            "zorder": float(zorder),
            "kind": "barh", "ys": ys, "widths": [float(v) for v in width],
            "lefts": _as_seq(left, len(ys)), "height": float(height),
            "color": self._mark_color(color, alpha), "label": label,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
        })
        return self

    # -- statistical --------------------------------------------------------

    def boxplot(self, data, *, positions=None, widths: float = 0.5, color=None,
                showfliers: bool = True, alpha: float = 1.0,
                label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Box-and-whisker plot. ``data`` is a list of numeric arrays (one box
        each); ``positions`` default to ``1..n``."""
        groups = data if _is_2d(data) else [data]
        stats = [_boxstats([float(v) for v in g]) for g in groups]
        positions = ([float(p) for p in positions] if positions is not None
                     else [float(i + 1) for i in range(len(groups))])
        self._marks.append({
            "zorder": float(zorder),
            "kind": "boxplot", "stats": stats, "positions": positions,
            "width": float(widths), "color": self._mark_color(color, alpha),
            "showfliers": showfliers, "label": label,
        })
        return self

    def violinplot(self, data, *, positions=None, widths: float = 0.5, color=None,
                   points: int = 128, alpha: float = 1.0,
                   label: str | None = None, zorder: float = 0.0) -> "Axes":
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
            "zorder": float(zorder),
            "kind": "violin", "violins": violins, "positions": positions,
            "width": float(widths), "color": self._mark_color(color, alpha),
            "label": label,
        })
        return self

    def pie(self, sizes, *, labels=None, colors=None, startangle: float = 90.0,
            radius: float = 1.0, alpha: float = 1.0, zorder: float = 0.0) -> "Axes":
        """Pie chart of ``sizes`` (auto-normalized). Turns the frame off and fixes
        an equal aspect so wedges stay circular.

        This is the one mark with no scalar ``label``: its labels are per-wedge,
        so they come from ``labels`` - which is also what feeds :meth:`legend`.
        """
        vals = [float(v) for v in sizes]
        total = sum(vals) or 1.0
        wedges = []
        ang = math.radians(startangle)
        for i, v in enumerate(vals):
            sweep = 2.0 * math.pi * v / total
            col = colors[i] if colors else None
            wedges.append({"a0": ang, "a1": ang + sweep,
                           "color": self._mark_color(col, alpha),
                           "label": labels[i] if labels else None})
            ang += sweep
        self._marks.append({"zorder": float(zorder), "kind": "pie", "wedges": wedges, "radius": float(radius)})
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
               origin: str = "upper", alpha: float = 1.0,
               label: str | None = None, zorder: float = 0.0) -> "_Mappable":
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
            "zorder": float(zorder),
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
            "alpha": float(alpha),
            "label": label,
            # A colormapped mark has no single colour, so its legend key is the
            # colormap's midpoint - the one swatch that reads as "this map".
            "color": _with_alpha(cm(0.5), alpha),
        })
        return _Mappable(self, cm, lo, hi, norm=(nrm if norm_code != "linear" else None))

    # -- step / stair family ------------------------------------------------

    def step(self, xs, ys, *, where: str = "pre", color=None,
             linewidth: float | None = None, alpha: float = 1.0,
             linestyle: str = "solid", label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Step plot through ``(xs, ys)``; ``where`` is ``pre``/``post``/``mid``."""
        px, py = _step_points(list(_to_f64(xs)), list(_to_f64(ys)), where)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "line", "xs": _to_f64(px), "ys": _to_f64(py), "label": label,
            "color": self._mark_color(color, alpha),
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle, "marker": None, "markersize": 5.0, "simplify": False,
        })
        return self

    def stairs(self, values, edges=None, *, color=None, linewidth: float | None = None,
               alpha: float = 1.0, fill: bool = False, baseline: float = 0.0,
               label: str | None = None, zorder: float = 0.0) -> "Axes":
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
                "zorder": float(zorder),
                "kind": "fill", "xs": xs, "y1": top,
                "y2": _to_f64(_as_seq(baseline, len(xs))),
                "color": self._next_color(color), "alpha": 0.3, "label": label,
            })
        else:
            px = array("d", [edges[0]]) + xs + array("d", [edges[-1]])
            py = array("d", [baseline]) + top + array("d", [baseline])
            self._marks.append({
                "zorder": float(zorder),
                "kind": "line", "xs": px, "ys": py, "label": label,
                "color": self._mark_color(color, alpha),
                "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
                "linestyle": "solid", "marker": None, "markersize": 5.0, "simplify": False,
            })
        return self

    def stem(self, xs, ys, *, bottom: float = 0.0, color=None, alpha: float = 1.0,
             marker: str = "o", markersize: float = 5.0,
             label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Stem plot: a vertical line from ``bottom`` to each ``(x, y)`` topped by
        a marker, with a baseline."""
        self._marks.append({
            "zorder": float(zorder),
            "kind": "stem", "xs": self._coords(xs, "x"), "ys": self._coords(ys, "y"),
            "bottom": float(bottom), "color": self._mark_color(color, alpha),
            "marker": marker, "markersize": float(markersize), "label": label,
        })
        return self

    def broken_barh(self, xranges, yrange, *, color=None, edgecolor=None,
                    alpha: float = 1.0, label: str | None = None,
                    zorder: float = 0.0) -> "Axes":
        """Horizontal bars from ``(xstart, width)`` pairs, all spanning the
        vertical ``yrange = (ymin, height)`` (e.g. Gantt / interval plots)."""
        self._marks.append({
            "zorder": float(zorder),
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
                  color=None, linewidth: float | None = None, alpha: float = 1.0,
                  label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Raster of event marks. ``positions`` is a 1D array or a list of rows;
        each row is offset by ``lineoffsets`` and drawn ``linelengths`` long
        (perpendicular to ``orientation``)."""
        rows = positions if len(positions) and _is_2d(positions) else [positions]
        rows = [_to_f64(r) for r in rows]
        self._marks.append({
            "zorder": float(zorder),
            "kind": "eventplot", "rows": rows, "orientation": orientation,
            "offset": float(lineoffsets), "length": float(linelengths),
            "color": self._mark_color(color, alpha), "label": label,
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
        })
        return self

    # -- 2D binning ---------------------------------------------------------

    def hist2d(self, xs, ys, *, bins=10, range=None, cmap="viridis", norm=None,
               vmin: float | None = None, vmax: float | None = None,
               alpha: float = 1.0, label: str | None = None,
               zorder: float = 0.0) -> "_Mappable":
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
                           extent=(xlo, xhi, ylo, yhi), origin="lower",
                           alpha=alpha, label=label, zorder=zorder)

    def hexbin(self, xs, ys, *, gridsize: int = 30, cmap="viridis", norm=None,
               vmin: float | None = None, vmax: float | None = None,
               alpha: float = 1.0, label: str | None = None,
               zorder: float = 0.0) -> "_Mappable":
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
        if alpha < 1.0:
            colors = [_with_alpha(c, alpha) for c in colors]
        self._marks.append({
            "zorder": float(zorder),
            "kind": "hexbin", "centers": [(cx, cy) for cx, cy, _ in hexes],
            "colors": colors, "offsets": offs, "label": label,
            "color": _with_alpha(cm(0.5), alpha),
        })
        return _Mappable(self, cm, nrm.vmin, nrm.vmax,
                         norm=(nrm if type(nrm) is not _norms.Normalize else None))

    # -- field / grid -------------------------------------------------------

    def pcolormesh(self, *args, cmap="viridis", norm=None, vmin: float | None = None,
                   vmax: float | None = None, alpha: float = 1.0,
                   label: str | None = None, zorder: float = 0.0) -> "_Mappable":
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
                               extent=extent, origin="lower",
                               alpha=alpha, label=label, zorder=zorder)
        cm, nrm, colors = self._map_colors(
            [v for row in Z for v in row], cmap, norm, vmin, vmax)
        if alpha < 1.0:
            colors = [_with_alpha(c, alpha) for c in colors]
        # Cell edges from coordinate midpoints (irregular quad mesh).
        xe = _edges_from_centers(xc)
        ye = _edges_from_centers(yc)
        quads = []
        for iy in _irange(h):
            for ix in _irange(w):
                quads.append((xe[ix], xe[ix + 1], ye[iy], ye[iy + 1],
                              colors[iy * w + ix]))
        self._marks.append({"zorder": float(zorder),
                            "kind": "quadmesh", "quads": quads, "label": label,
                            "color": _with_alpha(cm(0.5), alpha),
                            "extent": (xe[0], xe[-1], ye[0], ye[-1])})
        return _Mappable(self, cm, nrm.vmin, nrm.vmax)

    def contour(self, *args, levels=None, colors=None, cmap=None,
                linewidth: float | None = None, alpha: float = 1.0,
                label: str | None = None, zorder: float = 0.0) -> "Axes":
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
        if alpha < 1.0:
            lcolors = [_with_alpha(c, alpha) for c in lcolors]
        self._marks.append({
            "zorder": float(zorder),
            "kind": "contour", "segs": segs, "xcoords": xc, "ycoords": yc,
            "colors": lcolors, "label": label,
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
            # Legend key: the middle level's colour stands for the line set.
            "color": lcolors[len(lcolors) // 2] if lcolors else self._theme.palette[0],
            "extent": (min(xc), max(xc), min(yc), max(yc)),
        })
        return self

    def contourf(self, *args, levels=None, cmap="viridis", norm=None,
                 vmin: float | None = None, vmax: float | None = None,
                 upsample: int = 6, alpha: float = 1.0,
                 label: str | None = None, zorder: float = 0.0) -> "_Mappable":
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
                         for b in _with_alpha(cm(nrm(0.5 * (edges[k] + edges[k + 1]))), alpha))
        img, uw, uh = _core.contourf_image(flat, w, h, edges, band_lut, upsample)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "contourf", "img": bytes(img), "uw": uw, "uh": uh,
            "label": label, "color": _with_alpha(cm(0.5), alpha),
            "extent": (min(xc), max(xc), min(yc), max(yc)),
        })
        return _Mappable(self, cm, edges[0], edges[-1], norm=nrm)

    def pcolor(self, *args, **kwargs) -> "_Mappable":
        """Alias of :meth:`pcolormesh`.

        matplotlib distinguishes the two (``pcolor`` returns a masked-aware
        ``PolyCollection``, ``pcolormesh`` a faster ``QuadMesh``); pyplotrs has
        only the fast path, and it already chooses per-cell quads over the
        image path whenever the grid is irregular, so the distinction has
        nothing left to express."""
        return self.pcolormesh(*args, **kwargs)

    def matshow(self, data, **kwargs) -> "_Mappable":
        """Display a matrix with row 0 at the top and one cell per entry.

        :meth:`imshow` with the conventions a *matrix* wants rather than the
        ones an *image* wants: origin at the top-left and an equal aspect, so
        cells stay square."""
        kwargs.setdefault("origin", "upper")
        self._aspect = "equal"
        return self.imshow(data, **kwargs)

    def spy(self, data, *, markersize: float = 4.0, color=None,
            marker: str = "s", alpha: float = 1.0, label: str | None = None,
            zorder: float = 0.0) -> "Axes":
        """Plot the sparsity pattern of ``data``: a marker wherever an entry is
        nonzero, row 0 at the top."""
        rows = list(data)
        pts_x: list[float] = []
        pts_y: list[float] = []
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                if v:
                    pts_x.append(float(j))
                    pts_y.append(float(i))
        self.scatter(pts_x, pts_y, markersize=markersize, color=color,
                     marker=marker, alpha=alpha, label=label, zorder=zorder)
        # Matrix orientation: row 0 on top, and square cells.
        nrows = len(rows)
        ncols = max((len(r) for r in rows), default=0)
        self._xlim = (-0.5, ncols - 0.5)
        self._ylim = (nrows - 0.5, -0.5)
        self._aspect = "equal"
        return self

    def stackplot(self, x, *ys, labels=None, colors=None, alpha: float = 1.0,
                  baseline: float = 0.0, zorder: float = 0.0) -> "Axes":
        """Stacked area plot: each series in ``ys`` is filled on top of the
        cumulative total of the ones before it.

        ``ys`` may be passed as separate arrays or as one sequence of arrays,
        matching ``stackplot(x, a, b)`` and ``stackplot(x, [a, b])``."""
        if len(ys) == 1 and _is_2d(ys[0]):
            ys = tuple(ys[0])
        xs = _to_f64(x)
        n = len(xs)
        lower = [float(baseline)] * n
        for i, series in enumerate(ys):
            vals = _as_seq(series, n)
            upper = [lo + v for lo, v in zip(lower, vals)]
            self.fill_between(xs, upper, lower, alpha=alpha, zorder=zorder,
                              color=(colors[i % len(colors)] if colors else None),
                              label=(labels[i] if labels and i < len(labels) else None))
            lower = upper
        return self

    def quiver(self, x, y, u, v, *, scale: float = 1.0, color=None,
               linewidth: float | None = None, alpha: float = 1.0,
               label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Arrow field: an arrow at each ``(x, y)`` pointing along ``(u, v)``.

        ``scale`` multiplies the vectors in data space (so the arrow tip lands
        at ``x + u*scale``), and the arrowheads are sized in points. ``x``/``y``
        may be 1D lists or 2D grids, as long as all four agree in shape."""
        xs, ys, us, vs = (_to_f64(_flatten2d(a)) for a in (x, y, u, v))
        if not (len(xs) == len(ys) == len(us) == len(vs)):
            raise ValueError(
                f"quiver needs x, y, u, v of equal length; got "
                f"{len(xs)}, {len(ys)}, {len(us)}, {len(vs)}"
            )
        self._marks.append({
            "zorder": float(zorder),
            "kind": "quiver", "xs": xs, "ys": ys, "us": us, "vs": vs,
            "scale": float(scale), "color": self._mark_color(color, alpha),
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
            "label": label,
        })
        return self

    def streamplot(self, x, y, u, v, *, density: float = 1.0, color=None,
                   linewidth: float | None = None, alpha: float = 1.0,
                   maxlength: float = 4.0, arrows: bool = True,
                   label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Streamlines of the vector field ``(u, v)`` sampled on the grid
        ``(x, y)``.

        ``x``/``y`` are the 1D coordinates of the grid columns/rows and
        ``u``/``v`` are 2D ``len(y) x len(x)`` grids. Seeds are laid on a
        ``density``-scaled lattice and integrated both ways with RK4;
        ``maxlength`` caps each streamline's arc length in grid cells.
        ``arrows`` puts a direction head at each streamline's midpoint - a
        streamline is otherwise unsigned, and which way the flow runs is
        usually the point of drawing one."""
        xc = [float(t) for t in x]
        yc = [float(t) for t in y]
        gu = [[float(t) for t in row] for row in u]
        gv = [[float(t) for t in row] for row in v]
        h, w = len(gu), len(gu[0]) if gu else 0
        if h < 2 or w < 2:
            raise ValueError("streamplot needs a grid of at least 2x2")
        col = self._mark_color(color, alpha)
        lw = self._theme.line_width if linewidth is None else float(linewidth)
        heads: list[tuple[float, float, float, float]] = []
        first = True
        for px, py in _streamlines(xc, yc, gu, gv, density, maxlength):
            if len(px) < 2:
                continue
            # Only the first streamline carries the label, so one legend key
            # stands for the whole field rather than one per line.
            self.line(px, py, color=col, linewidth=lw, simplify=False,
                      zorder=zorder, label=(label if first else None))
            first = False
            if arrows and len(px) >= 3:
                k = len(px) // 2
                dxs, dys = px[k] - px[k - 1], py[k] - py[k - 1]
                mag = math.hypot(dxs, dys)
                if mag > 0.0:
                    heads.append((px[k - 1], py[k - 1], dxs / mag, dys / mag))
        if heads:
            # One quiver mark for every head, so the arrows cost a single mark
            # rather than one per streamline. The shaft is a hair long enough
            # to carry the head and no more - the line underneath is the path.
            span = max(abs(xc[-1] - xc[0]), abs(yc[-1] - yc[0])) or 1.0
            self._marks.append({
                "zorder": float(zorder),
                "kind": "quiver",
                "xs": array("d", [p[0] for p in heads]),
                "ys": array("d", [p[1] for p in heads]),
                "us": array("d", [p[2] for p in heads]),
                "vs": array("d", [p[3] for p in heads]),
                "scale": span * 0.012, "color": col, "linewidth": lw,
                "label": None,
            })
        return self

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
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
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
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
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
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
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

    def fill(self, x, y, *, facecolor=None, edgecolor=None, linewidth: float = 1.0,
             linestyle: str = "solid", alpha: float = 1.0,
             hatch: str | None = None) -> "Axes":
        """Fill the closed polygon through ``(x, y)`` - matplotlib's ``ax.fill``.

        A thin wrapper over :meth:`polygon` taking parallel ``x``/``y`` arrays
        instead of a list of point pairs; ``facecolor`` cycles the palette like
        a data mark when omitted. It is a patch like :meth:`polygon` (drawn
        over the data, outside the zorder/legend contract the marks share) -
        call :meth:`polygon` directly for its other knobs.
        """
        xs = _to_f64(x)
        ys = _to_f64(y)
        if len(xs) != len(ys):
            raise ValueError(f"fill needs x and y of equal length; got {len(xs)}, {len(ys)}")
        return self.polygon(list(zip(xs, ys)), facecolor=facecolor, edgecolor=edgecolor,
                            linewidth=linewidth, linestyle=linestyle, alpha=alpha, hatch=hatch)

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
        if location not in ("top", "bottom"):
            raise ValueError(
                f"secondary_xaxis location must be 'top' or 'bottom', got {location!r}"
            )
        self._secondary.append({"axis": "x", "loc": location, "functions": functions,
                                "label": label})
        return self

    def secondary_yaxis(self, location: str, *, functions=None,
                        label: str | None = None) -> "Axes":
        """A functional secondary y-axis at ``location`` (``"left"``/``"right"``)."""
        if location not in ("left", "right"):
            raise ValueError(
                f"secondary_yaxis location must be 'left' or 'right', got {location!r}"
            )
        self._secondary.append({"axis": "y", "loc": location, "functions": functions,
                                "label": label})
        return self

    def _has_extras(self) -> bool:
        return bool(self._twinx or self._twiny or self._insets or self._secondary)

    # -- public API: chrome -------------------------------------------------

    # -- annotations --------------------------------------------------------

    def text(self, x, y, s, *, color=None, fontsize: float | None = None,
             weight: str = "normal", style: str = "normal",
             ha: str = "left", va: str = "baseline",
             rotation: float = 0.0) -> "Axes":
        """Draw ``s`` at data coordinates ``(x, y)``.

        ``ha`` is ``left``/``center``/``right``; ``va`` is
        ``baseline``/``bottom``/``center``/``top``. ``s`` may contain ``$...$``
        math. ``color`` defaults to the theme text colour. ``weight`` is
        ``normal`` or ``bold`` and ``style`` is ``normal`` or ``italic``; both
        select a real face of the body family, so the glyphs are genuinely bold
        or italic rather than synthetically slanted.

        ``rotation`` turns the text counter-clockwise by that many degrees
        about its anchor, and it stays selectable text in PDF/SVG - the
        rotation is a group transform in the IR, not baked-out paths."""
        self._annotations.append({
            "kind": "text", "x": float(x), "y": float(y), "s": str(s),
            "color": self._theme.text_color if color is None else self._theme.resolve(color),
            "size": None if fontsize is None else float(fontsize),
            "font": _font(weight, style), "ha": ha, "va": va,
            "rotation": float(rotation),
        })
        return self

    def annotate(self, text, xy, *, xytext=None, color=None, fontsize: float | None = None,
                 weight: str = "normal", style: str = "normal",
                 arrow: bool = True, ha: str = "left", va: str = "bottom",
                 rotation: float = 0.0) -> "Axes":
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
            "rotation": float(rotation),
        })
        return self

    def set(self, *, title=None, xlabel=None, ylabel=None, xlim=None, ylim=None,
            xscale=None, yscale=None, xticks=None, yticks=None,
            xticklabels=None, yticklabels=None, xformatter=None, yformatter=None,
            grid=None, aspect=None, xmargin=None, ymargin=None, margin=None,
            xinverted=None, yinverted=None, xminor=None, yminor=None, minor=None,
            tick_direction=None, tick_length=None) -> "Axes":
        """Set any combination of title, axis labels, view limits, axis scales,
        and tick/grid/aspect/margin controls.

        ``xscale``/``yscale`` accept ``"linear"`` (default), ``"log"``,
        ``"symlog"``, ``"logit"`` or a :class:`pyplotrs.scales.Scale`.
        ``xticks``/``yticks`` pin tick positions; ``xticklabels``/``yticklabels``
        give matching label strings. ``xformatter``/``yformatter`` accept a
        :class:`pyplotrs.ticker.Formatter`, a ``"{x:.2f}"`` template, or a
        callable. ``grid`` overrides the theme grid; ``aspect="equal"`` equalizes
        the data-unit scale on both axes.

        Passing ``xlim="auto"`` (or ``ylim``) clears a previously pinned limit
        and returns that axis to autoscaling - ``None`` means "leave alone", so
        it cannot double as a reset.

        ``xmargin``/``ymargin`` (or ``margin`` for both) set the autoscale
        padding as a fraction of the data span, replacing the 5% default;
        ``0`` gives limits tight to the data. ``xinverted``/``yinverted``
        make an axis descend without pinning numbers, which composes with
        autoscaling. ``xminor``/``yminor`` (or ``minor``) put that many minor
        intervals inside each major one - non-linear scales already subdivide
        themselves, so this is for linear axes. ``tick_direction`` is ``"out"``
        (default) or ``"in"``, and ``tick_length`` overrides the tick mark
        length in points."""
        if title is not None:
            self._title = title
        if xlabel is not None:
            self._xlabel = xlabel
        if ylabel is not None:
            self._ylabel = ylabel
        if xlim is not None:
            self._xlim = None if xlim == "auto" else (float(xlim[0]), float(xlim[1]))
        if ylim is not None:
            self._ylim = None if ylim == "auto" else (float(ylim[0]), float(ylim[1]))
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
        if margin is not None:
            xmargin = margin if xmargin is None else xmargin
            ymargin = margin if ymargin is None else ymargin
        if xmargin is not None:
            self._xmargin = float(xmargin)
        if ymargin is not None:
            self._ymargin = float(ymargin)
        if xinverted is not None:
            self._xinverted = bool(xinverted)
        if yinverted is not None:
            self._yinverted = bool(yinverted)
        if minor is not None:
            xminor = minor if xminor is None else xminor
            yminor = minor if yminor is None else yminor
        if xminor is not None:
            self._xminor = int(xminor)
        if yminor is not None:
            self._yminor = int(yminor)
        if tick_direction is not None:
            if tick_direction not in ("in", "out"):
                raise ValueError(
                    f'tick_direction must be "in" or "out", got {tick_direction!r}')
            self._tick_direction = tick_direction
        if tick_length is not None:
            self._tick_length = float(tick_length)
        return self

    # -- reading an axes back -----------------------------------------------
    #
    # Writing is `set(**kwargs)`; reading is these. The split is deliberate:
    # there is one way to change an axes and one way to interrogate it, rather
    # than matplotlib's parallel `get_x`/`set_x` pairs *plus* a bulk `set`.
    #
    # Every getter reports the **effective** value - what will actually be
    # drawn - not just what was explicitly set. `get_xlim()` on an axes with no
    # explicit limit returns the autoscaled range, and `get_xticks()` returns
    # the located ticks, because "what did I set" is already visible in the
    # calling code and "what will I get" is not.

    def get_xlim(self) -> tuple[float, float]:
        """Effective x limits: the explicit ``xlim`` if set, else autoscaled -
        and unified across the row when the figure was built ``sharex=True``."""
        return self._effective_ranges()[0]

    def get_ylim(self) -> tuple[float, float]:
        """Effective y limits (see :meth:`get_xlim`; ``sharey`` unifies these)."""
        return self._effective_ranges()[1]

    def get_xlabel(self) -> str | None:
        return self._xlabel

    def get_ylabel(self) -> str | None:
        return self._ylabel

    def get_xscale(self) -> str:
        """The x scale's name (``"linear"``, ``"log"``, ``"symlog"``, ...)."""
        return getattr(self._xscale, "name", self._xscale.code)

    def get_yscale(self) -> str:
        return getattr(self._yscale, "name", self._yscale.code)

    def get_aspect(self) -> str:
        return self._aspect or "auto"

    def get_xticks(self) -> list[float]:
        """The x tick positions that will be drawn."""
        return [v for v, _ in self._xtick_pairs()]

    def get_yticks(self) -> list[float]:
        return [v for v, _ in self._ytick_pairs()]

    def get_xticklabels(self) -> list[str]:
        """The x tick label strings that will be drawn."""
        return [s for _, s in self._xtick_pairs()]

    def get_yticklabels(self) -> list[str]:
        return [s for _, s in self._ytick_pairs()]

    def _effective_ranges(self):
        """This axes' ranges as they will be *drawn*, including the union that
        ``sharex``/``sharey`` applies across the figure in ``_build_scene``."""
        own = self._ranges()
        fig = getattr(self, "_figure", None)
        if fig is None or not (fig.sharex or fig.sharey):
            return own
        siblings = [ax._ranges() for ax in fig.axes]
        if not siblings:
            return own
        xr, yr = own
        if fig.sharex:
            xr = (min(r[0][0] for r in siblings), max(r[0][1] for r in siblings))
        if fig.sharey:
            yr = (min(r[1][0] for r in siblings), max(r[1][1] for r in siblings))
        return xr, yr

    def _xtick_pairs(self) -> list[tuple[float, str]]:
        """``(value, label)`` x ticks, resolved exactly as ``_draw`` does."""
        xr = self._effective_ranges()[0]
        return self._resolve_ticks(self._xscale, xr[0], xr[1], 7,
                                   self._xticks_manual, self._xticklabels_manual,
                                   self._xformatter)

    def _ytick_pairs(self) -> list[tuple[float, str]]:
        yr = self._effective_ranges()[1]
        return self._resolve_ticks(self._yscale, yr[0], yr[1], 6,
                                   self._yticks_manual, self._yticklabels_manual,
                                   self._yformatter)

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
            labels = [_scales._fmt_plain(v) if v == int(v) else _ticker.fix_minus(f"{v:g}")
                      for v in values]
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
        xpad = _DATA_PAD if self._xmargin is None else self._xmargin
        ypad = _DATA_PAD if self._ymargin is None else self._ymargin
        if self._xlim:
            xr = self._xlim
        elif has_image:
            xr = xs.bounds() or (0.0, 1.0)
        else:
            xr = xs.padded(xpad)

        if self._ylim:
            yr = self._ylim
        elif has_image:
            yr = ys.bounds() or (0.0, 1.0)
        elif has_bar:
            lo, hi = ys.bounds() or (0.0, 1.0)
            # Bars are read against a baseline, so a non-negative series keeps
            # zero in view rather than floating above it.
            yr = (0.0, hi + (hi or 1.0) * ypad) if lo >= 0.0 else ys.padded(ypad)
        else:
            yr = ys.padded(ypad)

        # Non-linear scales own their autoscaling (positive-domain clipping and
        # transformed-space padding), unless the user pinned explicit limits.
        # This is the one path that still needs the values rather than the
        # bounds, so it pays for a concatenation - non-linear scales are the
        # uncommon case, and the arrays were retained by reference anyway.
        if not self._xscale.is_identity and not self._xlim:
            xr = self._xscale.data_limits(_concat(xs.arrays()))
        if not self._yscale.is_identity and not self._ylim:
            yr = self._yscale.data_limits(_concat(ys.arrays()))

        # Inversion is applied last, on whatever range we ended up with, so it
        # composes with autoscaling. Writing `xlim=(hi, lo)` still works and is
        # the direct spelling; `xinverted=True` is for the common case of
        # wanting a descending axis *without* pinning the numbers (depth,
        # astronomical magnitude, matrix rows).
        if self._xinverted:
            xr = (xr[1], xr[0])
        if self._yinverted:
            yr = (yr[1], yr[0])
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

        cbar_w = cbar_h = 0.0
        if self._colorbar:
            cb = self._colorbar
            cbticks = _colorbar_ticks(cb)
            if cb.get("orientation", "vertical") == "horizontal":
                # Beneath the plot: the strip's thickness plus its own tick
                # marks, tick labels and (upright) label, stacked downward.
                cbar_h = _CBAR_GAP + _CBAR_WIDTH + _CBAR_TICK_LEN + _CBAR_TICK_GAP
                cbar_h += tick_label_h
                if cb["label"]:
                    a, d, _ = scene.font_vmetrics(_AXIS_LABEL_SIZE)
                    cbar_h += a + d + _AXIS_LABEL_GAP
            else:
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

        # Each secondary axis reserves its own space, in the band the primary
        # chrome on that side already uses. Without this the ticks were drawn
        # at the plot edge with nothing reserved beyond it: on `top` they
        # landed under the title, and on `right` they landed *past the canvas*
        # and vanished. `_offset` is how far outside the plot edge the spine
        # sits - everything already reserved on that side - so a second
        # secondary on the same side stacks outside the first rather than over
        # it, and a secondary y clears a colorbar or twinx.
        tick_band = _TICK_LENGTH + _TICK_LABEL_GAP + tick_label_h
        outward = {
            # The title is drawn at the *top* of its band, so only a twiny sits
            # between the plot's top edge and free space.
            "top": tick_band if self._twiny is not None else 0.0,
            "bottom": x_tick_h, "left": y_tick_w, "right": cbar_w,
        }
        added = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
        for spec in self._secondary:
            side = spec["loc"]
            if spec["axis"] == "y":
                # A y axis is measured across its widest tick label, not the
                # line height an x axis needs.
                sticks = self._secondary_ticks(spec, xr, yr)
                widest = max((_tw(scene, lbl, _TICK_LABEL_SIZE) for _, lbl in sticks),
                             default=0.0)
                thick = _TICK_LENGTH + _TICK_LABEL_GAP + widest
            else:
                thick = tick_band
            if spec["label"]:
                # A gap on each side of the label box: one to the tick labels
                # it sits beyond, one to the primary's own axis label beyond
                # it. Without the outer gap the two collide, because the
                # primary label's glyph box overhangs its band.
                a, d, _ = scene.font_vmetrics(_AXIS_LABEL_SIZE)
                thick += _AXIS_LABEL_GAP + (a + d) + _AXIS_LABEL_GAP
            spec["_offset"] = outward[side]
            outward[side] += thick
            added[side] += thick
        title_h += added["top"]
        x_tick_h += added["bottom"]
        y_tick_w += added["left"]
        cbar_w += added["right"]
        self._sec_right_w = added["right"]

        bands = (title_h, xlabel_h, ylabel_w, x_tick_h, y_tick_w, cbar_w, cbar_h)
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
        #
        # The spans are signed - a descending limit (`ylim=(hi, lo)`, which is
        # how an inverted axis is spelled) makes one negative. Aspect is about
        # scale, not direction, so it works in magnitudes; using the signed span
        # here made `u` negative, `new_pw` a *negative width*, and mirrored the
        # other axis. Direction stays where it belongs, in the sign of
        # `txspan`/`tyspan` inside `sx`/`sy` below.
        if self._aspect == "equal":
            u = min(pw / abs(txspan), ph / abs(tyspan))
            new_pw, new_ph = u * abs(txspan), u * abs(tyspan)
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

        # Minor ticks: empty for linear scales unless asked for (so untouched
        # linear output stays byte-identical), e.g. the 2..9 x 10^k
        # subdivisions on a log axis, or `set(xminor=4)` on a linear one.
        x_minor = self._xscale.minor_ticks(xmin, xmax)
        y_minor = self._yscale.minor_ticks(ymin, ymax)
        if self._xminor > 0 and not x_minor:
            x_minor = _subdivide([v for v, _ in xticks], self._xminor, xmin, xmax)
        if self._yminor > 0 and not y_minor:
            y_minor = _subdivide([v for v, _ in yticks], self._yminor, ymin, ymax)

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
        for m in self._ordered_marks():
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

        # Tick geometry. `tlen` is the drawn length; `_TICK_LENGTH` stays the
        # length the *label band* was measured against in `_bands`, so an
        # inward tick does not leave a gap where the outward one used to be.
        tlen = _TICK_LENGTH if self._tick_length is None else self._tick_length
        inward = self._tick_direction == "in"

        # X ticks + labels.
        for value, label in _xt:
            x = sx(value)
            scene.add_path(
                [(x, py + ph), (x, py + ph + (-tlen if inward else tlen))],
                stroke_color=_SPINE,
                stroke_width=sw,
            )
            tw = _tw(scene, label, _TICK_LABEL_SIZE)
            baseline = py + ph + _TICK_LENGTH + _TICK_LABEL_GAP + t_asc
            _text(scene, x - tw / 2.0, baseline, label, _TICK_LABEL_SIZE, _BLACK)

        # Shorter, unlabeled minor tick marks (log subdivisions etc.).
        _MINOR_LEN = tlen * 0.6
        for value in _xm:
            x = sx(value)
            scene.add_path(
                [(x, py + ph), (x, py + ph + (-_MINOR_LEN if inward else _MINOR_LEN))],
                stroke_color=_SPINE, stroke_width=sw)

        # Y ticks + labels (right-aligned, vertically centered on the tick).
        for value, label in _yt:
            y = sy(value)
            scene.add_path(
                [(px + (tlen if inward else -tlen), y), (px, y)],
                stroke_color=_SPINE,
                stroke_width=sw,
            )
            tw = _tw(scene, label, _TICK_LABEL_SIZE)
            baseline = y + (t_asc - t_desc) / 2.0
            _text(scene, px - _TICK_LENGTH - _TICK_LABEL_GAP - tw, baseline, label,
                           _TICK_LABEL_SIZE, _BLACK)
        for value in _ym:
            y = sy(value)
            scene.add_path(
                [(px + (_MINOR_LEN if inward else -_MINOR_LEN), y), (px, y)],
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
            self._draw_legend(scene, px, py, pw, ph, proj)

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
                            an["ha"], an["va"], an.get("font", "body"),
                            an.get("rotation", 0.0))
            else:  # plain text
                _place_text(scene, sx(an["x"]), sy(an["y"]), an["s"], size, color,
                            an["ha"], an["va"], an.get("font", "body"),
                            an.get("rotation", 0.0))

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
                self._draw_side_label(scene, self._cbar_band(axl.cbar), plot,
                                      tw._ylabel, right=True)

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
        """A rotated axis label centred in ``band``, reading top-to-bottom on the
        right (matching a twinx's y label) and bottom-to-top on the left
        (matching the primary y label)."""
        t = self._theme
        size = t.axis_label_size
        a, d, _ = scene.font_vmetrics(size)
        tw = _tw(scene, text, size)
        pivot_x = band.x + band.w - (a + d) / 2.0 if right else band.x + (a + d) / 2.0
        pivot_y = plot.y + plot.h / 2.0
        if right:
            scene.begin_group(0.0, 1.0, -1.0, 0.0, pivot_x, pivot_y)   # +90deg
        else:
            scene.begin_group(0.0, -1.0, 1.0, 0.0, pivot_x, pivot_y)   # -90deg
        _text(scene, -tw / 2.0, 0.0, text, size, t.text_color)
        scene.end_group()

    def _cbar_band(self, band):
        """``layout.cbar`` narrowed to exclude the slice a secondary y axis on
        the right reserved out of it. Both share that band, and the colorbar's
        (or twinx's) own label has to stay within its own share instead of
        being pushed out on top of the secondary axis."""
        if not self._sec_right_w:
            return band
        return _Rect(band.x, band.y, max(band.w - self._sec_right_w, 0.0), band.h)

    def _secondary_ticks(self, spec, xr, yr):
        """Tick ``(value, label)`` pairs for a secondary axis, in *its* units.

        Shared by `_bands` and `_draw_secondary` so the space reserved for an
        axis is measured from the same ticks that get drawn into it."""
        fns = spec["functions"]
        fwd = fns[0] if fns else (lambda v: v)
        is_x = spec["axis"] == "x"
        r = xr if is_x else yr
        s0, s1 = fwd(r[0]), fwd(r[1])
        return _scales.nice_ticks(min(s0, s1), max(s0, s1), 7 if is_x else 6)

    def _draw_secondary(self, scene, plot, xr, yr, spec) -> None:
        t = self._theme
        _SPINE, sw, _BLACK = t.spine_color, t.spine_width, t.text_color
        _TL = t.tick_label_size
        t_asc, t_desc, _ = scene.font_vmetrics(_TL)
        _AL = t.axis_label_size
        l_asc, l_desc, _ = scene.font_vmetrics(_AL)
        fns = spec["functions"]
        inv = fns[1] if fns else (lambda v: v)
        ticks = self._secondary_ticks(spec, xr, yr)
        # How far outside the plot edge the spine sits: everything `_bands`
        # already reserved on this side. 0 puts it on the plot's own spine.
        off = spec.get("_offset", 0.0)
        axis_label = spec["label"]
        hproj = self._proj_for(plot, xr, yr, self._xscale, self._yscale)
        if spec["axis"] == "x":
            top = spec["loc"] == "top"
            edge_y = plot.y - off if top else plot.y1 + off
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
            if axis_label:
                # Just outside the far edge of the tick labels.
                far = (edge_y - _TICK_LENGTH - _TICK_LABEL_GAP - t_desc - t_asc if top
                       else edge_y + _TICK_LENGTH + _TICK_LABEL_GAP + t_asc + t_desc)
                baseline = (far - _AXIS_LABEL_GAP - l_desc if top
                            else far + _AXIS_LABEL_GAP + l_asc)
                lw = _tw(scene, axis_label, _AL)
                _text(scene, plot.x + (plot.w - lw) / 2.0, baseline, axis_label,
                      _AL, _BLACK)
        else:  # secondary y
            right = spec["loc"] == "right"
            edge_x = plot.x1 + off if right else plot.x - off
            direction = 1.0 if right else -1.0
            scene.add_path([(edge_x, plot.y), (edge_x, plot.y1)],
                           stroke_color=_SPINE, stroke_width=sw, cap="butt")
            widest = 0.0
            for sval, label in ticks:
                y = hproj.sy(inv(sval))
                if y < plot.y - 0.5 or y > plot.y1 + 0.5:
                    continue
                scene.add_path([(edge_x, y), (edge_x + direction * _TICK_LENGTH, y)],
                               stroke_color=_SPINE, stroke_width=sw)
                lw = _tw(scene, label, _TL)
                widest = max(widest, lw)
                bx = (edge_x + _TICK_LENGTH + _TICK_LABEL_GAP if right
                      else edge_x - _TICK_LENGTH - _TICK_LABEL_GAP - lw)
                _text(scene, bx, y + (t_asc - t_desc) / 2.0, label, _TL, _BLACK)
            if axis_label:
                strip = _TICK_LENGTH + _TICK_LABEL_GAP + widest + _AXIS_LABEL_GAP
                thick = l_asc + l_desc
                x0 = edge_x + strip if right else edge_x - strip - thick
                self._draw_side_label(scene, _Rect(x0, plot.y, thick, plot.h),
                                      plot, axis_label, right=right)

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
                               stroke_width=r["linewidth"], dash=_dash_for(r["linestyle"]))
            elif k == "axvline":
                x = sx(r["x"])
                y0, y1 = py + ph - r["min"] * ph, py + ph - r["max"] * ph
                scene.add_path([(x, y0), (x, y1)], stroke_color=r["color"],
                               stroke_width=r["linewidth"], dash=_dash_for(r["linestyle"]))
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
                           stroke_width=r["linewidth"], dash=_dash_for(r["linestyle"]))

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
                                     m["linewidth"], _dash_for(m["linestyle"]), "round", "round",
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
            # Fast path, like line/scatter: the band polygon is built in Rust
            # from the two bound arrays. Doing it here in Python cost two
            # `sx`/`sy` calls per sample and dominated the save.
            ax, bx, ay, by = proj.coeffs
            swap = m.get("orient", "y") == "x"
            scene.add_band_xform(
                m["ys"] if swap else m["xs"], m["y1"], m["y2"],
                ax, bx, ay, by, _with_alpha(m["color"], m["alpha"]),
                swap, proj.xcode, proj.ycode)
        elif kind == "lines":
            dash = _dash_for(m["linestyle"])
            horizontal = m["orient"] == "h"
            for p, a, b in zip(m["pos"], m["lo"], m["hi"]):
                if horizontal:
                    pts = [(sx(a), sy(p)), (sx(b), sy(p))]
                else:
                    pts = [(sx(p), sy(a)), (sx(p), sy(b))]
                scene.add_path(pts, stroke_color=m["color"], stroke_width=m["linewidth"],
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
                                       stroke_color=m["color"], stroke_width=m["linewidth"])
                    else:
                        scene.add_path([(sx(off - half), sy(pos)), (sx(off + half), sy(pos))],
                                       stroke_color=m["color"], stroke_width=m["linewidth"])
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
            xc, yc, w = m["xcoords"], m["ycoords"], m["linewidth"]
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
                            m["color"], m["linewidth"], head_len=6.0, head_w=2.5)
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
        lut = _colormap_lut(m["cmap"], m.get("alpha", 1.0))
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
        color, w, cap = m["color"], m["linewidth"], m["capsize"]
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
        band = self._cbar_band(layout.cbar)
        horizontal = cb.get("orientation", "vertical") == "horizontal"
        shrink = max(0.0, min(1.0, cb.get("shrink", 1.0)))

        if horizontal:
            self._draw_colorbar_horizontal(scene, cb, plot, band, shrink)
            return

        # Strip aligned vertically with the plot area, `shrink`ed about its
        # centre so a short bar stays opposite the middle of the data.
        strip_x = band.x + _CBAR_GAP
        strip_h = plot.h * shrink
        strip_y = plot.y + (plot.h - strip_h) / 2.0
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

    def _draw_colorbar_horizontal(self, scene, cb, plot, band, shrink: float) -> None:
        """The horizontal variant: strip under the plot, ticks below it, and an
        upright label under those (no rotation - it reads left-to-right here)."""
        t = self._theme
        _TICK_LABEL_SIZE = t.tick_label_size
        _AXIS_LABEL_SIZE = t.axis_label_size
        _SPINE = t.spine_color
        _BLACK = t.text_color
        cmap = cb["cmap"]
        vmin, vmax = cb["vmin"], cb["vmax"]

        strip_w = plot.w * shrink
        strip_x = plot.x + (plot.w - strip_w) / 2.0
        strip_y = band.y + _CBAR_GAP
        strip_h = _CBAR_WIDTH

        # Horizontal gradient: 1 row x N cols, col 0 = left = vmin.
        n = 256
        buf = bytearray(n * 4)
        denom = n - 1
        for i in range(n):
            r, g, b, a = cmap(i / denom)
            o = i * 4
            buf[o] = r
            buf[o + 1] = g
            buf[o + 2] = b
            buf[o + 3] = a
        scene.add_image(bytes(buf), n, 1, strip_x, strip_y, strip_w, strip_h)
        scene.add_path(
            [(strip_x, strip_y), (strip_x + strip_w, strip_y),
             (strip_x + strip_w, strip_y + strip_h), (strip_x, strip_y + strip_h)],
            close=True, stroke_color=_SPINE, stroke_width=0.8,
        )

        t_asc, t_desc, _ = scene.font_vmetrics(_TICK_LABEL_SIZE)
        span = (vmax - vmin) or 1.0
        norm = cb.get("norm")
        tick_bottom = strip_y + strip_h + _CBAR_TICK_LEN
        for value, label in _colorbar_ticks(cb):
            frac = norm(value) if norm is not None else (value - vmin) / span
            tx = strip_x + frac * strip_w
            scene.add_path([(tx, strip_y + strip_h), (tx, tick_bottom)],
                           stroke_color=_SPINE, stroke_width=1.0)
            lw = _tw(scene, label, _TICK_LABEL_SIZE)
            _text(scene, tx - lw / 2.0, tick_bottom + _CBAR_TICK_GAP + t_asc,
                  label, _TICK_LABEL_SIZE, _BLACK)

        if cb["label"]:
            a, _d, _ = scene.font_vmetrics(_AXIS_LABEL_SIZE)
            lw = _tw(scene, cb["label"], _AXIS_LABEL_SIZE)
            baseline = (tick_bottom + _CBAR_TICK_GAP + t_asc + t_desc
                        + _AXIS_LABEL_GAP + a)
            _text(scene, strip_x + (strip_w - lw) / 2.0, baseline, cb["label"],
                  _AXIS_LABEL_SIZE, _BLACK)

    # -- legend -------------------------------------------------------------

    def _legend_entries(self) -> list[dict]:
        """Labelled 2D marks, passed through with their kind intact so the glyph
        drawer can pick a swatch for bar/hist/fill and a rule for lines.

        A pie is the one mark whose labels are per-*wedge* rather than
        per-mark, so it expands into one entry each - which is also what
        ``ax.pie(labels=...)`` followed by ``ax.legend()`` means in matplotlib.
        """
        out: list[dict] = []
        for m in self._marks:
            if m["kind"] == "pie":
                out.extend({"kind": "pie", "label": w["label"], "color": w["color"]}
                           for w in m["wedges"] if w.get("label"))
            elif m.get("label"):
                out.append(m)
        return out

    def _draw_legend(self, scene, px: float, py: float, pw: float, ph: float,
                     proj: "_Proj | None" = None) -> None:
        entries = self._legend_entries()
        if not entries:
            return

        box_w, box_h, mt = _measure_legend(scene, entries, self._theme, self._legend)
        inset = 6.0
        loc = self._legend["loc"]
        right = px + pw - inset - box_w
        left = px + inset
        top = py + inset
        bottom = py + ph - inset - box_h
        hcenter = px + (pw - box_w) / 2.0
        positions = {
            "upper right": (right, top),
            "upper left": (left, top),
            "lower right": (right, bottom),
            "lower left": (left, bottom),
            "upper center": (hcenter, top),
            "lower center": (hcenter, bottom),
        }
        if loc == "best":
            bx, by = self._best_legend_position(positions, box_w, box_h, proj)
        else:
            bx, by = positions.get(loc, (right, top))
        _draw_legend_box(scene, entries, bx, by, mt)

    def _best_legend_position(self, positions: dict, box_w: float, box_h: float,
                              proj: "_Proj | None"):
        """The candidate corner that covers the least data.

        Scores each corner by how many sampled mark points would fall inside the
        box and takes the lowest, preferring earlier candidates on a tie so the
        familiar upper-right stays the default on an empty or symmetric plot.

        The sample is capped (:data:`_LEGEND_PROBE_POINTS` per mark), so the cost
        is a few hundred operations per figure no matter how large the data -
        this runs at draw time, and a legend is not worth an O(n) pass.
        """
        order = ["upper right", "upper left", "lower right", "lower left",
                 "upper center", "lower center"]
        if proj is None:
            return positions["upper right"]

        points = self._sample_device_points(proj)
        if not points:
            return positions["upper right"]

        best = None
        for name in order:
            bx, by = positions[name]
            x1, y1 = bx + box_w, by + box_h
            covered = sum(1 for (dx, dy) in points if bx <= dx <= x1 and by <= dy <= y1)
            if best is None or covered < best[0]:
                best = (covered, bx, by)
                if covered == 0:
                    break  # nothing can beat a clear corner
        return best[1], best[2]

    def _sample_device_points(self, proj: "_Proj") -> list[tuple[float, float]]:
        """Up to :data:`_LEGEND_PROBE_POINTS` device-space points per mark, as a
        cheap stand-in for "where the ink is"."""
        sx, sy = proj.sx, proj.sy
        out: list[tuple[float, float]] = []
        for m in self._marks:
            xs = m.get("xs")
            ys = m.get("ys")
            if xs is None or ys is None:
                continue
            n = min(len(xs), len(ys))
            if n == 0:
                continue
            step = max(1, n // _LEGEND_PROBE_POINTS)
            for i in range(0, n, step):
                x, y = xs[i], ys[i]
                if math.isfinite(x) and math.isfinite(y):
                    out.append((sx(x), sy(y)))
        return out
