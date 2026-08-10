"""Rectangles and the data-to-device projection.

``_Rect`` / ``_AxLayout`` / ``_layout_cell`` mirror the Rust layout solver's
band reservation, which Python needs for insets (placed on this side).
``_Proj`` carries the scale-aware device map plus the affine coefficients the
Rust fast paths consume.
"""

from __future__ import annotations


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
    title_h, xlabel_h, ylabel_w, x_tick_h, y_tick_w, cbar_w, cbar_h = bands
    ylabel = _Rect(cell.x, cell.y, ylabel_w, cell.h)
    y_tick_x = cell.x + ylabel_w
    title = _Rect(cell.x, cell.y, cell.w, title_h)
    plot_x = y_tick_x + y_tick_w
    plot_y = cell.y + title_h
    plot_w = max(cell.x1 - cbar_w - plot_x, 0.0)
    plot_h = max(cell.y1 - xlabel_h - x_tick_h - cbar_h - plot_y, 0.0)
    plot = _Rect(plot_x, plot_y, plot_w, plot_h)
    y_tick = _Rect(y_tick_x, plot_y, y_tick_w, plot_h)
    x_tick = _Rect(plot_x, plot.y1, plot_w, x_tick_h)
    xlabel = _Rect(plot_x, plot.y1 + x_tick_h, plot_w, xlabel_h)
    cbar = (_Rect(plot_x, plot.y1 + x_tick_h + xlabel_h, plot_w, cbar_h) if cbar_h > 0.0
            else _Rect(cell.x1 - cbar_w, cell.y, cbar_w, cell.h))
    return _AxLayout(cell=cell, plot=plot, title=title, xlabel=xlabel, ylabel=ylabel,
                     x_tick=x_tick, y_tick=y_tick, cbar=cbar)
