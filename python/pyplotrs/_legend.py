"""Legends: one key per labeled artist."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ._canvas import NO_LINE, Canvas, dash
from .artists import Artist, Key, View
from .text import Label

LOCATIONS = (
    "best",
    "upper right",
    "upper left",
    "lower left",
    "lower right",
    "upper center",
    "lower center",
    "center left",
    "center right",
    "center",
)

_KEY_W, _KEY_GAP, _COL_GAP, _PAD, _INSET = 22.0, 5.0, 12.0, 6.0, 6.0


@dataclass
class LegendSpec:
    loc: str = "best"
    ncols: int = 1
    title: Label | None = None
    frame: bool = True
    fontsize: float | None = None

    def __post_init__(self) -> None:
        if self.loc not in LOCATIONS:
            raise ValueError(
                f"unknown legend loc {self.loc!r}; expected one of {', '.join(LOCATIONS)}"
            )
        self.ncols = max(1, int(self.ncols))


Entry = tuple[Label, Key]


def entries(artists: list[Artist]) -> list[Entry]:
    out = []
    for a in artists:
        key = a.legend_key() if a.label else None
        if key is not None:
            out.append((a.label, key))
    return out


@dataclass
class Box:
    """A measured legend."""

    entries: list[Entry]
    spec: LegendSpec
    size: float
    row_h: float
    ascent: float
    col_widths: list[float]
    nrows: int
    title_h: float
    width: float
    height: float


def measure(canvas: Canvas, items: list[Entry], spec: LegendSpec) -> Box:
    size = spec.fontsize or canvas.theme.legend_size
    ascent, descent = canvas.line_height(size)
    row_h = ascent + descent
    ncols = min(spec.ncols, max(len(items), 1))
    nrows = math.ceil(len(items) / ncols)
    cols = [items[c * nrows : (c + 1) * nrows] for c in range(ncols)]
    widths = [
        _KEY_W + _KEY_GAP + max((canvas.measure(lbl, size).width for lbl, _ in col), default=0.0)
        for col in cols
    ]
    gap = row_h * 0.55
    width = 2 * _PAD + sum(widths) + _COL_GAP * (ncols - 1)
    height = 2 * _PAD + nrows * row_h + (nrows - 1) * gap
    title_h = 0.0
    if spec.title:
        title_h = row_h + gap
        height += title_h
        width = max(width, 2 * _PAD + canvas.measure(spec.title, size, "bold").width)
    return Box(items, spec, size, row_h, ascent, widths, nrows, title_h, width, height)


def draw_key(canvas: Canvas, key: Key, x0: float, x1: float, cy: float, size: float) -> None:
    cx = (x0 + x1) / 2
    if key.kind == "patch":
        h = size * 0.85
        canvas.rects(
            [x0 + 2],
            [cy - h / 2],
            [x1 - 2],
            [cy + h / 2],
            fill=key.color,
            stroke=key.edgecolor,
            width=0.8,
        )
        return
    if key.kind == "marker":
        canvas.markers(
            [cx],
            [cy],
            marker=key.marker or "o",
            size=key.markersize,
            fill=key.color,
            edge=key.edgecolor,
        )
        return
    if key.linestyle not in NO_LINE:
        canvas.path(
            [x0 + 1, x1 - 1],
            [cy, cy],
            stroke=key.color,
            width=key.linewidth,
            dash=dash(key.linestyle),
            cap="round",
        )
    if key.kind == "errorbar":
        canvas.segments([cx], [cy - 3.5], [cx], [cy + 3.5], color=key.color, width=key.linewidth)
    if key.marker:
        canvas.markers([cx], [cy], marker=key.marker, size=key.markersize, fill=key.color)


def draw(canvas: Canvas, box: Box, x: float, y: float) -> None:
    """Draw ``box`` with its top-left corner at ``(x, y)``."""
    theme = canvas.theme
    if box.spec.frame:
        canvas.rects(
            [x],
            [y],
            [x + box.width],
            [y + box.height],
            fill=theme.legend_facecolor,
            stroke=theme.legend_edgecolor,
            width=0.8,
        )
    top = y + _PAD
    if box.spec.title:
        canvas.text(x + _PAD, top + box.ascent, box.spec.title, box.size, weight="bold")
        top += box.title_h
    gap = box.row_h * 0.55
    left = x + _PAD
    for c, col_w in enumerate(box.col_widths):
        row_y = top
        for label, key in box.entries[c * box.nrows : (c + 1) * box.nrows]:
            draw_key(canvas, key, left, left + _KEY_W, row_y + box.row_h / 2, box.size)
            canvas.text(left + _KEY_W + _KEY_GAP, row_y + box.ascent, label, box.size)
            row_y += box.row_h + gap
        left += col_w + _COL_GAP


def place(box: Box, loc: str, view: View, artists: list[Artist]) -> tuple[float, float]:
    """The top-left corner for a legend inside the plot area."""
    left, right = view.x + _INSET, view.x + view.w - _INSET - box.width
    top, bottom = view.y + _INSET, view.y + view.h - _INSET - box.height
    hmid, vmid = view.x + (view.w - box.width) / 2, view.y + (view.h - box.height) / 2
    spots = {
        "upper right": (right, top),
        "upper left": (left, top),
        "lower left": (left, bottom),
        "lower right": (right, bottom),
        "upper center": (hmid, top),
        "lower center": (hmid, bottom),
        "center left": (left, vmid),
        "center right": (right, vmid),
        "center": (hmid, vmid),
    }
    if loc != "best":
        return spots[loc]
    # Device positions of a sample of every artist's data.
    pts = []
    for a in artists:
        xs, ys = a.footprint()
        for px, py in zip(xs, ys, strict=False):
            dx, dy = view.tf.x(px), view.tf.y(py)
            if math.isfinite(dx) and math.isfinite(dy):
                pts.append((dx, dy))

    def covered(spot: tuple[float, float]) -> int:
        x0, y0 = spot
        return sum(
            1 for px, py in pts if x0 <= px <= x0 + box.width and y0 <= py <= y0 + box.height
        )

    order = (
        "upper right",
        "upper left",
        "lower left",
        "lower right",
        "upper center",
        "lower center",
        "center left",
        "center right",
        "center",
    )
    return spots[min(order, key=lambda name: covered(spots[name]))]
