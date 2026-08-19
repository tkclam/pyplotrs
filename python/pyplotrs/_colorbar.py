"""Colorbar rendering.

Split out of `axes.py` for the reason `tests/test_module_layout.py` enforces:
the 2D mark surface is legitimately large, and everything that merely *hangs
off* an axes - the legend placement, this - does not belong inside it.

The two orientations are separate functions rather than one branchy one
because they share almost no geometry: a vertical bar reserves width and hangs
its label rotated off the right edge, a horizontal one reserves height and sets
its label flat underneath.
"""

from __future__ import annotations

from ._const import (
    _AXIS_LABEL_GAP,
    _CBAR_GAP,
    _CBAR_TICK_GAP,
    _CBAR_TICK_LEN,
    _CBAR_WIDTH,
)
from ._draw import _colorbar_ticks, _text, _tw

__all__ = ["draw"]


def draw(ax, scene, layout) -> None:
    t = ax._theme
    _TICK_LABEL_SIZE = t.tick_label_size
    _AXIS_LABEL_SIZE = t.axis_label_size
    _SPINE = t.spine_color
    _BLACK = t.text_color
    cb = ax._colorbar
    cmap = cb["cmap"]
    vmin, vmax = cb["vmin"], cb["vmax"]
    plot = layout.plot
    band = ax._cbar_band(layout.cbar)
    horizontal = cb.get("orientation", "vertical") == "horizontal"
    shrink = max(0.0, min(1.0, cb.get("shrink", 1.0)))

    if horizontal:
        _draw_horizontal(ax, scene, cb, plot, band, shrink)
        return

    # Strip aligned vertically with the plot area, `shrink`ed about its
    # center so a short bar stays opposite the middle of the data.
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

def _draw_horizontal(ax, scene, cb, plot, band, shrink: float) -> None:
    """The horizontal variant: strip under the plot, ticks below it, and an
    upright label under those (no rotation - it reads left-to-right here)."""
    t = ax._theme
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
