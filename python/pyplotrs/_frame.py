"""Layout and drawing of a 2D axes' frame: ticks, spines, labels, title,
colorbar, twin axes and the legend.

Rendering happens in two passes. `measure` works out how much room the frame
needs around the plot area (the figure uses this to place every axes), and
`draw` paints the axes into the rectangle it was given.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from . import _core, _legend
from . import scales as _scales
from ._axis import Axis, Range, Ticks
from ._canvas import Canvas
from .artists import Mappable, View
from .colormaps import Colormap
from .norms import BoundaryNorm, Norm
from .text import Label

if TYPE_CHECKING:
    from .axes import Axes

Side = Literal["left", "right", "top", "bottom"]

TICK_LABEL_GAP = 2.5
AXIS_LABEL_GAP = 3.0
TITLE_GAP = 4.0
OFFSET_GAP = 3.0
CBAR_GAP = 8.0
CBAR_WIDTH = 11.0
MINOR_TICK = 0.6  # minor tick length relative to major


@dataclass
class Margins:
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0
    left: float = 0.0


@dataclass
class AxisBand:
    """Ticks and a label along one side of a rectangle, already measured."""

    side: Side
    ticks: Ticks
    label: Label | None
    rotation: float = 0.0
    thickness: float = 0.0
    tick_thickness: float = 0.0  # tick marks + tick labels, without the axis label


def _rotated(width: float, height: float, deg: float) -> tuple[float, float, float]:
    """``(below, left, right)`` extents of a label hung from its anchor at
    ``deg`` degrees, right end at the anchor."""
    if deg == 0:
        return height, width / 2, width / 2
    t = math.radians(deg)
    c, s = abs(math.cos(t)), abs(math.sin(t))
    return width * s + height * c, width * c + height * s, height * s


def measure_band(canvas: Canvas, band: AxisBand, show_ticks: bool = True) -> AxisBand:
    th = canvas.theme
    size = th.tick_label_size
    a, d = canvas.line_height(size)
    tick_out = th.tick_length if th.tick_direction == "out" else 0.0
    thick = 0.0
    if show_ticks:
        widths = [canvas.measure(s, size).width for s in band.ticks.labels]
        if band.side in ("top", "bottom"):
            below = max((_rotated(w, a + d, band.rotation)[0] for w in widths), default=0.0)
            thick = tick_out + TICK_LABEL_GAP + below
            if band.side == "bottom" and band.ticks.offset:
                thick += OFFSET_GAP + canvas.measure(band.ticks.offset, size).height
        else:
            thick = tick_out + TICK_LABEL_GAP + max(widths, default=0.0)
    band.tick_thickness = thick
    if band.label:
        thick += (
            AXIS_LABEL_GAP
            + canvas.measure(band.label, th.axis_label_size, th.axis_label_weight).height
        )
    band.thickness = thick
    return band


def draw_band(
    canvas: Canvas,
    band: AxisBand,
    rect: tuple[float, float, float, float],
    majors: list[float],
    minors: list[float],
    outset: float = 0.0,
    show_ticks: bool = True,
) -> None:
    """Draw ``band`` along ``rect`` (x, y, w, h). ``majors``/``minors`` are
    device positions along the side; ``outset`` moves the band outward."""
    th = canvas.theme
    x, y, w, h = rect
    size = th.tick_label_size
    a, d = canvas.line_height(size)
    out = 1.0 if th.tick_direction == "out" else -1.0
    tl = th.tick_length
    side = band.side
    sign = {"left": -1.0, "top": -1.0, "right": 1.0, "bottom": 1.0}[side]
    edge = {"left": x, "right": x + w, "top": y, "bottom": y + h}[side] + sign * outset
    horizontal = side in ("top", "bottom")
    if show_ticks:
        for positions, length in ((majors, tl), (minors, tl * MINOR_TICK)):
            if not positions:
                continue
            tip = edge + sign * out * length
            n = len(positions)
            if horizontal:
                canvas.segments(
                    positions,
                    [edge] * n,
                    positions,
                    [tip] * n,
                    color=th.spine_color,
                    width=th.spine_width,
                )
            else:
                canvas.segments(
                    [edge] * n,
                    positions,
                    [tip] * n,
                    positions,
                    color=th.spine_color,
                    width=th.spine_width,
                )
        start = edge + sign * (max(out, 0.0) * tl + TICK_LABEL_GAP)
        for pos, label in zip(majors, band.ticks.labels, strict=False):
            if side == "bottom":
                if band.rotation:
                    with canvas.group(_rotation(band.rotation, pos, start)):
                        canvas.text(0.0, a, label, size, ha="right")
                else:
                    canvas.text(pos, start + a, label, size, ha="center")
            elif side == "top":
                canvas.text(pos, start - d, label, size, ha="center")
            else:
                canvas.text(
                    start, pos + (a - d) / 2, label, size, ha="left" if side == "right" else "right"
                )
        if band.ticks.offset:
            if side == "bottom":
                oy = start + _rotated(0, a + d, band.rotation)[0] + OFFSET_GAP
                canvas.text(x + w, oy + a, band.ticks.offset, size, ha="right")
            elif side == "left":
                canvas.text(x, y - OFFSET_GAP - d, band.ticks.offset, size)
            elif side == "right":
                canvas.text(x + w, y - OFFSET_GAP - d, band.ticks.offset, size, ha="right")
    if band.label:
        ls, lw = th.axis_label_size, th.axis_label_weight
        e = canvas.measure(band.label, ls, lw)
        at = edge + sign * (band.tick_thickness + AXIS_LABEL_GAP)
        if side == "bottom":
            canvas.text(x + w / 2, at + e.ascent, band.label, ls, weight=lw, ha="center")
        elif side == "top":
            canvas.text(x + w / 2, at - e.depth, band.label, ls, weight=lw, ha="center")
        elif side == "left":
            canvas.text(
                at - e.depth, y + h / 2, band.label, ls, weight=lw, ha="center", rotation=90
            )
        else:
            canvas.text(
                at + e.ascent, y + h / 2, band.label, ls, weight=lw, ha="center", rotation=90
            )


def _rotation(deg: float, x: float, y: float) -> tuple[float, float, float, float, float, float]:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return (c, -s, s, c, x, y)


# -- colorbars ---------------------------------------------------------------------


@dataclass
class ColorbarSpec:
    mappable: Mappable
    label: Label | None = None
    orientation: Literal["vertical", "horizontal"] = "vertical"
    shrink: float = 1.0
    ticks: list[float] | None = None
    formatter: object = None
    band: AxisBand | None = None

    def norm(self) -> Norm:
        return self.mappable.norm

    def positions(self, values: list[float]) -> list[float]:
        """Positions in 0..1 along the strip."""
        n = self.norm()
        if isinstance(n, BoundaryNorm):
            b = n.boundaries
            return [_piecewise(b, v) for v in values]
        return [n(v) for v in values]

    def located(self, minus: bool) -> Ticks:
        n = self.norm()
        if self.ticks is not None:
            values = list(self.ticks)
            from .ticker import plain

            labels: list[Any] = [plain(v, minus) for v in values]
        else:
            pairs = n.ticks(6, minus)
            values, labels = [v for v, _ in pairs], [s for _, s in pairs]
        if self.formatter is not None:
            from .ticker import format_ticks, get

            fmt = get(self.formatter)  # type: ignore[arg-type]
            assert fmt is not None
            labels = list(format_ticks(fmt, values, minus))
        if self.ticks is None and len(values) > 7:  # e.g. many contour levels
            step = -(-len(values) // 7)
            values, labels = values[::step], labels[::step]
        lo, hi = n.limits
        keep = [
            i
            for i, v in enumerate(values)
            if min(lo, hi) - 1e-9 * abs(hi - lo) <= v <= max(lo, hi) + 1e-9 * abs(hi - lo)
        ]
        return Ticks([values[i] for i in keep], [labels[i] for i in keep])

    def strip_lut(self) -> bytes:
        cmap: Colormap = self.mappable.cmap
        n = self.norm()
        if not isinstance(n, BoundaryNorm):
            return cmap.lut(self.mappable.alpha)
        bins = len(n.boundaries) - 1
        out = bytearray()
        for i in range(256):
            r, g, b, _ = cmap((min(int(i / 256 * bins), bins - 1) + 0.5) / bins)
            out += bytes((r, g, b, round(self.mappable.alpha * 255)))
        return bytes(out)


def _piecewise(bounds: tuple[float, ...], v: float) -> float:
    n = len(bounds) - 1
    for i in range(n):
        if v <= bounds[i + 1] or i == n - 1:
            return (i + (v - bounds[i]) / ((bounds[i + 1] - bounds[i]) or 1.0)) / n
    return 1.0


def measure_colorbar(canvas: Canvas, cb: ColorbarSpec) -> float:
    side: Side = "right" if cb.orientation == "vertical" else "bottom"
    cb.band = measure_band(canvas, AxisBand(side, cb.located(canvas.theme.unicode_minus), cb.label))
    return CBAR_GAP + CBAR_WIDTH + cb.band.thickness


def draw_colorbar(
    canvas: Canvas, cb: ColorbarSpec, plot: tuple[float, float, float, float], outset: float
) -> None:
    assert cb.band is not None
    x, y, w, h = plot
    vertical = cb.orientation == "vertical"
    shrink = min(1.0, max(0.05, cb.shrink))
    ramp = [i / 255 for i in range(256)]
    if vertical:
        sh = h * shrink
        rect = (x + w + outset + CBAR_GAP, y + (h - sh) / 2, CBAR_WIDTH, sh)
        canvas.colormapped_image(ramp, 1, 256, cb.strip_lut(), 0.0, 1.0, *rect, origin_upper=False)
    else:
        sw = w * shrink
        rect = (x + (w - sw) / 2, y + h + outset + CBAR_GAP, sw, CBAR_WIDTH)
        canvas.colormapped_image(ramp, 256, 1, cb.strip_lut(), 0.0, 1.0, *rect)
    rx, ry, rw, rh = rect
    canvas.rects([rx], [ry], [rx + rw], [ry + rh], stroke=canvas.theme.spine_color, width=0.8)
    pos = cb.positions(cb.band.ticks.values)
    majors = [ry + rh * (1 - p) for p in pos] if vertical else [rx + rw * p for p in pos]
    draw_band(canvas, cb.band, rect, majors, [])


# -- the axes frame --------------------------------------------------------------


@dataclass
class Plan:
    """An axes measured for layout."""

    xr: Range
    yr: Range
    bottom: AxisBand
    left: AxisBand
    margins: Margins
    title_h: float = 0.0
    twins: list[tuple[Axes, AxisBand, Range]] = field(default_factory=list)
    cbar_outset: float = 0.0


def _fit(canvas: Canvas, axis: Axis, r: Range, length: float, horizontal: bool) -> Ticks:
    """Ticks for an axis ``length`` points long, using fewer ticks when the
    labels would crowd each other."""
    minus, size = canvas.theme.unicode_minus, canvas.theme.tick_label_size
    if axis.ticks is not None or isinstance(axis.scale, _scales.Categorical):
        return axis.locate(*r, minus=minus)
    ticks = axis.locate(*r, minus=minus)
    for n in range(axis.max_ticks - 1, 2, -1):
        if len(ticks.values) < 3:
            break
        spacing = length / (len(ticks.values) - 1)
        if horizontal:
            need = max(canvas.measure(s, size).width for s in ticks.labels) + size * 0.6
        else:
            need = canvas.measure("0", size).height * 1.6
        if need <= spacing:
            break
        saved, axis.max_ticks = axis.max_ticks, n
        try:
            ticks = axis.locate(*r, minus=minus)
        finally:
            axis.max_ticks = saved
    return ticks


def _x_rotation(canvas: Canvas, ax: Axes, ticks: Ticks, width_hint: float) -> float:
    rot = ax._xtickrotation
    if rot != "auto":
        return float(rot)
    if len(ticks.values) < 2:
        return 0.0
    widest = max(canvas.measure(s, canvas.theme.tick_label_size).width for s in ticks.labels)
    spacing = width_hint / (len(ticks.values) - 1)
    if widest <= spacing * 0.92:
        return 0.0
    return 45.0 if spacing >= 8.0 else 90.0


def measure(
    ax: Axes,
    canvas: Canvas,
    xr: Range,
    yr: Range,
    width_hint: float = 200.0,
    height_hint: float = 160.0,
) -> Plan:
    th = canvas.theme
    minus = th.unicode_minus
    frame = ax._frame_on
    xticks = _fit(canvas, ax.xaxis, xr, width_hint, True)
    yticks = _fit(canvas, ax.yaxis, yr, height_hint, False)
    rot = _x_rotation(canvas, ax, xticks, width_hint) if frame else 0.0
    bottom = measure_band(canvas, AxisBand("bottom", xticks, ax.xaxis.label, rot), frame)
    left = measure_band(canvas, AxisBand("left", yticks, ax.yaxis.label), frame)
    m = Margins(left=left.thickness, bottom=bottom.thickness)

    # Tick labels centered on the outermost ticks hang past the plot's ends.
    if frame and xticks.values and rot == 0:
        a, b = ax.xaxis.scale.transform(xr[0]), ax.xaxis.scale.transform(xr[1])
        size = th.tick_label_size
        for i, attr in ((0, "left"), (-1, "right")):
            f = (ax.xaxis.scale.transform(xticks.values[i]) - a) / ((b - a) or 1.0)
            dist = (f if (attr == "left") == (b > a) else 1 - f) * width_hint
            hang = canvas.measure(xticks.labels[i], size).width / 2 - dist
            setattr(m, attr, max(getattr(m, attr), hang))

    plan = Plan(xr, yr, bottom, left, m)
    if frame and yticks.offset:
        m.top += OFFSET_GAP + canvas.measure(yticks.offset, th.tick_label_size).height
    for twin, which in ax._twins:
        txr, tyr = twin._data_view()
        if which == "x":  # twinx: shares x, own y axis on the right
            band = measure_band(
                canvas, AxisBand("right", twin.yaxis.locate(*tyr, minus=minus), twin.yaxis.label)
            )
            m.right += band.thickness
            plan.twins.append((twin, band, tyr))
        else:
            band = measure_band(
                canvas, AxisBand("top", twin.xaxis.locate(*txr, minus=minus), twin.xaxis.label)
            )
            m.top += band.thickness
            plan.twins.append((twin, band, txr))
    if ax._colorbar is not None:
        cb_thick = measure_colorbar(canvas, ax._colorbar)
        if ax._colorbar.orientation == "vertical":
            plan.cbar_outset = m.right
            m.right += cb_thick
        else:
            plan.cbar_outset = m.bottom
            m.bottom += cb_thick
    if ax.title:
        plan.title_h = canvas.measure(ax.title, th.title_size, th.title_weight).height + TITLE_GAP
        m.top += plan.title_h
    return plan


def transform(
    scale_x, scale_y, xr: Range, yr: Range, rect: tuple[float, float, float, float]
) -> _core.Transform:
    x, y, w, h = rect
    tx0, tx1 = scale_x.transform(xr[0]), scale_x.transform(xr[1])
    ty0, ty1 = scale_y.transform(yr[0]), scale_y.transform(yr[1])
    ax_ = w / ((tx1 - tx0) or 1.0)
    ay_ = -h / ((ty1 - ty0) or 1.0)
    return _core.Transform(ax_, x - tx0 * ax_, ay_, y + h - ty0 * ay_, scale_x.code, scale_y.code)


def _equal_aspect(
    ax: Axes, xr: Range, yr: Range, rect: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    x, y, w, h = rect
    sx = abs(ax.xaxis.scale.transform(xr[1]) - ax.xaxis.scale.transform(xr[0])) or 1.0
    sy = abs(ax.yaxis.scale.transform(yr[1]) - ax.yaxis.scale.transform(yr[0])) or 1.0
    u = min(w / sx, h / sy)
    nw, nh = u * sx, u * sy
    return x + (w - nw) / 2, y + (h - nh) / 2, nw, nh


def draw(ax: Axes, canvas: Canvas, plan: Plan, rect: tuple[float, float, float, float]) -> View:
    th = canvas.theme
    if ax._aspect == "equal":
        rect = _equal_aspect(ax, plan.xr, plan.yr, rect)
    x, y, w, h = rect
    tf = transform(ax.xaxis.scale, ax.yaxis.scale, plan.xr, plan.yr, rect)
    view = View(tf, x, y, w, h, plan.xr, plan.yr)
    xt, yt = plan.bottom.ticks, plan.left.ticks
    xs = [tf.x(v) for v in xt.values]
    ys = [tf.y(v) for v in yt.values]
    xm = [tf.x(v) for v in xt.minor]
    ym = [tf.y(v) for v in yt.minor]

    if th.axes_facecolor is not None and not ax._is_twin:
        canvas.rects([x], [y], [x + w], [y + h], fill=th.axes_facecolor)
    grid = th.grid if ax._grid is None else ax._grid
    if grid and ax._frame_on:
        if xs:
            canvas.segments(
                xs, [y] * len(xs), xs, [y + h] * len(xs), color=th.grid_color, width=th.grid_width
            )
        if ys:
            canvas.segments(
                [x] * len(ys), ys, [x + w] * len(ys), ys, color=th.grid_color, width=th.grid_width
            )

    draw_artists(canvas, ax._artists, view)
    for twin, band, r in plan.twins:
        if band.side == "right":
            twin_tf = transform(ax.xaxis.scale, twin.yaxis.scale, plan.xr, r, rect)
            twin_view = View(twin_tf, x, y, w, h, plan.xr, r)
        else:
            twin_tf = transform(twin.xaxis.scale, ax.yaxis.scale, r, plan.yr, rect)
            twin_view = View(twin_tf, x, y, w, h, r, plan.yr)
        draw_artists(canvas, twin._artists, twin_view)
        twin._last_view = twin_view

    if ax._frame_on:
        spines = set(th.spines) | {band.side for _, band, _ in plan.twins}
        _draw_spines(canvas, spines, rect)
        draw_band(canvas, plan.bottom, rect, xs, xm)
        draw_band(canvas, plan.left, rect, ys, ym)
    else:
        draw_band(canvas, plan.bottom, rect, [], [], show_ticks=False)
        draw_band(canvas, plan.left, rect, [], [], show_ticks=False)
    top_outset = (
        canvas.measure(yt.offset, th.tick_label_size).height + OFFSET_GAP
        if yt.offset and ax._frame_on
        else 0.0
    )
    right_outset = 0.0
    for twin, band, _ in plan.twins:
        tv = twin._last_view
        assert tv is not None
        if band.side == "right":
            pos = [tv.tf.y(v) for v in band.ticks.values]
            draw_band(canvas, band, rect, pos, [tv.tf.y(v) for v in band.ticks.minor], right_outset)
            right_outset += band.thickness
        else:
            pos = [tv.tf.x(v) for v in band.ticks.values]
            draw_band(canvas, band, rect, pos, [tv.tf.x(v) for v in band.ticks.minor], top_outset)
            top_outset += band.thickness
    if ax._colorbar is not None:
        draw_colorbar(canvas, ax._colorbar, rect, plan.cbar_outset)
    if ax.title:
        e = canvas.measure(ax.title, th.title_size, th.title_weight)
        loc = ax._title_loc
        tx = {"left": x, "center": x + w / 2, "right": x + w}[loc]
        canvas.text(
            tx,
            y - top_outset - TITLE_GAP - e.depth,
            ax.title,
            th.title_size,
            weight=th.title_weight,
            ha=loc,
        )  # type: ignore[arg-type]
    if ax._legend is not None:
        everything = ax._artists + [a for t, _ in ax._twins for a in t._artists]
        items = _legend.entries(everything)
        if items:
            box = _legend.measure(canvas, items, ax._legend)
            _legend.draw(canvas, box, *_legend.place(box, ax._legend.loc, view, ax._artists))
    for inset, bounds in ax._insets:
        bx, by, bw, bh = bounds
        inset_rect = (x + bx * w, y + (1 - by - bh) * h, bw * w, bh * h)
        ixr, iyr = inset._data_view()
        ix, iy, iw, ih = inset_rect
        canvas.rects([ix], [iy], [ix + iw], [iy + ih], fill=th.background)
        draw(inset, canvas, measure(inset, canvas, ixr, iyr, iw, ih), inset_rect)
    ax._last_view = view
    return view


def draw_artists(canvas: Canvas, artists: list, view: View) -> None:
    ordered = sorted(artists, key=lambda a: a.zorder)
    clipped = [a for a in ordered if a.clip]
    if clipped:
        with canvas.group(clip=(view.x, view.y, view.w, view.h)):
            for a in clipped:
                a.draw(canvas, view)
    for a in ordered:
        if not a.clip:
            a.draw(canvas, view)


def _draw_spines(canvas: Canvas, spines: set[str], rect: tuple[float, float, float, float]) -> None:
    th = canvas.theme
    x, y, w, h = rect
    half = th.spine_width / 2
    # Run each spine half a stroke past any corner it shares with another, so
    # the corner is closed.
    ext = {s: half if s in spines else 0.0 for s in ("left", "right", "top", "bottom")}
    lines = {
        "left": (x, y - ext["top"], x, y + h + ext["bottom"]),
        "right": (x + w, y - ext["top"], x + w, y + h + ext["bottom"]),
        "top": (x - ext["left"], y, x + w + ext["right"], y),
        "bottom": (x - ext["left"], y + h, x + w + ext["right"], y + h),
    }
    chosen = [lines[s] for s in ("left", "right", "top", "bottom") if s in spines]
    if chosen:
        x0, y0, x1, y1 = (list(c) for c in zip(*chosen, strict=True))
        canvas.segments(
            x0,
            y0,
            x1,
            y1,
            color=th.spine_color,
            width=th.spine_width,
        )


__all__ = ["Axis", "ColorbarSpec", "Margins", "Plan", "draw", "measure"]
