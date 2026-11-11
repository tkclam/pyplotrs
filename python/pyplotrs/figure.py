"""Figures: a page holding a grid of axes, and how it is saved.

    fig, ax = pp.subplots()
    fig, axs = pp.subplots(2, 3, figsize=(180, 100), units="mm", sharex=True)
    fig, axd = pp.subplot_mosaic("AAB;CDB")

Sizes are in points by default, so a figure can be planned against its type
size; the 250 x 200 pt default is one journal column wide.
"""

from __future__ import annotations

import html
import os
import textwrap
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, overload

from . import _data, _frame, _legend
from ._canvas import Canvas
from ._frame import ColorbarSpec, Margins
from .artists import Mappable
from .axes import Axes, AxesBase
from .colors import to_hex
from .text import Label, as_label, plain
from .theme import Theme, resolve

if TYPE_CHECKING:
    from .axes3d import Axes3D
    from .polar import PolarAxes

__all__ = ["Figure", "figure", "subplot_mosaic", "subplots"]

DEFAULT_FIGSIZE = (250.0, 200.0)
OUTER = 6.0  # page margin
WSPACE = 16.0  # between one plot's frame and the next one's
HSPACE = 14.0
SUPTITLE_GAP = 6.0
LEGEND_GAP = 10.0
INLINE_DPI = 150.0

Projection = Literal["3d", "polar"] | None
Share = bool | Literal["row", "col"]
Span = tuple[int, int, int, int]  # row, col, rowspan, colspan


def _axes_class(projection: Projection) -> type:
    if projection is None:
        return Axes
    if projection == "3d":
        from .axes3d import Axes3D

        return Axes3D
    if projection == "polar":
        from .polar import PolarAxes

        return PolarAxes
    raise ValueError(f"unknown projection {projection!r}; expected None, '3d' or 'polar'")


class Figure:
    """A page holding axes on a grid. Create with `subplots`, `subplot_mosaic`
    or `figure`."""

    def __init__(
        self,
        figsize: tuple[float, float] = DEFAULT_FIGSIZE,
        *,
        units: str = "pt",
        theme: Theme | str | None = None,
        nrows: int = 1,
        ncols: int = 1,
        width_ratios: Sequence[float] | None = None,
        height_ratios: Sequence[float] | None = None,
        sharex: Share = False,
        sharey: Share = False,
    ) -> None:
        self.size = _data.figsize_points(figsize, units)
        self.theme = resolve(theme)
        self.nrows, self.ncols = int(nrows), int(ncols)
        self.width_ratios = _ratios(width_ratios, self.ncols, "width_ratios")
        self.height_ratios = _ratios(height_ratios, self.nrows, "height_ratios")
        self.sharex, self.sharey = sharex, sharey
        self.suptitle: Label | None = None
        self._slots: list[tuple[Any, Span]] = []
        self._legend: _legend.LegendSpec | None = None

    # -- building ------------------------------------------------------------------

    @property
    def axes(self) -> list[Any]:
        """Every axes in the figure, in the order added."""
        return [ax for ax, _ in self._slots]

    @overload
    def add_axes(
        self,
        row: int = 0,
        col: int = 0,
        rowspan: int = 1,
        colspan: int = 1,
        *,
        projection: None = None,
    ) -> Axes: ...
    @overload
    def add_axes(
        self,
        row: int = 0,
        col: int = 0,
        rowspan: int = 1,
        colspan: int = 1,
        *,
        projection: Literal["3d"],
    ) -> Axes3D: ...
    @overload
    def add_axes(
        self,
        row: int = 0,
        col: int = 0,
        rowspan: int = 1,
        colspan: int = 1,
        *,
        projection: Literal["polar"],
    ) -> PolarAxes: ...

    def add_axes(
        self,
        row: int = 0,
        col: int = 0,
        rowspan: int = 1,
        colspan: int = 1,
        *,
        projection: Projection = None,
    ) -> Any:
        """Add an axes covering grid cells ``row..row+rowspan``, ``col..col+colspan``."""
        if not (
            row >= 0
            and col >= 0
            and rowspan >= 1
            and colspan >= 1
            and row + rowspan <= self.nrows
            and col + colspan <= self.ncols
        ):
            raise ValueError(
                f"cells ({row}, {col}) + ({rowspan}, {colspan}) fall outside the "
                f"{self.nrows}x{self.ncols} grid"
            )
        ax = _axes_class(projection)(self.theme, self)
        self._slots.append((ax, (row, col, rowspan, colspan)))
        return ax

    def set(self, *, suptitle: Label | None = None) -> Figure:
        """Set the figure title."""
        if suptitle is not None:
            self.suptitle = as_label(suptitle)
        return self

    def legend(
        self,
        loc: Literal["right", "bottom"] = "right",
        *,
        ncols: int | None = None,
        title: Label | None = None,
        frameon: bool = False,
        fontsize: float | None = None,
    ) -> None:
        """One legend for the labeled marks of every axes, in its own space
        beside (``"right"``) or below (``"bottom"``) the plots."""
        if loc not in ("right", "bottom"):
            raise ValueError(f"figure legend loc must be 'right' or 'bottom', got {loc!r}")
        self._legend = _legend.LegendSpec(
            "best", ncols or (1 if loc == "right" else 4), title, frameon, fontsize
        )
        self._legend_loc = loc

    def colorbar(
        self,
        mappable: Mappable,
        *,
        label: Label | None = None,
        orientation: Literal["vertical", "horizontal"] = "vertical",
        shrink: float = 1.0,
        ticks: Sequence[float] | None = None,
        format: Any = None,
    ) -> None:
        """A colorbar for a colormapped mark (from ``imshow``, ``scatter(c=...)``,
        ``contourf``, ...), beside or below the axes holding it."""
        if getattr(mappable, "cmap", None) is None or getattr(mappable, "norm", None) is None:
            raise TypeError(
                "colorbar() needs a colormapped mark, e.g. the result of imshow() or scatter(c=...)"
            )
        if orientation not in ("vertical", "horizontal"):
            raise ValueError(f"orientation must be 'vertical' or 'horizontal', got {orientation!r}")
        ax = self._owner(mappable)
        ax._colorbar = ColorbarSpec(
            mappable,
            None if label is None else as_label(label),
            orientation,
            float(shrink),
            None if ticks is None else [float(t) for t in ticks],
            format,
        )

    def _owner(self, artist: Any) -> Axes:
        for ax in self.axes:
            if not isinstance(ax, Axes):
                continue
            if artist in ax._artists:
                return ax
            for twin, _ in ax._twins:
                if artist in twin._artists:
                    return ax
        raise ValueError("that mark does not belong to a 2D axes in this figure")

    # -- layout ----------------------------------------------------------------------

    def _share_groups(self, which: str) -> list[list[Axes]]:
        mode = self.sharex if which == "x" else self.sharey
        flat = [(ax, s) for ax, s in self._slots if isinstance(ax, Axes)]
        if not mode:
            return []
        if mode is True:
            return [[ax for ax, _ in flat]]
        key = (lambda s: s[1]) if mode == "col" else (lambda s: s[0])
        groups: dict[int, list[Axes]] = {}
        for ax, s in flat:
            groups.setdefault(key(s), []).append(ax)
        return list(groups.values())

    def _views(self) -> dict[int, tuple[tuple[float, float], tuple[float, float]]]:
        views = {id(ax): ax._data_view() for ax in self.axes if isinstance(ax, Axes)}
        for i, which in enumerate("xy"):
            for group in self._share_groups(which):
                spans = [views[id(ax)][i] for ax in group]
                lo = min(min(r) for r in spans)
                hi = max(max(r) for r in spans)
                for ax in group:
                    own = views[id(ax)]
                    r = (hi, lo) if own[i][0] > own[i][1] else (lo, hi)
                    views[id(ax)] = (r, own[1]) if i == 0 else (own[0], r)
        return views

    def _view_of(self, ax: Axes) -> tuple[tuple[float, float], tuple[float, float]]:
        return self._views().get(id(ax)) or ax._data_view()

    def _tracks(
        self,
        start: float,
        total: float,
        n: int,
        ratios: list[float],
        before: list[float],
        after: list[float],
        gap: float,
    ) -> list[tuple[float, float]]:
        """``(offset, size)`` of each plot along one direction, leaving every
        track the margins its axes need."""
        spacing = before[0] + after[-1] + sum(after[i] + gap + before[i + 1] for i in range(n - 1))
        avail = max(total - spacing, 10.0 * n)
        at, out = start + before[0], []
        for i in range(n):
            size = avail * ratios[i] / sum(ratios)
            out.append((at, size))
            at += size + (after[i] + gap + before[i + 1] if i < n - 1 else 0.0)
        return out

    def _render(self, transparent: bool = False) -> Canvas:
        w, h = self.size
        th = self.theme
        canvas = Canvas(w, h, th)
        if th.figure_facecolor is not None and not transparent:
            canvas.rects([0.0], [0.0], [w], [h], fill=th.figure_facecolor)
        top, bottom, left, right = OUTER, h - OUTER, OUTER, w - OUTER

        title_lines: list[Label] = []
        if self.suptitle:
            title_lines = _wrap(
                canvas, self.suptitle, w - 2 * OUTER, th.suptitle_size, th.suptitle_weight
            )
            for line in title_lines:
                top += canvas.measure(line, th.suptitle_size, th.suptitle_weight).height
            top += SUPTITLE_GAP

        legend_box = None
        if self._legend is not None:
            seen: set[str] = set()
            items = []
            for ax in self.axes:
                pool = list(ax._artists) + [
                    a for t, _ in getattr(ax, "_twins", []) for a in t._artists
                ]
                for label, key in _legend.entries(pool):
                    if plain(label) not in seen:
                        seen.add(plain(label))
                        items.append((label, key))
            if items:
                legend_box = _legend.measure(canvas, items, self._legend)
                if self._legend_loc == "right":
                    right -= legend_box.width + LEGEND_GAP
                else:
                    bottom -= legend_box.height + LEGEND_GAP

        views = self._views()
        width_hint = (right - left) / max(self.ncols, 1) - 50.0
        height_hint = (bottom - top) / max(self.nrows, 1) - 40.0
        plans: list[Any] = []
        margins: list[Margins] = []
        for ax, (_, _, rs, cs) in self._slots:
            if isinstance(ax, Axes):
                xr, yr = views[id(ax)]
                plan = _frame.measure(ax, canvas, xr, yr, width_hint * cs, height_hint * rs)
                plans.append(plan)
                margins.append(plan.margins)
            else:
                plan = ax._measure(canvas)
                plans.append(plan)
                margins.append(plan.margins)

        def edge(attr: str, index: int, is_start: bool, along_rows: bool) -> float:
            best = 0.0
            for (_, (r, c, rs, cs)), m in zip(self._slots, margins, strict=True):
                pos = (
                    (r if is_start else r + rs - 1)
                    if along_rows
                    else (c if is_start else c + cs - 1)
                )
                if pos == index:
                    best = max(best, getattr(m, attr))
            return best

        cols = self._tracks(
            left,
            right - left,
            self.ncols,
            self.width_ratios,
            [edge("left", c, True, False) for c in range(self.ncols)],
            [edge("right", c, False, False) for c in range(self.ncols)],
            WSPACE,
        )
        rows = self._tracks(
            top,
            bottom - top,
            self.nrows,
            self.height_ratios,
            [edge("top", r, True, True) for r in range(self.nrows)],
            [edge("bottom", r, False, True) for r in range(self.nrows)],
            HSPACE,
        )

        for (ax, (r, c, rs, cs)), plan in zip(self._slots, plans, strict=True):
            x0, _ = cols[c]
            x1 = cols[c + cs - 1][0] + cols[c + cs - 1][1]
            y0, _ = rows[r]
            y1 = rows[r + rs - 1][0] + rows[r + rs - 1][1]
            rect = (x0, y0, x1 - x0, y1 - y0)
            if isinstance(ax, Axes):
                _frame.draw(ax, canvas, plan, rect)
            else:
                ax._draw(canvas, plan, rect)

        y = OUTER
        for line in title_lines:
            e = canvas.measure(line, th.suptitle_size, th.suptitle_weight)
            canvas.text(
                w / 2, y + e.ascent, line, th.suptitle_size, weight=th.suptitle_weight, ha="center"
            )
            y += e.height
        if legend_box is not None:
            grid_top, grid_bottom = rows[0][0], rows[-1][0] + rows[-1][1]
            grid_left, grid_right = cols[0][0], cols[-1][0] + cols[-1][1]
            if self._legend_loc == "right":
                lx = w - OUTER - legend_box.width
                ly = (grid_top + grid_bottom - legend_box.height) / 2
            else:
                lx = (grid_left + grid_right - legend_box.width) / 2
                ly = h - OUTER - legend_box.height
            _legend.draw(canvas, legend_box, lx, ly)
        return canvas

    # -- output ----------------------------------------------------------------------

    def _description(self) -> tuple[str, str]:
        """``(title, alt text)`` for accessible output, from the figure's labels."""
        parts = [plain(self.suptitle)] if self.suptitle else []
        for ax in self.axes:
            if ax.title:
                parts.append(plain(ax.title))
            xl, yl = (
                getattr(getattr(ax, "xaxis", None), "label", None),
                getattr(getattr(ax, "yaxis", None), "label", None),
            )
            if xl and yl:
                parts.append(f"{plain(yl)} versus {plain(xl)}")
        title = plain(self.suptitle) if self.suptitle else (parts[0] if parts else "Figure")
        return title, "; ".join(parts) or "Figure"

    def to_bytes(
        self,
        format: Literal["png", "pdf", "svg", "html"] = "png",
        *,
        dpi: float = 200.0,
        transparent: bool = False,
        tagged: bool = False,
        title: str | None = None,
        alt: str | None = None,
    ) -> bytes:
        """The figure as a file's bytes. See `save`."""
        if not (0 < dpi < float("inf")):
            raise ValueError(f"dpi must be positive and finite, got {dpi!r}")
        if format == "html":
            return self._html(title, alt, transparent, dpi).encode()
        if any(not isinstance(ax, AxesBase) for ax in self.axes):
            raise TypeError("unexpected axes type")
        scene = self._render(transparent).scene
        if format == "png":
            return scene.to_png(dpi=dpi, transparent=transparent)
        if format == "pdf":
            auto_title, auto_alt = self._description()
            return scene.to_pdf(
                dpi=dpi, tagged=tagged, title=title or auto_title, alt=alt or auto_alt
            )
        if format == "svg":
            return scene.to_svg(dpi=dpi).encode()
        raise ValueError(f"unknown format {format!r}; expected png, pdf, svg or html")

    def save(
        self,
        path: str | os.PathLike[str],
        *,
        dpi: float = 200.0,
        transparent: bool = False,
        tagged: bool = False,
        title: str | None = None,
        alt: str | None = None,
    ) -> None:
        """Save to ``path``; the extension picks the format.

        * ``.pdf``: vector, with real (selectable, editable) embedded text.
          ``tagged=True`` writes an accessible PDF with ``title`` and ``alt``
          text (derived from the figure's labels when not given).
        * ``.svg``: vector, with real text and embedded fonts.
        * ``.png``: raster at ``dpi``.
        * ``.html``: a self-contained page; interactive for 3D figures.

        ``dpi`` also sets the resolution of images embedded in vector output.
        ``transparent`` drops the page background.
        """
        ext = os.path.splitext(os.fspath(path))[1].lower().lstrip(".")
        fmt = {"htm": "html"}.get(ext, ext)
        if fmt not in ("png", "pdf", "svg", "html"):
            raise ValueError(
                f"cannot tell the format of {os.fspath(path)!r}; use .pdf, .svg, .png or .html"
            )
        data = self.to_bytes(
            fmt, dpi=dpi, transparent=transparent, tagged=tagged, title=title, alt=alt
        )  # type: ignore[arg-type]
        with open(path, "wb") as f:
            f.write(data)

    def _html(self, title: str | None, alt: str | None, transparent: bool, dpi: float) -> str:
        auto_title, auto_alt = self._description()
        title, alt = title or auto_title, alt or auto_alt
        if any(getattr(ax, "is_3d", False) for ax in self.axes):
            from ._html3d import interactive_html

            return interactive_html(self, title, alt)
        svg = self._render(transparent).scene.to_svg(dpi=dpi)
        if svg.startswith("<?xml"):
            svg = svg[svg.index("?>") + 2 :].lstrip()
        svg = svg.replace("<svg ", f'<svg role="img" aria-label="{html.escape(alt)}" ', 1)
        face = self.theme.figure_facecolor
        page, sheet = ("#f5f5f5", "#fff") if face is None else (to_hex(face), to_hex(face))
        shadow = "box-shadow:0 1px 6px rgba(0,0,0,.15);" if face is None else ""
        return (
            textwrap.dedent(f"""\
            <!DOCTYPE html>
            <html lang="en">
            <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>{html.escape(title)}</title>
            <style>
            html,body{{margin:0;height:100%}}
            body{{display:flex;align-items:center;justify-content:center;background:{page}}}
            svg{{max-width:100%;height:auto;background:{sheet};{shadow}}}
            </style>
            </head>
            <body>
            """)
            + svg
            + "\n</body>\n</html>\n"
        )

    def _repr_png_(self) -> bytes:
        return self.to_bytes("png", dpi=INLINE_DPI)

    def __getattr__(self, name: str) -> Any:
        hints = {
            "savefig": "use save(path)",
            "tight_layout": "layout is automatic",
            "add_subplot": "use add_axes(row, col, ...)",
            "suptitle": "use set(suptitle=...)",
        }
        if hints.get(name):
            raise AttributeError(f"Figure has no {name!r}; {hints[name]}")
        raise AttributeError(f"'Figure' object has no attribute {name!r}")

    def __repr__(self) -> str:
        w, h = self.size
        return f"<Figure {w:g}x{h:g} pt, {len(self._slots)} axes>"


def _ratios(ratios: Sequence[float] | None, n: int, name: str) -> list[float]:
    if ratios is None:
        return [1.0] * n
    out = [float(r) for r in ratios]
    if len(out) != n or not all(r > 0 for r in out):
        raise ValueError(f"{name} needs {n} positive values, got {list(ratios)!r}")
    return out


def _wrap(canvas: Canvas, s: Label, width: float, size: float, weight: str) -> list[Label]:
    """Break a plain-text title onto lines no wider than ``width``."""
    if not isinstance(s, str) or canvas.measure(s, size, weight).width <= width:
        return [s]
    lines, current = [], ""
    for word in s.split():
        trial = f"{current} {word}".strip()
        if current and canvas.measure(trial, size, weight).width > width:
            lines.append(current)
            current = word
        else:
            current = trial
    return [*lines, current] if current else lines


# -- constructors --------------------------------------------------------------------


def figure(
    figsize: tuple[float, float] = DEFAULT_FIGSIZE,
    *,
    nrows: int = 1,
    ncols: int = 1,
    units: str = "pt",
    theme: Theme | str | None = None,
    **kwargs: Any,
) -> Figure:
    """An empty figure with a grid to place axes on with `Figure.add_axes`."""
    return Figure(figsize, units=units, theme=theme, nrows=nrows, ncols=ncols, **kwargs)


@overload
def subplots(
    nrows: Literal[1] = 1,
    ncols: Literal[1] = 1,
    *,
    figsize: tuple[float, float] = ...,
    units: str = ...,
    theme: Theme | str | None = ...,
    projection: None = None,
    sharex: Share = ...,
    sharey: Share = ...,
    width_ratios: Sequence[float] | None = ...,
    height_ratios: Sequence[float] | None = ...,
) -> tuple[Figure, Axes]: ...
@overload
def subplots(
    nrows: Literal[1] = 1,
    ncols: Literal[1] = 1,
    *,
    figsize: tuple[float, float] = ...,
    units: str = ...,
    theme: Theme | str | None = ...,
    projection: Literal["3d"],
    sharex: Share = ...,
    sharey: Share = ...,
    width_ratios: Sequence[float] | None = ...,
    height_ratios: Sequence[float] | None = ...,
) -> tuple[Figure, Axes3D]: ...
@overload
def subplots(
    nrows: Literal[1] = 1,
    ncols: Literal[1] = 1,
    *,
    figsize: tuple[float, float] = ...,
    units: str = ...,
    theme: Theme | str | None = ...,
    projection: Literal["polar"],
    sharex: Share = ...,
    sharey: Share = ...,
    width_ratios: Sequence[float] | None = ...,
    height_ratios: Sequence[float] | None = ...,
) -> tuple[Figure, PolarAxes]: ...
@overload
def subplots(
    nrows: int = 1,
    ncols: int = 1,
    *,
    figsize: tuple[float, float] = ...,
    units: str = ...,
    theme: Theme | str | None = ...,
    projection: Projection = None,
    sharex: Share = ...,
    sharey: Share = ...,
    width_ratios: Sequence[float] | None = ...,
    height_ratios: Sequence[float] | None = ...,
) -> tuple[Figure, Any]: ...


def subplots(
    nrows: int = 1,
    ncols: int = 1,
    *,
    figsize: tuple[float, float] = DEFAULT_FIGSIZE,
    units: str = "pt",
    theme: Theme | str | None = None,
    projection: Projection = None,
    sharex: Share = False,
    sharey: Share = False,
    width_ratios: Sequence[float] | None = None,
    height_ratios: Sequence[float] | None = None,
) -> tuple[Figure, Any]:
    """A figure with an ``nrows`` x ``ncols`` grid of axes.

    Returns ``(fig, ax)`` for one axes, ``(fig, [ax, ...])`` for a single row
    or column, and ``(fig, [[ax, ...], ...])`` otherwise. ``sharex``/``sharey``
    (``True``, ``"row"`` or ``"col"``) give axes the same limits.
    ``width_ratios``/``height_ratios`` size the plots relative to each other.
    """
    fig = Figure(
        figsize,
        units=units,
        theme=theme,
        nrows=nrows,
        ncols=ncols,
        width_ratios=width_ratios,
        height_ratios=height_ratios,
        sharex=sharex,
        sharey=sharey,
    )
    grid = [[fig.add_axes(r, c, projection=projection) for c in range(ncols)] for r in range(nrows)]  # type: ignore[call-overload]
    if nrows == 1 and ncols == 1:
        return fig, grid[0][0]
    if nrows == 1 or ncols == 1:
        return fig, [ax for row in grid for ax in row]
    return fig, grid


def subplot_mosaic(
    layout: str | Sequence[Sequence[str]],
    *,
    figsize: tuple[float, float] = DEFAULT_FIGSIZE,
    units: str = "pt",
    theme: Theme | str | None = None,
    width_ratios: Sequence[float] | None = None,
    height_ratios: Sequence[float] | None = None,
    projection: dict[str, Projection] | None = None,
) -> tuple[Figure, dict[str, Any]]:
    """Axes laid out by name. Each letter names an axes; repeat it to span
    cells, and use ``.`` for an empty cell. Rows are lines or ``;``-separated::

        fig, axd = pp.subplot_mosaic('''
            AAB
            CDB
        ''')
        axd["A"].line(t, v)
    """
    if isinstance(layout, str):
        text = textwrap.dedent(layout).strip()
        rows = [
            list(r.strip())
            for r in (text.split(";") if ";" in text else text.splitlines())
            if r.strip()
        ]
    else:
        rows = [list(r) for r in layout]
    if not rows or len({len(r) for r in rows}) != 1:
        raise ValueError("every row of a mosaic must have the same number of cells")
    boxes: dict[str, list[int]] = {}
    for r, row in enumerate(rows):
        for c, name in enumerate(row):
            if name in (".", " "):
                continue
            b = boxes.setdefault(name, [r, c, r, c])
            b[0], b[1], b[2], b[3] = min(b[0], r), min(b[1], c), max(b[2], r), max(b[3], c)
    for name, (r0, c0, r1, c1) in boxes.items():
        if any(rows[r][c] != name for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)):
            raise ValueError(f"mosaic cells for {name!r} must form a rectangle")
    fig = Figure(
        figsize,
        units=units,
        theme=theme,
        nrows=len(rows),
        ncols=len(rows[0]),
        width_ratios=width_ratios,
        height_ratios=height_ratios,
    )
    proj = projection or {}
    axd = {
        name: fig.add_axes(r0, c0, r1 - r0 + 1, c1 - c0 + 1, projection=proj.get(name))  # type: ignore[call-overload]
        for name, (r0, c0, r1, c1) in boxes.items()
    }
    return fig, axd
