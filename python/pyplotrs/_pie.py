"""Pie geometry and drawing.

Its own module because a pie is not a cartesian mark: it has no axes to be
clipped to and no data-space extent, and the one hard part - fitting slice
labels around the rim - is a device-space packing problem that shares nothing
with the rest of `axes.py`. Keeping it there was what pushed that module past
the size `tests/test_module_layout.py` holds it to.
"""

from __future__ import annotations

import math

from ._const import _PIE_LABEL_R, _PIE_MIN_RADIUS, _PIE_WEDGE_STROKE
from ._draw import _text, _th, _tw

__all__ = ["geometry", "draw", "draw_labels"]


def geometry(ax, scene, m, proj):
    """Device center and radius for a pie, plus its placed slice labels.

    A slice label is a device length (its shaped width) hung off a data
    length (the rim), so no fixed data-space margin can hold it: it wastes
    the cell when the labels are short and clips them when they are long.
    The pie is fitted here instead, where the text can be measured against
    the rect it has to land in. Each label turns into linear bounds on the
    radius - the text box has to stay inside that rect on all four sides -
    and the tightest bound over every label wins. The labels are held to the
    axes' whole cell, not to the equal-aspect square the wedges live in, so
    a wide figure spends its horizontal slack on the labels and keeps the
    pie as large as the cell's height allows.

    Returns ``(cx, cy, r, placed)``, with ``placed`` a list of
    ``(x, baseline, text)`` ready to draw.
    """
    px, py, pw, ph = proj.cell
    cx, cy = proj.sx(0.0), proj.sy(0.0)
    # The wedge separators straddle the rim, so keep half of one inside
    # (and never let that inset drive a `radius=0` pie negative).
    r = max(0.0, abs(proj.sx(m["radius"]) - cx) - _PIE_WEDGE_STROKE / 2.0)
    size = ax._theme.tick_label_size

    # Measure once: (cos, sin, width, ascent, descent, text) per label.
    labs = []
    for wd in m["wedges"]:
        lab = wd.get("label")
        if not lab:
            continue
        am = (wd["a0"] + wd["a1"]) / 2.0
        asc, desc = _th(scene, lab, size)
        labs.append((math.cos(am), math.sin(am), _tw(scene, lab, size),
                     asc, desc, lab))

    fit = r
    for c, s, w, asc, desc, _lab in labs:
        h2 = (asc + desc) / 2.0
        # The label box, anchored at radius `_PIE_LABEL_R`, slides from
        # left-aligned on the right of the pie to right-aligned on the left
        # (centered straight up or down), so it leans away from the rim.
        # Each side of the box grows as `a*r + b`; only a side that grows
        # with r (a > 0) can bind.
        for a, b, avail in (
            (_PIE_LABEL_R * max(c, 0.0), w * (1.0 + c) / 2.0, px + pw - cx),
            (_PIE_LABEL_R * max(-c, 0.0), w * (1.0 - c) / 2.0, cx - px),
            (_PIE_LABEL_R * max(s, 0.0), h2, cy - py),
            (_PIE_LABEL_R * max(-s, 0.0), h2, py + ph - cy),
        ):
            if a > 0.0:
                fit = min(fit, (avail - b) / a)
    r = max(fit, r * _PIE_MIN_RADIUS)

    placed = []
    for c, s, w, asc, desc, lab in labs:
        lx = cx + _PIE_LABEL_R * r * c
        ly = cy - _PIE_LABEL_R * r * s
        placed.append((lx - w * (1.0 - c) / 2.0, ly + (asc - desc) / 2.0, lab))
    return cx, cy, r, placed

def draw(ax, scene, m, proj) -> None:
    cx, cy, r, _placed = geometry(ax, scene, m, proj)
    for wd in m["wedges"]:
        a0, a1 = wd["a0"], wd["a1"]
        n = max(2, int((a1 - a0) / (math.pi / 36)) + 1)
        pts = [(cx, cy)]
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
        scene.add_path(pts, fill_color=wd["color"], close=True,
                       stroke_color=ax._theme.separator_color,
                       stroke_width=_PIE_WEDGE_STROKE)

def draw_labels(ax, scene, m, proj) -> None:
    """Slice labels, drawn outside the data clip: the fit above keeps them
    in the rect, but a label too wide to fit at all (`_PIE_MIN_RADIUS`)
    should overhang whole rather than lose its last glyph to the clip."""
    _cx, _cy, _r, placed = geometry(ax, scene, m, proj)
    size = ax._theme.tick_label_size
    for x, baseline, lab in placed:
        _text(scene, x, baseline, lab, size, ax._theme.text_color)
