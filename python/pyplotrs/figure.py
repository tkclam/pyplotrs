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
import textwrap

from . import _pyplotrs_core as _core
from . import theme as _theme
from ._const import (
    _HSPACE,
    _INLINE_DPI,
    _LEGEND_COL_GAP_L,
    _LEGEND_COL_GAP_R,
    _OUTER_MARGIN,
    _TITLE_GAP,
    _WSPACE,
    DEFAULT_FIGSIZE,
)
from ._draw import (
    _draw_legend_box,
    _font,
    _measure_legend,
    _text,
    _th,
    _tw,
)
from ._util import _figsize_to_points
from .axes import Axes, Mappable
from .axes3d import Axes3D
from .polar import PolarAxes
from .theme import Theme


def _svg_to_html(svg: str, title: str, alt: str) -> str:
    """Wrap a standalone SVG document in a self-contained HTML5 page.

    The SVG is *inlined* (not referenced via ``<img>``), so the result is a
    single portable file that keeps real, selectable ``<text>`` and its embedded
    fonts; raster images inside the scene are already base64 data URIs, so the
    page fetches nothing when viewed. The figure is centered and shrinks to fit
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


# -- line styles ------------------------------------------------------------

# -- marker shapes ----------------------------------------------------------

# -- legend helpers (shared by per-axes and figure-level legends) -----------

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
    against its font scale — e.g. the default 250x200 pt figure with a 10 pt
    font. That default is a single journal column wide (~3.5 in), so a figure
    comes out at publication size instead of needing to be scaled down to one.
    Pass ``units="in"``, ``"cm"`` or ``"mm"`` to give the size in another unit
    (Nature's widths are 89 mm / 183 mm).
    """

    def __init__(self, figsize: tuple[float, float] = DEFAULT_FIGSIZE, nrows: int = 1,
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
        # Relative column widths / row heights. Normalized in the Rust solver, so
        # only the proportions matter; `None` means an even grid.
        self._width_ratios = None if width_ratios is None else [float(v) for v in width_ratios]
        self._height_ratios = (
            None if height_ratios is None else [float(v) for v in height_ratios])
        make = _axes_class(projection)
        self.axes = [self._adopt(make(self.theme)) for _ in range(nrows * ncols)]
        # Spanning placement (GridSpec / subplot_mosaic): one
        # (row, col, rowspan, colspan) per axes, or None for a uniform grid.
        self._spans: list[tuple[int, int, int, int]] | None = None

    def set(self, *, suptitle: str | None = None) -> "Figure":
        if suptitle is not None:
            self.suptitle = suptitle
        return self

    def _adopt(self, ax):
        """Give ``ax`` a back-reference to this figure.

        Only the getters need it, and only to answer honestly under
        ``sharex``/``sharey``: sharing is resolved in ``_build_scene``, so an
        axes asked for its limits in isolation would report its own data range
        and not the unified one that will be drawn."""
        ax._figure = self
        return ax

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
        ax = self._adopt(_axes_class(projection)(self.theme))
        self.axes.append(ax)
        self._spans.append((r0, c0, rs, cs))
        return ax

    def _has_3d(self) -> bool:
        """True if any axes is a 3D axes (a figure's axes are homogeneous)."""
        return any(isinstance(ax, Axes3D) for ax in self.axes)

    def legend(self, *, loc: str = "right", ncol: int = 1,
               title: str | None = None, frameon: bool = True,
               fontsize: float | None = None) -> "Figure":
        """Enable a single figure-level legend, collecting the labeled marks of
        every axes into one box placed in a reserved column to the right of the
        grid. Unlike :meth:`Axes.legend`, this is laid out as its own region and
        so can never overlap the data. ``loc`` currently supports ``"right"``.

        ``ncol``/``title``/``frameon``/``fontsize`` work as on
        :meth:`Axes.legend`; the reserved column is measured from them, so a
        two-column figure legend takes a wider, shorter band."""
        self._legend = {
            "loc": loc, "ncol": int(ncol), "title": title,
            "frameon": bool(frameon),
            "fontsize": None if fontsize is None else float(fontsize),
        }
        return self

    def _figure_legend_entries(self) -> list[dict]:
        """Labeled marks across every axes, de-duplicated by label so a series
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

    def colorbar(self, mappable: "Mappable", *, label: str | None = None,
                 orientation: str = "vertical", shrink: float = 1.0,
                 ticks=None, format=None) -> "Figure":
        """Attach a colorbar for ``mappable`` (from :meth:`Axes.imshow` or a
        colormapped :meth:`Axes.scatter`) in a reserved band beside its axes.
        The tick scale follows the mappable's ``norm`` (e.g. log ticks for
        a :class:`~pyplotrs.norms.LogNorm`).

        ``orientation="horizontal"`` puts the bar beneath the plot instead, in
        its own reserved band below the x-axis label. ``shrink`` scales the
        strip's length as a fraction of the plot extent, centered. ``ticks``
        pins the tick values and ``format`` accepts anything
        :mod:`pyplotrs.ticker` does - a formatter, a ``"{x:.2f}"`` template, or
        a callable."""
        if orientation not in ("vertical", "horizontal"):
            raise ValueError(
                f'orientation must be "vertical" or "horizontal", got {orientation!r}')
        mappable.ax._colorbar = {
            "cmap": mappable.cmap,
            "vmin": mappable.vmin,
            "vmax": mappable.vmax,
            "label": label,
            "norm": mappable.norm,
            "orientation": orientation,
            "shrink": float(shrink),
            "ticks": None if ticks is None else [float(v) for v in ticks],
            "format": format,
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
                box_w, _box_h, legend_mt = _measure_legend(scene, fig_entries, self.theme, self._legend)
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
             transparent: bool = False, title: str | None = None,
             alt: str | None = None) -> None:
        """Save to ``path``; the format is inferred from the extension
        (``.pdf``, ``.svg``, ``.png``, or ``.html``/``.htm``).

        ``transparent=True`` drops the white page fill from ``.png`` output in
        favor of an alpha channel. ``.pdf``/``.svg``/``.html`` paint no page
        background to begin with, so they are already "transparent" and ignore
        this flag.

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
                f.write(scene.to_png(dpi, transparent))
        else:
            raise ValueError(
                f"Unsupported file extension for {path_str!r}; "
                "expected .pdf, .svg, .png, or .html"
            )


def subplots(nrows: int = 1, ncols: int = 1, *, figsize: tuple[float, float] = DEFAULT_FIGSIZE,
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


def subplot_mosaic(mosaic, *, figsize: tuple[float, float] = DEFAULT_FIGSIZE,
                   theme=None, units: str = "pt"):
    """Build a figure of spanning axes from an ASCII ``mosaic`` layout.

    ``mosaic`` is a multi-line string (or a list of equal-length rows) whose
    repeated labels mark the cells each axes spans, e.g.::

        \"\"\"
        AB
        AC
        \"\"\"

    gives ``A`` spanning both rows of column 0, with ``B``/``C`` stacked at the
    right. ``"."`` (or a space) marks an empty cell. Returns
    ``(fig, {label: axes})``. Each label's cells must form a solid rectangle.

    The string is dedented before it is read, so the indented triple-quoted
    form above - the way a mosaic is actually written inside a function - means
    what it looks like. Without that, the shared leading spaces are cells of
    their own and the layout gains a phantom panel wider than the real ones.
    """
    if isinstance(mosaic, str):
        rows = [list(line) for line in textwrap.dedent(mosaic).splitlines()
                if line.strip()]
    else:
        rows = [list(r) for r in mosaic]
    nrows = len(rows)
    ncols = max((len(r) for r in rows), default=0)
    # Bounding box (min/max row & col) of each label's occupied cells.
    boxes: dict[str, list[int]] = {}
    order: list[str] = []
    for r, row in enumerate(rows):
        for c, label in enumerate(row):
            if label in (".", " "):
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
