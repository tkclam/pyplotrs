"""The 2D ``Axes``: a coordinate system plus a stack of marks.

Also holds ``_AxesBase`` - the contract every axes kind shares (color
cycling, the mark ordering rule, legends, the ``get_*`` readers) - and
``Mappable``, the handle a colormapped mark returns for
``Figure.colorbar``.
"""

from __future__ import annotations

import math
from array import array

from . import _colorbar, _pie
from . import _pyplotrs_core as _core
from . import colormaps as _colormaps
from . import norms as _norms
from . import scales as _scales
from . import theme as _theme
from . import ticker as _ticker
from ._const import (
    _AXIS_LABEL_GAP,
    _BOX_SLOT,
    _CBAR_GAP,
    _CBAR_TICK_GAP,
    _CBAR_TICK_LEN,
    _CBAR_WIDTH,
    _DATA_PAD,
    _DEFAULT_CELL_W,
    _ELLIPSE_N,
    _OFFSET_TEXT_GAP,
    _SEAM_STROKE,
    _TICK_LABEL_FIT,
    _TICK_LABEL_GAP,
    _TICK_LABEL_MIN45,
    _TICK_LENGTH,
    _TITLE_GAP,
)
from ._draw import (
    _check_marker,
    _colorbar_ticks,
    _dash_for,
    _draw_arrow,
    _draw_hatch,
    _draw_legend_box,
    _draw_marker,
    _draws_line,
    _font,
    _measure_legend,
    _norm_lut,
    _place_text,
    _rgba_values,
    _text,
    _th,
    _tw,
)
from ._draw import (
    draw_rotated_tick_label as _draw_rotated_tick_label,
)
from ._draw import (
    tick_rotation_geometry as _tick_rotation_geometry,
)
from ._layout import _layout_cell, _Proj, _Rect
from ._legend import best_position as _best_legend_position
from ._util import (
    _NUMERIC_BUFFER_FORMATS,
    _as_seq,
    _auto_levels,
    _axis_range,
    _boxstats,
    _check_margin,
    _clip_segment,
    _edges_from_centers,
    _expand_degenerate,
    _field_args,
    _flatten2d,
    _fold_guides,
    _interp_coord,
    _is_2d,
    _is_uniform,
    _level_edges,
    _matplotlib_hint,
    _RangeAcc,
    _require_same_length,
    _spine_ends,
    _step_points,
    _streamlines,
    _subdivide,
    _to_f64,
    _to_f64_grid,
    _union_ranges,
    _with_alpha,
)
from .mappable import Mappable
from .theme import Theme

#: Alias so methods taking a ``range=`` keyword can still reach the builtin.
_irange = range


class _AxesBase:
    """State and behavior every axes class shares.

    ``Axes``, ``Axes3D`` and ``PolarAxes`` are separate coordinate systems, but
    they are all "a theme, a color cycle and a stack of labeled marks". That
    much used to be written out three times - ``_next_color`` byte-identically,
    ``legend`` differing only in its default position, and the legend-entry
    normalization twice over - which is how the ``barh`` legend crash and the
    hardcoded swatch size survived: a fix applied to one copy silently missed
    the others.
    """

    def __repr__(self) -> str:
        """``<Axes 'Title' 12 marks xlim=(0, 10)>`` rather than an address.

        Inherited by `Axes3D` and `PolarAxes`, which report their own class
        name and their own mark list through `_MARKS_ATTR`.
        """
        bits = [type(self).__name__]
        title = getattr(self, "_title", None)
        if title:
            bits.append(repr(title))
        n = len(getattr(self, self._MARKS_ATTR, ()))
        bits.append(f"{n} mark{'' if n == 1 else 's'}")
        for axis in ("x", "y"):
            pinned = getattr(self, f"_{axis}lim", None)
            if pinned:
                bits.append(f"{axis}lim=({pinned[0]:g}, {pinned[1]:g})")
        return f"<{' '.join(bits)}>"


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
        """The resolved color for a mark, with ``alpha`` folded in.

        Folding opacity into the color here is what lets every mark take an
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
        """``(handles, labels)`` for the labeled marks, in draw order.

        A handle is the mark's own dict: pyplotrs has no Artist objects, and
        the mark *is* what the legend key gets drawn from."""
        entries = self._legend_entries()
        return list(entries), [e["label"] for e in entries]

    def legend(self, *, loc: str | None = None, ncol: int = 1,
               title: str | None = None, frameon: bool = True,
               fontsize: float | None = None):
        """Enable an auto-legend over this axes' labeled marks.

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
        """The labeled marks to draw legend keys for.

        3D and polar marks carry projection-specific fields, so they are
        normalized here into the line/scatter shapes the shared glyph drawer
        understands. Colormapped kinds (surface, trisurf, contour3d) carry no
        single data color, so they store a representative swatch color (their
        colormap's midpoint, or the middle level) at mark-construction time for
        exactly this purpose. ``Axes`` overrides this to pass its marks
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
        # X tick label angle: "auto" rotates only on a collision (see
        # `_x_tick_angle`), a number forces it, 0 forces flat.
        self._xtickrotation = "auto"
        self._x_tick_deg = 0.0
        # Shared offset/multiplier lifted out of the tick labels, written once
        # at the end of the axis. Computed in `_bands` (which always runs
        # before `_draw`, as the layout depends on it) and rendered there.
        self._x_offset_text = ""
        self._y_offset_text = ""
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


    def __getattr__(self, name: str):
        """Turn a matplotlib method name into the one line that replaces it.

        Only reached when normal lookup fails, so it costs nothing on the happy
        path. It deliberately does **not** alias: `plot` stays `line`, and the
        `set_*` family stays folded into `set()`, because those renames are the
        API's argument. What changes is that the error explains itself instead
        of being a bare "no attribute 'plot'".
        """
        hint = _matplotlib_hint(type(self).__name__, name)
        if hint is not None:
            raise AttributeError(hint)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def _coords(self, values, axis: str) -> "array":
        """Coerce plot coordinates to a contiguous ``array("d")``.

        Datetime-like values switch that axis to a
        [`DateScale`][pyplotrs.scales.DateScale] (mapped via ``date2num``); strings
        switch it to a [`CategoricalScale`][pyplotrs.scales.CategoricalScale], mapping each
        distinct label to an integer position in first-seen order.

        The numeric case is the hot one and is handled first, without ever
        materializing an intermediate Python list: anything already offering an
        ``f64`` buffer (a NumPy array, another ``array("d")``) is taken as-is.
        Only inputs that are *not* plain numbers pay for the datetime/string
        inspection below.
        """
        # Buffer-backed *numeric* input can't be dates or strings - take the
        # fast path before touching the sequence at all. The format check is
        # what makes that true: a NumPy `<U8` array is buffer-backed too, and
        # so is anything with a struct format this module cannot read as a
        # number, so testing only `ndim`/`c_contiguous` sent string arrays into
        # `_to_f64` to die on "unsupported format 1w" instead of reaching the
        # categorical branch below. `datetime64` does not even get that far -
        # `memoryview()` itself raises ValueError for it.
        try:
            view = memoryview(values)
        except (TypeError, ValueError, NotImplementedError):
            view = None
        if (
            view is not None
            and view.ndim == 1
            and view.c_contiguous
            and view.format in _NUMERIC_BUFFER_FORMATS
        ):
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
        _check_marker(marker)
        xs, ys = self._coords(xs, "x"), self._coords(ys, "y")
        _require_same_length("line", x=xs, y=ys)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "line",
            "xs": xs,
            "ys": ys,
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
        """``line`` with the x-axis log-scaled - matplotlib's ``ax.semilogx``.

        A thin wrapper: ``ax.set(xscale="log")`` then ``ax.line(xs, ys, **kwargs)``.
        """
        self.set(xscale="log")
        return self.line(xs, ys, **kwargs)

    def semilogy(self, xs, ys, **kwargs) -> "Axes":
        """``line`` with the y-axis log-scaled - matplotlib's ``ax.semilogy``."""
        self.set(yscale="log")
        return self.line(xs, ys, **kwargs)

    def loglog(self, xs, ys, **kwargs) -> "Axes":
        """``line`` with both axes log-scaled - matplotlib's ``ax.loglog``."""
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
        [`pyplotrs.norms`][pyplotrs.norms] instance for non-linear). Returns a colorbar handle
        in that case, else ``self``."""
        _check_marker(marker)
        xs = self._coords(xs, "x")
        ys = self._coords(ys, "y")
        _require_same_length("scatter", x=xs, y=ys)
        mark = {
            "zorder": float(zorder),
            "kind": "scatter",
            "xs": xs,
            "ys": ys,
            "label": label,
            # A colormapped scatter's per-point colors replace this, but it is
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
        #
        # `alpha` goes through here too. It used to be folded in only on the
        # `c is None` branch above, so `scatter(c=v, alpha=0.3)` - the standard
        # way to show density in an overplotted cloud - drew fully opaque
        # points, and a crowded region took the color of whichever point
        # happened to be drawn last instead of a blend. `hexbin`, `pcolormesh`
        # and `imshow` all already honored it; this was an omission.
        cvals = _to_f64(c)
        nrm = _norms.get(norm, vmin, vmax).autoscale(cvals)
        cm = _colormaps.get_cmap(cmap)
        mark["colors"] = _rgba_values(cvals, cm, nrm, alpha)
        return Mappable(self, cm, nrm.vmin, nrm.vmax, norm=nrm)

    def bar(self, x, height, *, width: float = 0.5, bottom=0.0, color=None,
            alpha: float = 1.0, label: str | None = None, edgecolor=None, zorder: float = 0.0) -> "Axes":
        """Draw vertical bars of the given ``height`` at positions ``x``. ``x``
        may be strings (categories), which set a categorical x-axis.

        ``width`` is a **data extent** in x units, not a stroke width: at the
        default 0.5 a bar fills half the gap to its neighbor. This is narrower
        than matplotlib's 0.8 on purpose - the gap is what makes bars read as
        discrete categories at the default single-column figure size."""
        xs = self._coords(x, "x")
        heights = [float(v) for v in height]
        bottoms = _as_seq(bottom, len(xs))
        _require_same_length("bar", x=xs, height=heights)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "bar",
            "xs": xs,
            "heights": heights,
            "bottoms": bottoms,
            "width": float(width),
            # Bars rest on their bases. Only the extreme bases can ever bind,
            # so two values stand in for all of them.
            "sticky_y": [min(bottoms), max(bottoms)] if bottoms else [],
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
        # `max(int(bins), 1)` used to silently promote 0 and negatives to a
        # single bin, so `hist(data, bins=0)` drew one wide bar rather than
        # complaining about the argument.
        if int(bins) < 1:
            raise ValueError(f"hist needs at least one bin; got bins={bins!r}")
        vals = _to_f64(data)
        if not len(vals):
            vals = array("d", (0.0, 1.0))
        span = (float(range[0]), float(range[1])) if range else None
        edges, counts = _core.histogram(vals, int(bins), span, bool(density))
        self._marks.append({
            "zorder": float(zorder),
            "kind": "hist",
            "edges": edges,
            "counts": counts,
            "sticky_y": [0.0],
            "color": self._mark_color(color, alpha),
            "label": label,
        })
        return self

    def fill_between(self, xs, y1, y2=0.0, *, color=None, alpha: float = 0.3,
                     label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Fill the band between ``y1`` and ``y2`` across ``xs``."""
        xs = self._coords(xs, "x")
        y1 = _to_f64(y1)
        _require_same_length("fill_between", x=xs, y1=y1)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "fill",
            "orient": "y",
            "xs": xs,
            "y1": y1,
            "y2": _to_f64(_as_seq(y2, len(xs))),
            "color": self._next_color(color),
            "alpha": float(alpha),
            "label": label,
        })
        return self

    def fill_betweenx(self, ys, x1, x2=0.0, *, color=None, alpha: float = 0.3,
                      label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Fill the band between ``x1`` and ``x2`` across ``ys`` - the transpose
        of ``fill_between``, for bands around a horizontal profile."""
        ys = self._coords(ys, "y")
        x1 = _to_f64(x1)
        _require_same_length("fill_betweenx", y=ys, x1=x1)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "fill",
            "orient": "x",
            "ys": ys,
            "y1": x1,
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

        Unlike ``axhline``, which spans a fraction of the axes and is a
        guide, these are data and participate in autoscaling. Each argument may
        be a scalar or a sequence; scalars broadcast."""
        return self._add_lines("h", y, xmin, xmax, color, linewidth, linestyle, label,
                               alpha, zorder)

    def vlines(self, x, ymin, ymax, *, color=None, linewidth: float | None = None,
               alpha: float = 1.0, linestyle: str = "solid",
               label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Vertical line segments at each ``x``, spanning ``ymin`` to ``ymax`` in
        **data** coordinates (see ``hlines``)."""
        return self._add_lines("v", x, ymin, ymax, color, linewidth, linestyle, label,
                               alpha, zorder)

    def _add_lines(self, orient, pos, lo, hi, color, linewidth, linestyle, label,
                   alpha=1.0, zorder: float = 0.0) -> "Axes":
        """Shared body of ``hlines`` / ``vlines``."""
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
        _check_marker(marker)
        xs = [float(x) for x in xs]
        ys = [float(y) for y in ys]
        _require_same_length("errorbar", x=xs, y=ys)
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
        """``(colormap, norm, rgba_per_value)`` for the per-element colored
        types (hexbin, pcolormesh). The mapping itself runs in Rust - see
        ``_rgba_values``."""
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
        widths = [float(v) for v in width]
        lefts = _as_seq(left, len(ys))
        _require_same_length("barh", y=ys, width=widths)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "barh", "ys": ys, "widths": widths,
            "lefts": lefts, "height": float(height),
            "sticky_x": [min(lefts), max(lefts)] if lefts else [],
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
        # The `max` keeps a box wider than one slot from clipping (see _BOX_SLOT).
        slot = max(_BOX_SLOT, float(widths) / 2.0)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "boxplot", "stats": stats, "positions": positions,
            "width": float(widths), "color": self._mark_color(color, alpha),
            "showfliers": showfliers, "label": label,
            "slot": slot,
            "sticky_x": ([min(positions) - slot, max(positions) + slot]
                         if positions else []),
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
            # Over the data range exactly, as matplotlib does. Evaluating 15%
            # past each end drew KDE tails the sample never reached, and - the
            # whole grid fed autoscaling - padded 5% beyond those on top.
            lo, hi = _expand_degenerate(min(vals), max(vals))
            grid = [lo + (hi - lo) * i / (points - 1) for i in range(points)]
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
        so they come from ``labels`` - which is also what feeds ``legend``.
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
        # Limits are the pie's own bounding box, so the equal-aspect square *is*
        # the pie. Room for the slice labels is taken out of the drawn radius at
        # draw time, where they can be measured (`_pie_geometry`); padding the
        # limits by a guessed factor instead both wasted the cell and still
        # clipped labels the guess was too small for.
        self._xlim = (-radius, radius)
        self._ylim = (-radius, radius)
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
               label: str | None = None, zorder: float = 0.0) -> "Mappable":
        """Display 2D ``data`` as a colormapped image.

        ``data`` is a sequence of equal-length rows. ``cmap`` is a colormap
        name (see [`pyplotrs.colormaps`][pyplotrs.colormaps]) or a ``Colormap``. ``norm`` maps
        values onto the color axis (``None`` linear, ``"log"`` for a
        [`LogNorm`][pyplotrs.norms.LogNorm], or any [`Normalize`][pyplotrs.norms.Normalize]);
        the per-pixel lookup runs in Rust. ``extent`` is ``(x0, x1, y0, y1)`` in
        data coordinates (default ``(0, ncols, 0, nrows)``); ``origin`` is
        ``"upper"`` (row 0 at top) or ``"lower"``. Returns a handle for
        ``Figure.colorbar``.
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
            # The whole norm, not a code: `_draw._norm_lut` decides at draw
            # time whether Rust can run it directly or has to be handed a
            # table with the norm already folded in. Keeping only a code here
            # is what let a `TwoSlopeNorm` be quietly downgraded to linear.
            "norm": nrm,
            "extent": extent,
            # Covers its extent exactly and stops. Per-mark and per-axis, so a
            # line drawn beyond the image still gets its own margin.
            "sticky_x": [extent[0], extent[1]],
            "sticky_y": [extent[2], extent[3]],
            "origin": origin,
            "alpha": float(alpha),
            "label": label,
            # A colormapped mark has no single color, so its legend key is the
            # colormap's midpoint - the one swatch that reads as "this map".
            "color": _with_alpha(cm(0.5), alpha),
        })
        # The colorbar gets the real norm unconditionally - it places its ticks
        # by calling it, so handing it `None` for anything Rust could not run
        # per-pixel drew a linear scale beside a non-linear image.
        return Mappable(self, cm, lo, hi, norm=nrm)

    # -- step / stair family ------------------------------------------------

    def step(self, xs, ys, *, where: str = "pre", color=None,
             linewidth: float | None = None, alpha: float = 1.0,
             linestyle: str = "solid", label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Step plot through ``(xs, ys)``; ``where`` is ``pre``/``post``/``mid``."""
        xs, ys = _to_f64(xs), _to_f64(ys)
        _require_same_length("step", x=xs, y=ys)
        px, py = _step_points(list(xs), list(ys), where)
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
                "sticky_y": [float(baseline)],
                "color": self._next_color(color), "alpha": 0.3, "label": label,
            })
        else:
            px = array("d", [edges[0]]) + xs + array("d", [edges[-1]])
            py = array("d", [baseline]) + top + array("d", [baseline])
            self._marks.append({
                "zorder": float(zorder),
                "kind": "line", "xs": px, "ys": py, "label": label,
                "sticky_y": [float(baseline)],
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
        _check_marker(marker)
        xs, ys = self._coords(xs, "x"), self._coords(ys, "y")
        _require_same_length("stem", x=xs, y=ys)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "stem", "xs": xs, "ys": ys,
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
               zorder: float = 0.0) -> "Mappable":
        """2D histogram of ``(xs, ys)`` rendered as a colormapped image. ``bins``
        is an int or ``(nx, ny)``; the count grid is built in Rust."""
        xs = _to_f64(xs)
        ys = _to_f64(ys)
        nx, ny = (bins, bins) if isinstance(bins, int) else (int(bins[0]), int(bins[1]))
        # A non-positive count reached the kernel, which computes `nx - 1` in
        # `usize` - so 0 wrapped to 18446744073709551615 and indexed an empty
        # buffer, and a negative failed as a PyO3 conversion OverflowError.
        if nx < 1 or ny < 1:
            raise ValueError(
                f"hist2d needs at least one bin on each axis; got bins=({nx}, {ny})"
            )
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
               zorder: float = 0.0) -> "Mappable":
        """Hexagonal binning of ``(xs, ys)`` colored by count (binning in Rust).

        The whole lattice is drawn, as in matplotlib: a cell no point landed in
        is a count of zero, so it takes the bottom of the colormap rather than
        leaving the background showing through.
        """
        xs = _to_f64(xs)
        ys = _to_f64(ys)
        xlo, xhi = _core.data_range(xs) or (0.0, 1.0)
        ylo, yhi = _core.data_range(ys) or (0.0, 1.0)
        hexes, sx, sy = _core.hexbin(xs, ys, gridsize, xlo, xhi, ylo, yhi)
        counts = _to_f64([c for _, _, c in hexes])
        cm, nrm, colors = self._map_colors(counts, cmap, norm, vmin, vmax)
        # Pointy-top hexagon: the Voronoi cell of the binner's two interleaved
        # lattices, sx wide and 2/3 sy tall. Both scales come from the binner -
        # sy is set by the *y* range and the derived row count, so guessing it
        # from sx (as this once did) only tiles when the two happen to agree,
        # and shears into slivers or overlapping spikes when they don't.
        offs = [(0.0, sy / 3.0), (sx / 2.0, sy / 6.0), (sx / 2.0, -sy / 6.0),
                (0.0, -sy / 3.0), (-sx / 2.0, -sy / 6.0), (-sx / 2.0, sy / 6.0)]
        if alpha < 1.0:
            colors = [_with_alpha(c, alpha) for c in colors]
        self._marks.append({
            "zorder": float(zorder),
            "kind": "hexbin", "centers": [(cx, cy) for cx, cy, _ in hexes],
            "colors": colors, "offsets": offs, "label": label,
            "color": _with_alpha(cm(0.5), alpha),
        })
        return Mappable(self, cm, nrm.vmin, nrm.vmax,
                         norm=(nrm if type(nrm) is not _norms.Normalize else None))

    # -- field / grid -------------------------------------------------------

    def pcolormesh(self, *args, cmap="viridis", norm=None, vmin: float | None = None,
                   vmax: float | None = None, alpha: float = 1.0,
                   label: str | None = None, zorder: float = 0.0) -> "Mappable":
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
                            "extent": (xe[0], xe[-1], ye[0], ye[-1]),
                            "sticky_x": [xe[0], xe[-1]],
                            "sticky_y": [ye[0], ye[-1]]})
        return Mappable(self, cm, nrm.vmin, nrm.vmax)

    def contour(self, *args, levels=None, colors=None, cmap=None,
                linewidth: float | None = None, alpha: float = 1.0,
                label: str | None = None, zorder: float = 0.0) -> "Axes":
        """Contour *lines* of a 2D field: ``contour(Z)`` or ``contour(X, Y, Z)``.
        Marching squares runs in Rust; lines are colored per level from
        ``colors`` (a single color / list) or ``cmap`` (default palette C0).

        ``levels`` is either the thresholds themselves, or an int asking for
        *about* that many: the levels then land on round numbers inside the data
        range, the way the axis locator picks ticks, so the count comes out near
        the hint rather than exactly on it.
        """
        xc, yc, Z = _field_args(args)
        h = len(Z)
        w = len(Z[0]) if Z else 0
        flat = _to_f64([v for row in Z for v in row])
        lvls = _auto_levels(flat, levels)
        lines = _core.contour_lines(flat, w, h, lvls)
        lcolors = self._level_colors(len(lvls), colors, cmap)
        if alpha < 1.0:
            lcolors = [_with_alpha(c, alpha) for c in lcolors]
        self._marks.append({
            "zorder": float(zorder),
            "kind": "contour", "lines": lines, "xcoords": xc, "ycoords": yc,
            "levels": lvls, "colors": lcolors, "label": label,
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
            # Legend key: the middle level's color stands for the line set.
            "color": lcolors[len(lcolors) // 2] if lcolors else self._theme.palette[0],
            "extent": (min(xc), max(xc), min(yc), max(yc)),
            # The field is only defined on its grid, so the view stops there.
            "sticky_x": [min(xc), max(xc)],
            "sticky_y": [min(yc), max(yc)],
        })
        return self

    def contourf(self, *args, levels=None, cmap="viridis", norm=None,
                 vmin: float | None = None, vmax: float | None = None,
                 upsample: int = 6, alpha: float = 1.0,
                 label: str | None = None, zorder: float = 0.0) -> "Mappable":
        """Filled contour bands of a 2D field. The field is bilinearly upsampled
        and band-colored in Rust (a raster fill, like ``imshow``).

        ``levels`` is either the band edges themselves, or an int asking for
        *about* that many bands. Auto edges are the round numbers
        ``contour`` draws its lines on, extended out to bracket the data, so
        a contour overlay lands exactly on the band boundaries - and the
        colorbar spans those round numbers rather than the raw extrema.
        """
        xc, yc, Z = _field_args(args)
        h = len(Z)
        w = len(Z[0]) if Z else 0
        flat = _to_f64([v for row in Z for v in row])
        edges = _level_edges(flat, levels)
        nbands = len(edges) - 1
        cm = _colormaps.get_cmap(cmap)
        # `levels` fixes where the bands *are*; `vmin`/`vmax` fix how the
        # colormap is stretched across them. Both were accepted and then
        # overwritten with the level extremes, so passing `vmin`/`vmax` to
        # `contourf` did nothing at all - not even a warning - and two panels
        # asked to share a color scale silently each got their own.
        nrm = _norms.get(norm, vmin, vmax)
        nrm.vmin = edges[0] if nrm.vmin is None else nrm.vmin
        nrm.vmax = edges[-1] if nrm.vmax is None else nrm.vmax
        band_lut = bytes(b for k in _irange(nbands)
                         for b in _with_alpha(cm(nrm(0.5 * (edges[k] + edges[k + 1]))), alpha))
        img, uw, uh = _core.contourf_image(flat, w, h, edges, band_lut, upsample)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "contourf", "img": bytes(img), "uw": uw, "uh": uh,
            "label": label, "color": _with_alpha(cm(0.5), alpha),
            "extent": (min(xc), max(xc), min(yc), max(yc)),
            "sticky_x": [min(xc), max(xc)],
            "sticky_y": [min(yc), max(yc)],
        })
        # The colorbar spans the norm, so an explicit vmin/vmax shows there too.
        return Mappable(self, cm, nrm.vmin, nrm.vmax, norm=nrm)

    def pcolor(self, *args, **kwargs) -> "Mappable":
        """Alias of ``pcolormesh``.

        matplotlib distinguishes the two (``pcolor`` returns a masked-aware
        ``PolyCollection``, ``pcolormesh`` a faster ``QuadMesh``); pyplotrs has
        only the fast path, and it already chooses per-cell quads over the
        image path whenever the grid is irregular, so the distinction has
        nothing left to express."""
        return self.pcolormesh(*args, **kwargs)

    def matshow(self, data, **kwargs) -> "Mappable":
        """Display a matrix with row 0 at the top and one cell per entry.

        ``imshow`` with the conventions a *matrix* wants rather than the
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
        for i, series in enumerate(ys):
            if hasattr(series, "__len__") and len(series) != n:
                raise ValueError(
                    f"stackplot needs x and every series of equal length; "
                    f"got x={n}, series {i}={len(series)}"
                )
        lower = [float(baseline)] * n
        for i, series in enumerate(ys):
            vals = _as_seq(series, n)
            upper = [lo + v for lo, v in zip(lower, vals)]
            self.fill_between(xs, upper, lower, alpha=alpha, zorder=zorder,
                              color=(colors[i % len(colors)] if colors else None),
                              label=(labels[i] if labels and i < len(labels) else None))
            if i == 0:
                # Only the first band rests on the floor, and the floor is the
                # whole reading: a stack hovering above the spine misreports
                # where the total starts. Sticks at this stack's *own* baseline,
                # not the literal zero matplotlib uses (stackplot.py:135) -
                # `baseline=100` should sit on 100, which matplotlib gets wrong.
                self._marks[-1]["sticky_y"] = [float(baseline)]
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
        fraction ``xmin..xmax`` (0 = left edge, 1 = right).

        ``y`` is folded into the y limits so the guide cannot land outside the
        frame; ``xmin``/``xmax`` are axes fractions, not data, so x is untouched."""
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
        fraction ``ymin..ymax``. ``x`` is folded into the x limits so the guide
        stays inside the frame; ``ymin``/``ymax`` are fractions. See ``axhline``."""
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
        the axes fraction ``xmin..xmax`` in x). Drawn behind the data; the band
        is folded into the y limits so it stays visible."""
        self._refs.append({
            "kind": "axhspan", "lo": float(ymin), "hi": float(ymax),
            "min": float(xmin), "max": float(xmax),
            "color": self._next_color(color), "alpha": float(alpha),
        })
        return self

    def axvspan(self, xmin: float, xmax: float, *, ymin: float = 0.0, ymax: float = 1.0,
                color=None, alpha: float = 0.3) -> "Axes":
        """Shade the vertical band between data ``xmin`` and ``xmax`` (spanning
        the axes fraction ``ymin..ymax`` in y). Drawn behind the data; the band
        is folded into the x limits so it stays visible."""
        self._refs.append({
            "kind": "axvspan", "lo": float(xmin), "hi": float(xmax),
            "min": float(ymin), "max": float(ymax),
            "color": self._next_color(color), "alpha": float(alpha),
        })
        return self

    def axline(self, xy1, *, xy2=None, slope: float | None = None, color=None,
               linewidth: float | None = None, linestyle: str = "solid") -> "Axes":
        """Draw an infinite line through ``xy1``, defined by a second point
        ``xy2`` or a ``slope``. Clipped to the plot rect. Alone among the
        guides it contributes nothing to the limits - it is infinite, so it has
        no extent to contribute and is always on screen already."""
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

        A thin wrapper over ``polygon`` taking parallel ``x``/``y`` arrays
        instead of a list of point pairs; ``facecolor`` cycles the palette like
        a data mark when omitted. It is a patch like ``polygon`` (drawn
        over the data, outside the zorder/legend contract the marks share) -
        call ``polygon`` directly for its other knobs.
        """
        xs = _to_f64(x)
        ys = _to_f64(y)
        _require_same_length("fill", x=xs, y=ys)
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
        math. ``color`` defaults to the theme text color. ``weight`` is
        ``normal`` or ``bold`` and ``style`` is ``normal`` or ``italic``; both
        select a real face of the body family, so the glyphs are genuinely bold
        or italic rather than synthetically slanted.

        ``rotation`` turns the text counter-clockwise by that many degrees
        about its anchor, and it stays selectable text in PDF/SVG - the
        rotation is a group transform in the IR, not baked-out paths."""
        self._annotations.append({
            "kind": "text", "x": float(x), "y": float(y), "s": s,
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
        a bold and/or italic face (see ``text``)."""
        xy = (float(xy[0]), float(xy[1]))
        self._annotations.append({
            "kind": "annotate", "s": text, "xy": xy,
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
            tick_direction=None, tick_length=None, xtickrotation=None) -> "Axes":
        """Set any combination of title, axis labels, view limits, axis scales,
        and tick/grid/aspect/margin controls.

        ``xscale``/``yscale`` accept ``"linear"`` (default), ``"log"``,
        ``"symlog"``, ``"logit"`` or a [`pyplotrs.scales.Scale`][pyplotrs.scales.Scale].
        ``xticks``/``yticks`` pin tick positions; ``xticklabels``/``yticklabels``
        give matching label strings. ``xformatter``/``yformatter`` accept a
        [`pyplotrs.ticker.Formatter`][pyplotrs.ticker.Formatter], a ``"{x:.2f}"`` template, or a
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
        length in points.

        ``xtickrotation`` is an angle in degrees for the x tick labels, or
        ``"auto"`` (the default) to rotate only when the labels would otherwise
        collide, or ``0`` to force them flat and accept the overlap. Long
        category names on a bar chart are the case this exists for: drawn flat
        they overprint each other, and the axis stops saying which bar is
        which."""
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
            self._xticklabels_manual = list(xticklabels)
        if yticklabels is not None:
            self._yticklabels_manual = list(yticklabels)
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
            self._xmargin = _check_margin("xmargin", xmargin)
        if ymargin is not None:
            self._ymargin = _check_margin("ymargin", ymargin)
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
        if xtickrotation is not None:
            self._xtickrotation = ("auto" if xtickrotation == "auto"
                                   else float(xtickrotation))
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
        """Effective y limits (see ``get_xlim``; ``sharey`` unifies these)."""
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
            xr = _union_ranges(xr, [r[0] for r in siblings])
        if fig.sharey:
            yr = _union_ranges(yr, [r[1] for r in siblings])
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
        locator+labels when nothing is overridden.

        Manual positions outside ``lo..hi`` are dropped. A pinned tick has no
        place on the axis to be drawn at, so it used to be placed by the same
        arithmetic anyway and land *outside* the plot rect - a stray label
        floating above or below the panel, over whatever was there."""
        return self._resolve_ticks_offset(
            scale, lo, hi, max_n, manual, manual_labels, formatter)[0]

    def _resolve_ticks_offset(self, scale, lo: float, hi: float, max_n: int,
                              manual, manual_labels, formatter):
        """``(pairs, offset_text)`` - [`_resolve_ticks`] plus the corner text.

        A numeric axis whose labels would otherwise repeat the same leading
        digits, or run to a string of zeros, gets a shared term lifted out of
        every label and written once at the end of the axis instead. Without
        it a nanometer axis can only be labeled by printing ten decimals, and
        a `1000000.05`-style label is both unreadable and wide enough to run
        off the page. An explicit formatter or explicit labels always win -
        this only fills in for the default.
        """
        if manual is not None:
            values = manual
        elif manual_labels is not None or formatter is not None:
            values = [v for v, _ in scale.ticks(lo, hi, max_n)]
        else:
            pairs = scale.ticks(lo, hi, max_n)
            if not getattr(scale, "supports_offset", False) or len(pairs) < 2:
                return pairs, ""
            vals = [v for v, _ in pairs]
            offset, exponent = _ticker.factor_out(vals)
            if not offset and not exponent:
                return pairs, ""
            labels = _ticker.apply_offset(vals, offset, exponent)
            return list(zip(vals, labels)), _ticker.offset_label(offset, exponent)
        if manual_labels is not None:
            labels = [manual_labels[i] if i < len(manual_labels) else ""
                      for i in range(len(values))]
        elif formatter is not None:
            labels = [formatter(v, i) for i, v in enumerate(values)]
        else:
            labels = [_scales._fmt_plain(v) if v == int(v) else _ticker.fix_minus(f"{v:g}")
                      for v in values]
        pairs = list(zip(values, labels))
        if manual is not None:
            eps = abs(hi - lo) * 1e-9
            pairs = [p for p in pairs if lo - eps <= p[0] <= hi + eps]
        return pairs, ""

    # -- layout helpers -----------------------------------------------------

    def _ranges(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Autoscaled ``(xrange, yrange)`` for this axes.

        Bulk coordinate arrays are reduced to their finite min/max **in Rust**
        and folded into a running bound (see ``_RangeAcc``); only the
        handful of derived scalars each mark contributes - bar edges, image
        extents, whisker ends - are touched in Python. Previously this
        concatenated every point of every mark into one list and scanned that,
        which was the single most expensive step in saving a large figure.
        """
        xs = _RangeAcc()
        ys = _RangeAcc()
        # Sticky bounds: values a mark rests *on* rather than merely reaches -
        # a bar's base, a stack's floor, an image's edge. Recorded by each mark
        # at construction; the margin is clamped at them (see `_clamp_sticky`).
        sticky_x: list[float] = []
        sticky_y: list[float] = []
        for m in self._marks:
            k = m["kind"]
            sx = m.get("sticky_x")
            if sx:
                sticky_x.extend(sx)
            sy = m.get("sticky_y")
            if sy:
                sticky_y.extend(sy)
            if k in ("line", "scatter"):
                xs.add_pairs(m["xs"], m["ys"], ys)
            elif k == "bar":
                hw = m["width"] / 2.0
                bx = _core.data_range(m["xs"])
                if bx is not None:
                    xs.add(bx[0] - hw, bx[1] + hw)
                ys.add_array(m["bottoms"])
                ys.add_offsets(m["bottoms"], m["heights"], two_sided=False)
            elif k == "hist":
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
                x0, x1, y0, y1 = m["extent"]
                xs.add(x0, x1)
                ys.add(y0, y1)
            elif k == "barh":
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
                hw = m["slot"]
                for pos, st in zip(m["positions"], m["stats"]):
                    xs.add(pos - hw, pos + hw)
                    ys.add(st["lo"], st["hi"])
                    # Fliers that aren't drawn must not move the axis: scaling
                    # to a hidden outlier squeezes the visible box to nothing.
                    if st["fliers"] and m["showfliers"]:
                        ys.add_array(_to_f64(st["fliers"]))
            elif k == "violin":
                hw = m["width"] / 2.0
                for pos, (grid, _dens) in zip(m["positions"], m["violins"]):
                    xs.add(pos - hw, pos + hw)
                    ys.add_array(_to_f64(grid))
            elif k == "hexbin":
                # The hexagons, not just their centers: the outer ring reaches
                # half a cell past the outermost center, so bounding the centers
                # alone slices those hexagons flat against the frame.
                hx = max(ox for ox, _ in m["offsets"])
                hy = max(oy for _, oy in m["offsets"])
                for cx, cy in m["centers"]:
                    xs.add(cx - hx, cx + hx)
                    ys.add(cy - hy, cy + hy)
            elif k in ("quadmesh", "contourf"):
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

        _fold_guides(self._patches, self._refs, xs, ys)

        xpad = _DATA_PAD if self._xmargin is None else self._xmargin
        ypad = _DATA_PAD if self._ymargin is None else self._ymargin
        xr = _axis_range(self._xscale, xs, self._xlim, xpad, sticky_x)
        yr = _axis_range(self._yscale, ys, self._ylim, ypad, sticky_y)

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

    def _x_tick_angle(self, scene, xticks, xr) -> float:
        """The angle to set the x tick labels at, in degrees CCW.

        An explicit ``xtickrotation`` wins. ``"auto"`` rotates only when the
        labels cannot fit flat: the widest one is compared against the space
        between two ticks, and if it does not fit the labels go to 45 degrees,
        or to 90 if even that leaves them overlapping. Flat labels that do not
        fit used to simply overprint each other - on a bar chart of species or
        condition names, which is where a legend-free categorical axis is most
        common, the reader could not tell which bar was which.

        The comparison uses the *cell* width rather than the plot width, which
        is not yet solved when this runs; it is within a few percent, and the
        decision only has to be right about whether the labels are close to
        touching.
        """
        rot = self._xtickrotation
        if rot != "auto":
            return float(rot)
        if len(xticks) < 2 or self._frame_off:
            return 0.0
        size = self._theme.tick_label_size
        widest = max(_tw(scene, lbl, size) for _, lbl in xticks)
        # Device points per tick interval, estimated from this axes' cell.
        cell_w = getattr(self, "_cell_w_hint", None) or _DEFAULT_CELL_W
        spacing = cell_w / max(1, len(xticks) - 1)
        if widest <= spacing * _TICK_LABEL_FIT:
            return 0.0
        # At 45 degrees a label needs only its own height of horizontal room
        # per tick; past that, upright is the only thing that always fits.
        return 45.0 if spacing >= _TICK_LABEL_MIN45 else 90.0

    def _bands(self, scene: "_core.Scene", xr, yr) -> tuple[
        tuple[float, float, float, float, float, float, float, float, float],
        list[tuple[float, str]],
        list[tuple[float, str]],
    ]:
        """Measure the reserved band sizes for this axes and locate ticks.

        Returns ``(bands, xticks, yticks)`` where ``bands`` is the 9-tuple
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

        xticks, self._x_offset_text = self._resolve_ticks_offset(
            self._xscale, xr[0], xr[1], 7, self._xticks_manual,
            self._xticklabels_manual, self._xformatter)
        yticks, self._y_offset_text = self._resolve_ticks_offset(
            self._yscale, yr[0], yr[1], 6, self._yticks_manual,
            self._yticklabels_manual, self._yformatter)

        # X tick label angle, and the band it needs at that angle. `_bands`
        # runs before `_draw`, so the angle chosen here is the one drawn.
        self._x_tick_deg = self._x_tick_angle(scene, xticks, xr)
        x_label_w = max((_tw(scene, lbl, _TICK_LABEL_SIZE) for _, lbl in xticks),
                        default=0.0)
        x_below, _l, _r = _tick_rotation_geometry(
            x_label_w, t_asc, t_desc, self._x_tick_deg)
        x_tick_h = _TICK_LENGTH + _TICK_LABEL_GAP + x_below
        y_label_w = max((_tw(scene, lbl, _TICK_LABEL_SIZE) for _, lbl in yticks), default=0.0)
        y_tick_w = _TICK_LENGTH + _TICK_LABEL_GAP + y_label_w

        # Corner text for a factored-out offset/multiplier. The x one sits on
        # its own line under the tick labels; the y one rides above the plot,
        # in the title band, which is the only space already above the axis.
        if self._x_offset_text and not self._frame_off:
            a, d = _th(scene, self._x_offset_text, _TICK_LABEL_SIZE, "body", t)
            x_tick_h += _OFFSET_TEXT_GAP + a + d
        offset_h = 0.0
        if self._y_offset_text and not self._frame_off:
            a, d = _th(scene, self._y_offset_text, _TICK_LABEL_SIZE, "body", t)
            offset_h = a + d + _OFFSET_TEXT_GAP

        # `axis("off")` - which `pie` implies - draws no tick and no tick label,
        # so a reserved tick band is empty by construction: it only pushes the
        # plot rect off-center inside the cell. On a pie that showed as a wide
        # blank strip down the left, the width of y labels that were never
        # drawn. The bands below (title, axis labels, colorbar, twins) still
        # draw with the frame off, so only these two are dropped.
        if self._frame_off:
            x_tick_h = y_tick_w = 0.0

        title_h = offset_h
        title_font = _font(t.title_weight)
        label_font = _font(t.axis_label_weight)
        if self._title:
            a, d = _th(scene, self._title, _TITLE_SIZE, title_font, t)
            title_h = a + d + _TITLE_GAP
        xlabel_h = 0.0
        if self._xlabel:
            a, d = _th(scene, self._xlabel, _AXIS_LABEL_SIZE, label_font, t)
            xlabel_h = a + d + _AXIS_LABEL_GAP
        ylabel_w = 0.0
        if self._ylabel:
            a, d = _th(scene, self._ylabel, _AXIS_LABEL_SIZE, label_font, t)
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
                    # Measured with `_th` on the *actual* label, not with the
                    # font's global line height: a label containing math has
                    # its own ascent and depth (a nested fraction is far taller
                    # than a line of text), and reserving `font_vmetrics` for
                    # it under-reserves the band the rotated label is then
                    # centered in - so its ink lands past the band's edge,
                    # which on an outermost band is the page edge.
                    a, d = _th(scene, cb["label"], _AXIS_LABEL_SIZE, label_font, t)
                    cbar_h += a + d + _AXIS_LABEL_GAP
            else:
                max_lbl = max(
                    (_tw(scene, lbl, _TICK_LABEL_SIZE) for _, lbl in cbticks),
                    default=0.0,
                )
                cbar_w = _CBAR_GAP + _CBAR_WIDTH + _CBAR_TICK_LEN + _CBAR_TICK_GAP + max_lbl
                if cb["label"]:
                    a, d = _th(scene, cb["label"], _AXIS_LABEL_SIZE, label_font, t)
                    cbar_w += a + d + _AXIS_LABEL_GAP

        # A twinx reserves right-side space for its y ticks/labels (shares the
        # cbar band slot); a twiny reserves top space in the title band.
        if self._twinx is not None and not self._colorbar:
            txr, tyr = self._twinx._ranges()
            tyt = self._twinx._yscale.ticks(tyr[0], tyr[1], 6)
            tlw = max((_tw(scene, lbl, _TICK_LABEL_SIZE) for _, lbl in tyt), default=0.0)
            cbar_w = _TICK_LENGTH + _TICK_LABEL_GAP + tlw
            if self._twinx._ylabel:
                a, d = _th(scene, self._twinx._ylabel, _AXIS_LABEL_SIZE, label_font, t)
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
                a, d = _th(scene, spec["label"], _AXIS_LABEL_SIZE, label_font, t)
                thick += _AXIS_LABEL_GAP + (a + d) + _AXIS_LABEL_GAP
            spec["_offset"] = outward[side]
            outward[side] += thick
            added[side] += thick
        title_h += added["top"]
        x_tick_h += added["bottom"]
        y_tick_w += added["left"]
        cbar_w += added["right"]
        self._sec_right_w = added["right"]

        # Horizontal room for the first and last x tick labels. Each is drawn
        # centered on its tick, and the outermost ticks sit on the plot's own
        # edges, so half of each label hangs outside the plot rect - past the
        # canvas on an outer column, where it used to be cut mid-glyph with
        # nothing said. The x tick band cannot hold this: it is exactly as wide
        # as the plot. So it is reserved beside the plot instead (see
        # `AxesBands::x_tick_overhang_l`).
        oh_l = oh_r = 0.0
        if xticks and not self._frame_off:
            _b, oh_l, _r = _tick_rotation_geometry(
                _tw(scene, xticks[0][1], _TICK_LABEL_SIZE), t_asc, t_desc,
                self._x_tick_deg)
            _b, _l, oh_r = _tick_rotation_geometry(
                _tw(scene, xticks[-1][1], _TICK_LABEL_SIZE), t_asc, t_desc,
                self._x_tick_deg)
        # The offset/multiplier is right-aligned at the plot's end, so it
        # overhangs nothing - but it does have to fit, and it is drawn on the
        # same side as the last tick label.
        if self._x_offset_text and not self._frame_off:
            oh_r = max(oh_r, 0.0)

        bands = (title_h, xlabel_h, ylabel_w, x_tick_h, y_tick_w, cbar_w, cbar_h,
                 oh_l, oh_r)
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
                     self._xscale.code, self._yscale.code, (px, py, pw, ph),
                     (plot.x, plot.y, plot.w, plot.h))

        # Theme: locals shadow the module defaults (sizes/colors) for this axes.
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
            # What abuts each end of a spine: the perpendicular edge at that
            # corner, or a tick sitting close enough to the end that its own
            # half-width overhangs it. `_spine_ends` turns that into how far to
            # run the spine past its endpoint. Edges a twin or a flush
            # secondary axis will draw count too - they are a corner from this
            # spine's point of view even though this axes is not drawing them.
            edges = set(t.spines)
            if self._twinx is not None:
                edges.add("right")
            if self._twiny is not None:
                edges.add("top")
            for spec in self._secondary:
                if not spec.get("_offset", 0.0):
                    edges.add(spec["loc"])
            x_at = [sx(v) for v, _ in xticks] + [sx(v) for v in x_minor]
            y_at = [sy(v) for v, _ in yticks] + [sy(v) for v in y_minor]
            # Vertical spines share their two ends' verdicts, horizontal ones
            # theirs: what a corner looks like does not depend on which of the
            # two spines meeting there is being drawn.
            v_lo, v_hi = self._spine_ends_for(y_at, py, py + ph, "top", "bottom", edges)
            h_lo, h_hi = self._spine_ends_for(x_at, px, px + pw, "left", "right", edges)
            if "left" in t.spines:
                scene.add_path([(px, py - v_lo), (px, py + ph + v_hi)],
                               stroke_color=_SPINE, stroke_width=sw, cap="butt")
            if "bottom" in t.spines:
                scene.add_path([(px - h_lo, py + ph), (px + pw + h_hi, py + ph)],
                               stroke_color=_SPINE, stroke_width=sw, cap="butt")
            if "right" in t.spines:
                scene.add_path([(px + pw, py - v_lo), (px + pw, py + ph + v_hi)],
                               stroke_color=_SPINE, stroke_width=sw, cap="butt")
            if "top" in t.spines:
                scene.add_path([(px - h_lo, py), (px + pw + h_hi, py)],
                               stroke_color=_SPINE, stroke_width=sw, cap="butt")

        # All data marks, clipped to the plot rect.
        marks = self._ordered_marks()
        scene.begin_group(1.0, 0.0, 0.0, 1.0, 0.0, 0.0, clip=(px, py, pw, ph))
        for m in marks:
            self._draw_mark(scene, m, proj)
        scene.end_group()

        # Pie slice labels sit outside the rim, and so outside the clip: they
        # are placed against the rect rather than in data space.
        for m in marks:
            if m["kind"] == "pie":
                _pie.draw_labels(self, scene, m, proj)

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
            top = py + ph + _TICK_LENGTH + _TICK_LABEL_GAP
            if self._x_tick_deg:
                _draw_rotated_tick_label(scene, x, top, label, _TICK_LABEL_SIZE,
                                         _BLACK, self._x_tick_deg, t)
            else:
                tw = _tw(scene, label, _TICK_LABEL_SIZE)
                _text(scene, x - tw / 2.0, top + t_asc, label, _TICK_LABEL_SIZE, _BLACK)

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

        # Shared offset/multiplier, written once instead of on every label.
        # The x term is right-aligned under the end of the axis and the y term
        # sits above its top-left corner, which is where a reader looks for the
        # units of the axis they just read.
        if not self._frame_off and self._x_offset_text:
            txt = self._x_offset_text
            a, _d = _th(scene, txt, _TICK_LABEL_SIZE, "body", t)
            ow = _tw(scene, txt, _TICK_LABEL_SIZE, "body", t)
            baseline = (py + ph + _TICK_LENGTH + _TICK_LABEL_GAP
                        + t_asc + t_desc + _OFFSET_TEXT_GAP + a)
            _text(scene, px + pw - ow, baseline, txt, _TICK_LABEL_SIZE, _BLACK, "body", t)
        if not self._frame_off and self._y_offset_text:
            txt = self._y_offset_text
            _a, d = _th(scene, txt, _TICK_LABEL_SIZE, "body", t)
            _text(scene, px, py - _OFFSET_TEXT_GAP - d, txt, _TICK_LABEL_SIZE,
                  _BLACK, "body", t)

        # Title, centered over the plot area.
        title_font = _font(t.title_weight)
        label_font = _font(t.axis_label_weight)
        if self._title:
            a, _d = _th(scene, self._title, _TITLE_SIZE, title_font, t)
            tw = _tw(scene, self._title, _TITLE_SIZE, title_font, t)
            baseline = layout.title.y + a
            _text(scene, px + (pw - tw) / 2.0, baseline, self._title, _TITLE_SIZE,
                  _BLACK, title_font, t)

        # X-axis label, centered over the plot area.
        if self._xlabel:
            a, _d = _th(scene, self._xlabel, _AXIS_LABEL_SIZE, label_font, t)
            tw = _tw(scene, self._xlabel, _AXIS_LABEL_SIZE, label_font, t)
            baseline = layout.xlabel.y + a
            _text(scene, px + (pw - tw) / 2.0, baseline, self._xlabel, _AXIS_LABEL_SIZE,
                  _BLACK, label_font, t)

        # Y-axis label, rotated 90deg CCW, centered on the plot area's height.
        if self._ylabel:
            # `_th`, not `font_vmetrics`: the band was reserved from the label's
            # own extents, so the pivot has to be computed from the same ones or
            # the label is centered against a box it does not have.
            a, d = _th(scene, self._ylabel, _AXIS_LABEL_SIZE, label_font, t)
            tw = _tw(scene, self._ylabel, _AXIS_LABEL_SIZE, label_font, t)
            band = layout.ylabel
            pivot_x = band.x + band.w / 2.0 - (d - a) / 2.0
            pivot_y = py + ph / 2.0
            # Affine = translate(pivot) * rotate(-90deg): (x,y) -> (y+px, -x+py).
            scene.begin_group(0.0, -1.0, 1.0, 0.0, pivot_x, pivot_y)
            _text(scene, -tw / 2.0, 0.0, self._ylabel, _AXIS_LABEL_SIZE, _BLACK, label_font, t)
            scene.end_group()

        # Annotations (text + callout arrows), on top of the data.
        if self._annotations:
            self._draw_annotations(scene, sx, sy)

        # Colorbar, drawn in its reserved right-hand band (outside the clip).
        if self._colorbar is not None:
            _colorbar.draw(self, scene, layout)

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
                            an.get("rotation", 0.0), self._theme)
            else:  # plain text
                _place_text(scene, sx(an["x"]), sy(an["y"]), an["s"], size, color,
                            an["ha"], an["va"], an.get("font", "body"),
                            an.get("rotation", 0.0), self._theme)

    # -- twin / secondary / inset drawing -----------------------------------

    def _spine_ends_for(self, tick_at, lo, hi, lo_side, hi_side, edges=None):
        """How far a spine runs past its ``lo``/``hi`` ends (see `_spine_ends`).

        ``tick_at`` is where this spine's ticks landed in device space; a tick
        within half a stroke width of an end is one that would otherwise jut
        past it. ``lo_side``/``hi_side`` name the perpendicular edges meeting
        those ends, looked up in ``edges`` (the theme's spines unless the caller
        knows of more - a twin draws edges the theme does not list).
        """
        t = self._theme
        sw = t.spine_width
        half = sw / 2.0
        if edges is None:
            edges = t.spines

        def meets(edge, side):
            return side in edges or any(abs(c - edge) < half for c in tick_at)

        return _spine_ends(t.spine_join, sw, meets(lo, lo_side), meets(hi, hi_side))

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
        return _Proj(sx, sy, (ax_c, bx_c, ay_c, by_c), xscale.code, yscale.code,
                     (px, py, pw, ph))

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
            twticks = list(tw._yscale.ticks(tyr[0], tyr[1], 6))
            lo, hi = self._spine_ends_for(
                [proj.sy(v) for v, _ in twticks], plot.y, plot.y1, "top", "bottom")
            scene.add_path([(plot.x1, plot.y - lo), (plot.x1, plot.y1 + hi)],
                           stroke_color=_SPINE, stroke_width=sw, cap="butt")
            for val, label in twticks:
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
            twticks = list(tw._xscale.ticks(txr[0], txr[1], 7))
            lo, hi = self._spine_ends_for(
                [proj.sx(v) for v, _ in twticks], plot.x, plot.x1, "left", "right")
            scene.add_path([(plot.x - lo, plot.y), (plot.x1 + hi, plot.y)],
                           stroke_color=_SPINE, stroke_width=sw, cap="butt")
            for val, label in twticks:
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
        """A rotated axis label centered in ``band``, reading top-to-bottom on the
        right (matching a twinx's y label) and bottom-to-top on the left
        (matching the primary y label)."""
        t = self._theme
        size = t.axis_label_size
        a, d = _th(scene, text, size, _font(t.axis_label_weight), t)
        tw = _tw(scene, text, size, _font(t.axis_label_weight), t)
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
        # An offset axis floats clear of the plot rect, so no spine of this
        # axes reaches its ends - only its own limit ticks can overhang them.
        corners = self._theme.spines if not off else ()
        if spec["axis"] == "x":
            top = spec["loc"] == "top"
            edge_y = plot.y - off if top else plot.y1 + off
            direction = -1.0 if top else 1.0
            xs_at = [x for x in (hproj.sx(inv(v)) for v, _ in ticks)
                     if plot.x - 0.5 <= x <= plot.x1 + 0.5]
            lo, hi = self._spine_ends_for(xs_at, plot.x, plot.x1, "left", "right",
                                          corners)
            scene.add_path([(plot.x - lo, edge_y), (plot.x1 + hi, edge_y)],
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
            ys_at = [y for y in (hproj.sy(inv(v)) for v, _ in ticks)
                     if plot.y - 0.5 <= y <= plot.y1 + 0.5]
            lo, hi = self._spine_ends_for(ys_at, plot.y, plot.y1, "top", "bottom",
                                          corners)
            scene.add_path([(edge_x, plot.y - lo), (edge_x, plot.y1 + hi)],
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
                               stroke_color=m["edgecolor"], stroke_width=1.0)
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
            # Stroked in its own face color (matplotlib's `edgecolors="face"`).
            # Neighboring hexagons abut exactly, so an antialiased fill splits
            # the pixels along a shared edge between them - each covers part of
            # the pixel, but they are composited one after the other, so the
            # background shows through in the gap and the lattice reads as a
            # mesh of pale seams. The stroke straddles the edge and paints that
            # sliver solid. See `_SEAM_STROKE`.
            #
            # Only for opaque fills: a translucent hexagon would composite its
            # own outline a second time over its own edge, trading the pale
            # seam for a darker one, which is the more visible artifact of the
            # two. Sealing that case needs the whole mark composited as a layer.
            opaque = all(c[3] >= 255 for c in m["colors"])
            for (cx, cy), col in zip(m["centers"], m["colors"]):
                poly = [(sx(cx + ox), sy(cy + oy)) for ox, oy in m["offsets"]]
                scene.add_path(poly, fill_color=col, close=True,
                               stroke_color=col if opaque else None,
                               stroke_width=_SEAM_STROKE, join="round")
        elif kind == "quadmesh":
            for x0, x1, y0, y1, col in m["quads"]:
                scene.add_path([(sx(x0), sy(y0)), (sx(x1), sy(y0)),
                                (sx(x1), sy(y1)), (sx(x0), sy(y1))],
                               fill_color=col, close=True)
        elif kind == "contour":
            xc, yc, w = m["xcoords"], m["ycoords"], m["linewidth"]
            # One path per continuous line, not per marching-squares cell: a
            # per-cell path meets its neighbor butt-cap to butt-cap and leaves a
            # wedge of background showing at every turn. Round joins close them.
            for li, closed, pts in m["lines"]:
                col = m["colors"][li] if li < len(m["colors"]) else m["colors"][-1]
                scene.add_path(
                    [(sx(_interp_coord(xc, px)), sy(_interp_coord(yc, py)))
                     for px, py in pts],
                    stroke_color=col, stroke_width=w, close=closed, join="round")
        elif kind == "contourf":
            self._draw_field_image(scene, m, sx, sy)
        elif kind == "quiver":
            for x, y, u, v in zip(m["xs"], m["ys"], m["us"], m["vs"]):
                _draw_arrow(scene, sx(x), sy(y),
                            sx(x + u * m["scale"]), sy(y + v * m["scale"]),
                            m["color"], m["linewidth"], head_len=6.0, head_w=2.5)
        elif kind == "pie":
            _pie.draw(self, scene, m, proj)

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
        # Same rule as `_draw_image`: an inverted axis is a flip of the grid,
        # not a negative extent. `contourf`/`pcolormesh`/`hist2d` land here.
        left, right = sx(x0), sx(x1)
        top, bot = sy(max(y0, y1)), sy(min(y0, y1))
        rx, rw = min(left, right), abs(right - left)
        ry, rh = min(top, bot), abs(bot - top)
        scene.add_image(m["img"], m["uw"], m["uh"], rx, ry, rw, rh,
                        right < left, bot < top)


    def _draw_image(self, scene, m: dict, sx, sy) -> None:
        x0, x1, y0, y1 = m["extent"]
        w, h = m["w"], m["h"]
        if w == 0 or h == 0:
            return
        # Device bbox of the extent, plus the *direction* each axis runs in.
        #
        # Taking abs() of the extents and stopping there is what made an
        # inverted axis lie: the rect came out right and the pixels came out in
        # the wrong order. A decreasing projection has to reach the image as a
        # flip of the grid, never as a negative width or height - the rect says
        # only where the image goes (see `Scene.add_colormapped_image`).
        left, right = sx(x0), sx(x1)
        top, bot = sy(max(y0, y1)), sy(min(y0, y1))
        rx, rw = min(left, right), abs(right - left)
        ry, rh = min(top, bot), abs(bot - top)
        flip_x = right < left
        # `top` is the device y of the *larger* data y, so on an ordinary
        # (y-up) axis it is the smaller device y. When it is not, the y axis is
        # inverted and the rows have to be mirrored to match.
        flip_y = bot < top

        # 256-entry RGBA LUT; the per-pixel lookup (the hot loop) runs in Rust
        # via add_colormapped_image, reading `flat` - already row-major and
        # contiguous from ingest - straight out of its buffer. `_norm_lut`
        # returns the code Rust should run, folding the norm into the table
        # when there is no code for it.
        lut, norm_code = _norm_lut(m["cmap"], m["norm"], m.get("alpha", 1.0))
        flat = m["flat"]
        origin_upper = (m["origin"] == "upper") != flip_y
        scene.add_colormapped_image(flat, w, h, m["vmin"], m["vmax"], lut,
                                    origin_upper, rx, ry, rw, rh,
                                    norm_code, flip_x)

    def _draw_errorbar(self, scene, m: dict, proj: "_Proj") -> None:
        """Draw one errorbar mark.

        Takes the whole ``_Proj`` rather than bare ``sx``/``sy`` closures:
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

    # -- legend -------------------------------------------------------------

    def _legend_entries(self) -> list[dict]:
        """Labeled 2D marks, passed through with their kind intact so the glyph
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
            bx, by = _best_legend_position(self._marks, positions, box_w, box_h, proj)
        else:
            bx, by = positions.get(loc, (right, top))
        _draw_legend_box(scene, entries, bx, by, mt)
