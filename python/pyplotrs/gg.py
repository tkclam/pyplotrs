"""pyplotrs.gg: a small declarative grammar-of-graphics layer.

Built directly on the imperative :class:`pyplotrs.Figure`/:class:`pyplotrs.Axes`
API and its mark vocabulary, so anything ``gg`` produces is an ordinary pyplotrs
figure (same editable-text PDF/SVG, same themes). A :class:`Plot` binds tabular
data to aesthetics (``x``, ``y``, ``color``), adds one or more *geoms*, and
optionally *facets* into small multiples::

    from pyplotrs.gg import Plot, Point, Line, facet

    (Plot(df, x="time", y="value", color="treatment")
        .add(Point())
        .add(Line())
        .facet(facet.wrap("subject", ncols=3))
        .labs(x="t (s)", y="response", title="Trials")
        .save("trials.pdf"))

Data may be a dict of columns, a list of record dicts, or any object exposing
``.columns`` + ``df[col]`` (pandas/polars) - no hard dependency on either.

A categorical ``color`` mapping splits the data into one series per level
(consistent palette colour + legend entry across geoms); faceting draws one
panel per level of a column with shared scales and a single figure legend.
"""

from __future__ import annotations

import math

from .figure import Figure, _figsize_to_points


class _Frame:
    """A minimal column store normalising the accepted input shapes to a dict
    of equal-length lists."""

    def __init__(self, data, _cols=None) -> None:
        if _cols is not None:
            self.cols = _cols
        elif isinstance(data, dict):
            self.cols = {k: list(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)) and data and isinstance(data[0], dict):
            keys = list(data[0].keys())
            self.cols = {k: [row.get(k) for row in data] for k in keys}
        elif hasattr(data, "columns") and hasattr(data, "__getitem__"):
            # pandas / polars style: df.columns + df[col] iterable
            self.cols = {c: list(data[c]) for c in list(data.columns)}
        else:
            raise TypeError(
                "gg.Plot data must be a dict of columns, a list of record dicts, "
                "or a DataFrame-like object (got "
                f"{type(data).__name__})"
            )
        self.n = len(next(iter(self.cols.values()))) if self.cols else 0

    def column(self, name):
        if name not in self.cols:
            raise KeyError(f"no column {name!r}; have {sorted(self.cols)}")
        return self.cols[name]

    def levels(self, name) -> list:
        """Distinct values of ``name`` in first-seen order."""
        seen: list = []
        s: set = set()
        for v in self.cols[name]:
            if v not in s:
                s.add(v)
                seen.append(v)
        return seen

    def where(self, name, value) -> "_Frame":
        idx = [i for i, v in enumerate(self.cols[name]) if v == value]
        return _Frame(None, _cols={k: [v[i] for i in idx] for k, v in self.cols.items()})


def _nums(values) -> list[float]:
    return [float(v) for v in values]


def _xy(frame: _Frame, mapping, *, sort: bool = False):
    xs = _nums(frame.column(mapping["x"]))
    ys = _nums(frame.column(mapping["y"]))
    if sort:
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        xs = [xs[i] for i in order]
        ys = [ys[i] for i in order]
    return xs, ys


# -- geoms ------------------------------------------------------------------

class Geom:
    """Base geom. Subclasses implement :meth:`draw` against one (sub)series."""

    def draw(self, ax, frame: _Frame, mapping: dict, color, label) -> None:  # pragma: no cover
        raise NotImplementedError


class Point(Geom):
    """Scatter points (``x``, ``y``)."""

    def __init__(self, *, size: float = 36.0, marker: str = "o") -> None:
        self.size = size
        self.marker = marker

    def draw(self, ax, frame, mapping, color, label) -> None:
        xs, ys = _xy(frame, mapping)
        ax.scatter(xs, ys, color=color, label=label, size=self.size, marker=self.marker)


class Line(Geom):
    """A polyline through (``x``, ``y``), sorted by ``x``."""

    def __init__(self, *, width: float | None = None, linestyle: str = "solid") -> None:
        self.width = width
        self.linestyle = linestyle

    def draw(self, ax, frame, mapping, color, label) -> None:
        xs, ys = _xy(frame, mapping, sort=True)
        ax.line(xs, ys, color=color, label=label, width=self.width, linestyle=self.linestyle)


class Area(Geom):
    """A filled area between ``y`` and a baseline (default 0)."""

    def __init__(self, *, baseline: float = 0.0, alpha: float = 0.4) -> None:
        self.baseline = baseline
        self.alpha = alpha

    def draw(self, ax, frame, mapping, color, label) -> None:
        xs, ys = _xy(frame, mapping, sort=True)
        ax.fill_between(xs, ys, self.baseline, color=color, alpha=self.alpha, label=label)


class Histogram(Geom):
    """A statistical geom: bin ``x`` into ``bins`` and draw counts."""

    def __init__(self, *, bins: int = 20, density: bool = False) -> None:
        self.bins = bins
        self.density = density

    def draw(self, ax, frame, mapping, color, label) -> None:
        xs = _nums(frame.column(mapping["x"]))
        ax.hist(xs, bins=self.bins, color=color, label=label, density=self.density)


# -- faceting ---------------------------------------------------------------

class _FacetWrap:
    def __init__(self, col: str, ncols: int = 3) -> None:
        self.col = col
        self.ncols = ncols


class facet:
    """Faceting specs namespace."""

    @staticmethod
    def wrap(col: str, ncols: int = 3) -> _FacetWrap:
        """One panel per level of ``col``, wrapped at ``ncols`` columns."""
        return _FacetWrap(col, ncols)


# -- the plot ---------------------------------------------------------------

class Plot:
    """A declarative plot specification. Chainable; terminal methods are
    :meth:`build` (returns a :class:`pyplotrs.Figure`) and :meth:`save`."""

    def __init__(self, data, *, x=None, y=None, color=None) -> None:
        self._frame = _Frame(data)
        self._mapping = {"x": x, "y": y, "color": color}
        self._geoms: list[Geom] = []
        self._facet: _FacetWrap | None = None
        self._theme = None
        self._labels: dict = {}
        self._figsize: tuple[float, float] | None = None

    # builders
    def add(self, geom: Geom) -> "Plot":
        """Add a geom (e.g. :class:`Point`, :class:`Line`). Geoms stack in the
        order added; returns ``self`` so calls chain."""
        self._geoms.append(geom)
        return self

    def facet(self, spec) -> "Plot":
        """Facet into small multiples, one panel per level of a column. ``spec``
        is a :func:`facet.wrap` spec (or a column name for the default wrap)."""
        if isinstance(spec, str):
            spec = _FacetWrap(spec)
        self._facet = spec
        return self

    def theme(self, theme) -> "Plot":
        """Set the :class:`~pyplotrs.theme.Theme` (or preset name) for the figure."""
        self._theme = theme
        return self

    def labs(self, *, x=None, y=None, title=None, color=None) -> "Plot":
        """Override axis/title labels (otherwise derived from the aesthetics)."""
        for k, v in (("x", x), ("y", y), ("title", title), ("color", color)):
            if v is not None:
                self._labels[k] = v
        return self

    def figsize(self, w: float, h: float, units: str = "pt") -> "Plot":
        """Set the figure ``(width, height)``, in **points** by default
        (``units="pt"``); pass ``units="in"``, ``"cm"`` or ``"mm"`` otherwise."""
        self._figsize = _figsize_to_points((w, h), units)
        return self

    # internals
    def _draw_panel(self, ax, frame: _Frame) -> bool:
        """Draw all geoms into ``ax`` for ``frame``. Returns whether a colour
        grouping (hence a legend) was applied."""
        color_col = self._mapping.get("color")
        if color_col and color_col in frame.cols:
            palette = ax._theme.palette
            for i, lvl in enumerate(frame.levels(color_col)):
                col = palette[i % len(palette)]
                sub = frame.where(color_col, lvl)
                for j, g in enumerate(self._geoms):
                    g.draw(ax, sub, self._mapping, col, str(lvl) if j == 0 else None)
            return True
        const = color_col if (color_col and color_col not in frame.cols) else None
        for g in self._geoms:
            g.draw(ax, frame, self._mapping, const, None)
        return False

    def _axis_labels(self) -> tuple[str | None, str | None]:
        return (self._labels.get("x", self._mapping.get("x")),
                self._labels.get("y", self._mapping.get("y")))

    def _global_xy(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Global (min, max) of the mapped x/y columns, for pinning blank
        facets. Falls back to (0, 1) when a column isn't numeric/present."""
        def rng(col):
            if col and col in self._frame.cols:
                try:
                    vs = _nums(self._frame.column(col))
                    return (min(vs), max(vs))
                except (TypeError, ValueError):
                    pass
            return (0.0, 1.0)
        return rng(self._mapping.get("x")), rng(self._mapping.get("y"))

    def build(self) -> Figure:
        """Realise the spec into a :class:`pyplotrs.Figure` (the terminal step).

        Raises :class:`ValueError` if no geom has been added."""
        if not self._geoms:
            raise ValueError("add at least one geom, e.g. .add(gg.Point())")
        xlab, ylab = self._axis_labels()
        grouped = self._mapping.get("color") in self._frame.cols

        if self._facet is not None:
            levels = self._frame.levels(self._facet.col)
            n = len(levels)
            ncols = max(1, min(self._facet.ncols, n))
            nrows = math.ceil(n / ncols)
            figsize = self._figsize or (min(3.1 * ncols + 0.8, 13.0) * 72.0,
                                        min(2.5 * nrows + 0.8, 10.0) * 72.0)
            fig = Figure(figsize=figsize, nrows=nrows, ncols=ncols,
                         sharex=True, sharey=True, theme=self._theme)
            for k, lvl in enumerate(levels):
                ax = fig.axes[k]
                self._draw_panel(ax, self._frame.where(self._facet.col, lvl))
                ax.set(title=f"{self._facet.col} = {lvl}", xlabel=xlab, ylabel=ylab)
            # Pin unused trailing panels to the global data range so they don't
            # distort the shared (sharex/sharey) scale.
            if n < nrows * ncols:
                gx, gy = self._global_xy()
                for k in range(n, nrows * ncols):
                    fig.axes[k].set(xlim=gx, ylim=gy)
            if self._labels.get("title"):
                fig.set(suptitle=self._labels["title"])
            if grouped:
                fig.legend()
            return fig

        fig = Figure(figsize=self._figsize or (480.0, 360.0), theme=self._theme)
        ax = fig.axes[0]
        legend = self._draw_panel(ax, self._frame)
        ax.set(title=self._labels.get("title"), xlabel=xlab, ylabel=ylab)
        if legend:
            ax.legend()
        return fig

    def save(self, path: str, **kwargs) -> None:
        """Build the figure and save it (see :meth:`pyplotrs.Figure.save`)."""
        self.build().save(path, **kwargs)


__all__ = ["Plot", "Point", "Line", "Area", "Histogram", "Geom", "facet"]
