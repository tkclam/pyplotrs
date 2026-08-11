"""Scene-drawing primitives shared by every axes kind.

One level above the Rust Scene: math-aware text, markers, arrows, hatching,
dash patterns, colormap lookup tables, and the legend box. Everything here
takes a ``scene`` and emits into it; nothing here knows what an Axes is.
"""

from __future__ import annotations

import math

from . import _pyplotrs_core as _core
from . import mathtext as _mathtext
from . import scales as _scales
from . import theme as _theme
from . import ticker as _ticker
from ._const import (
    _DASH_PATTERNS,
    _HATCH_SPACING,
    _LEGEND_SWATCH_KINDS,
    _LUT_CACHE,
    _LUT_CACHE_MAX,
)
from ._util import _circle_pts, _with_alpha


def _font(weight: str = "normal", style: str = "normal") -> str:
    """The Rust face selector for a weight/slant pair.

    ``"normal"``/``"bold"`` and ``"normal"``/``"italic"`` compose into
    ``"body"``, ``"body-bold"``, ``"body-italic"``, ``"body-bolditalic"``.
    Unknown values fall back to normal rather than raising: a typo should not
    lose a whole figure at save time.
    """
    bold = str(weight).lower() in ("bold", "semibold", "heavy", "black")
    italic = str(style).lower() in ("italic", "oblique")
    if not bold and not italic:
        return "body"
    return "body-" + ("bold" if bold else "") + ("italic" if italic else "")


def _tw(scene, text, size, font: str = "body") -> float:
    """Math-aware text width (drop-in for ``scene.measure_text``)."""
    return _mathtext.measure(scene, text, size, font)[0]


def _th(scene, text, size, font: str = "body") -> tuple[float, float]:
    """Math-aware ``(ascent, depth)`` for a string at ``size``."""
    _w, a, d = _mathtext.measure(scene, text, size, font)
    return a, d


def _text(scene, x, baseline, text, size, color, font: str = "body") -> None:
    """Math-aware text draw (drop-in for ``scene.add_text``)."""
    _mathtext.draw(scene, x, baseline, text, size, color, font)


def _colorbar_ticks(cb: dict, max_ticks: int = 6) -> list[tuple[float, str]]:
    """Locate colorbar ticks, honoring the mappable's ``norm`` (linear -> nice
    numbers, ``LogNorm`` -> decades, etc.), plus any explicit ``ticks``/
    ``format`` the caller pinned."""
    manual = cb.get("ticks")
    fmt = cb.get("format")
    if manual is not None:
        values = [float(v) for v in manual]
    elif cb.get("norm") is not None:
        pairs = cb["norm"].colorbar_ticks(max_ticks)
        if fmt is None:
            return pairs
        values = [v for v, _ in pairs]
    else:
        pairs = _scales.nice_ticks(cb["vmin"], cb["vmax"], max_ticks)
        if fmt is None:
            return pairs
        values = [v for v, _ in pairs]
    if fmt is not None:
        f = _ticker.get(fmt)
        return [(v, f(v, i)) for i, v in enumerate(values)]
    return [(v, _scales._fmt_plain(v) if v == int(v) else _ticker.fix_minus(f"{v:g}"))
            for v in values]


def _colormap_lut(cmap, alpha: float = 1.0) -> bytes:
    """A 256-entry RGBA lookup table sampled from ``cmap`` (1024 bytes).

    ``cmap``'s 256-entry RGB table is already materialized (built once, in
    Rust, at [`Colormap`][pyplotrs.colormaps.Colormap] construction); this just
    alpha-scales it into RGBA, also in Rust, and caches the result - it used
    to run on *every* draw of every image and again for each colorbar
    gradient, so building it once and reusing it still matters.

    ``alpha`` scales every entry's alpha channel, which is how the colormapped
    marks (image / contourf) honor a mark-level ``alpha``: they have no single
    color to fold it into the way ``_AxesBase._mark_color`` does, so it
    rides the LUT instead and the Rust per-pixel loop needs no new argument. It
    is part of the cache key, so a translucent image cannot poison the opaque
    table (or vice versa).
    """
    key = (cmap, alpha)
    hit = _LUT_CACHE.get(key)
    if hit is not None:
        return hit
    lut = _core.colormap_rgba_lut(cmap._table, alpha)
    if len(_LUT_CACHE) >= _LUT_CACHE_MAX:
        _LUT_CACHE.clear()
    _LUT_CACHE[key] = lut
    return lut


def _rgba_values(values, cmap, norm) -> list[tuple[int, int, int, int]]:
    """One RGBA per value, through ``norm`` then ``cmap``.

    Runs in Rust whenever the norm names a transform Rust knows
    ([`pyplotrs.norms.Normalize.code`][pyplotrs.norms.Normalize.code]), which covers linear and log - two
    Python calls per point otherwise, so 200k interpreter round-trips for a
    100k-point scatter. ``TwoSlopeNorm`` and ``BoundaryNorm`` are piecewise and
    have no such transform, so they keep the per-value Python path.
    """
    code = getattr(norm, "code", None)
    if code is not None:
        return _core.map_colors(values, _colormap_lut(cmap), norm.vmin, norm.vmax, code)
    return [cmap(norm(v)) for v in values]


def _dash_for(style) -> list[float] | None:
    """The dash pattern for ``style``, or ``None`` for a solid stroke.

    An unknown name used to fall through this ``.get`` default and draw a solid
    line, so ``linestyle="dashdotted"`` - a real matplotlib spelling - drew the
    wrong thing and said nothing. Since solid and "no pattern" share the same
    ``None``, the lookup could not distinguish "solid" from "never heard of
    it"; the membership test can.
    """
    if style not in _DASH_PATTERNS:
        known = sorted(repr(k) for k in _DASH_PATTERNS if k is not None)
        raise ValueError(
            f"unknown linestyle {style!r}; expected one of {', '.join(known)}"
        )
    return _DASH_PATTERNS[style]


def _draws_line(style) -> bool:
    return style not in ("none", None)


def _draw_hatch(scene, dev: list[tuple[float, float]], pattern: str, color,
                lw: float = 0.6) -> None:
    """Fill the device-space bounding box of ``dev`` with a line hatch. Exact for
    axis-aligned rectangles; a bbox approximation for other shapes."""
    xs = [x for x, _ in dev]
    ys = [y for _, y in dev]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 <= x0 or y1 <= y0:
        return
    sp = _HATCH_SPACING
    diag = sp * math.sqrt(2.0)
    scene.begin_group(1.0, 0.0, 0.0, 1.0, 0.0, 0.0, clip=(x0, y0, x1 - x0, y1 - y0))

    def line(a, b):
        scene.add_path([a, b], stroke_color=color, stroke_width=lw)

    if "|" in pattern or "+" in pattern:
        x = x0
        while x <= x1:
            line((x, y0), (x, y1)); x += sp
    if "-" in pattern or "+" in pattern:
        y = y0
        while y <= y1:
            line((x0, y), (x1, y)); y += sp
    if "/" in pattern or "x" in pattern:  # constant x+y
        c = x0 + y0
        while c <= x1 + y1:
            line((c - y0, y0), (c - y1, y1)); c += diag
    if "\\" in pattern or "x" in pattern:  # constant x-y
        c = x0 - y1
        while c <= x1 - y0:
            line((c + y0, y0), (c + y1, y1)); c += diag
    scene.end_group()


#: Every marker `_draw_marker` knows how to draw. Kept beside it rather than in
#: `_const` so that adding a branch below without adding it here is an obvious
#: omission rather than an edit in another file.
_MARKER_SHAPES = frozenset({"o", "s", "^", "v", "D", "+", "x"})


def _check_marker(shape) -> None:
    """Reject an unknown marker name at the *call*, not at `save`.

    `_draw_marker` guards itself too, but `scatter` never reaches it: markers
    are instanced in Rust (one stamp plus a placement per point), so an unknown
    name silently became a circle there. Validating where the argument arrives
    also means the traceback points at the caller's line rather than at a draw
    pass thousands of marks later.
    """
    if shape is None:
        return
    if shape not in _MARKER_SHAPES:
        raise ValueError(
            f"unknown marker {shape!r}; expected one of "
            f"{', '.join(repr(s) for s in sorted(_MARKER_SHAPES))}"
        )


def _draw_marker(scene, cx: float, cy: float, d: float, shape: str,
                 facecolor, edgecolor=None, edgewidth: float = 1.0) -> None:
    """Draw a single marker of diameter ``d`` centered at ``(cx, cy)``.

    Filled shapes: ``o`` circle, ``s`` square, ``^`` triangle-up,
    ``v`` triangle-down, ``D`` diamond. Stroke-only shapes: ``+`` plus,
    ``x`` cross.

    An unrecognized shape used to fall through to the circle branch, so
    ``marker="*"`` - which matplotlib draws as a star - silently drew a dot,
    and so did every typo. Rejecting it names the accepted set instead.
    """
    if shape not in _MARKER_SHAPES:
        raise ValueError(
            f"unknown marker {shape!r}; expected one of "
            f"{', '.join(repr(s) for s in sorted(_MARKER_SHAPES))}"
        )
    r = d / 2.0
    if shape in ("+", "x"):
        # A stroke-only marker needs ink even when the caller supplied neither
        # color. This read `_BLACK`, which only ever existed as a *local*
        # inside `Axes._draw`, so the branch raised `NameError`; nothing
        # reached it because `scatter` resolves a color first, but any other
        # caller would have. A module constant would just re-create the
        # shadowing trap, so the floor is spelled out here.
        col = edgecolor or facecolor or (0, 0, 0, 255)
        if shape == "+":
            segs = [[(cx - r, cy), (cx + r, cy)], [(cx, cy - r), (cx, cy + r)]]
        else:
            segs = [[(cx - r, cy - r), (cx + r, cy + r)], [(cx - r, cy + r), (cx + r, cy - r)]]
        for seg in segs:
            scene.add_path(seg, stroke_color=col, stroke_width=max(edgewidth, 1.0), cap="round")
        return

    if shape == "s":
        pts = [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
    elif shape == "^":
        s = r * 0.95
        pts = [(cx, cy - r), (cx + s, cy + r * 0.8), (cx - s, cy + r * 0.8)]
    elif shape == "v":
        s = r * 0.95
        pts = [(cx, cy + r), (cx - s, cy - r * 0.8), (cx + s, cy - r * 0.8)]
    elif shape == "D":
        pts = [(cx, cy - r), (cx + r * 0.8, cy), (cx, cy + r), (cx - r * 0.8, cy)]
    else:  # "o" and any unknown shape fall back to a circle
        pts = _circle_pts(cx, cy, r)

    scene.add_path(
        pts,
        fill_color=facecolor,
        close=True,
        stroke_color=edgecolor,
        stroke_width=edgewidth if edgecolor else 1.0,
    )


def _place_text(scene, dx: float, dy: float, s: str, size: float, color,
                ha: str = "left", va: str = "baseline", font: str = "body",
                rotation: float = 0.0) -> None:
    """Draw ``s`` (math-aware) anchored at device ``(dx, dy)`` with the given
    horizontal/vertical alignment. Coordinates are y-down device points.
    ``font`` must match between measuring and drawing or the anchor drifts.

    ``rotation`` is degrees counter-clockwise about the anchor. It is applied
    as a group transform rather than anything text-specific: the IR already
    carries an affine per group and all three backends honor it, so rotated
    labels stay real selectable text in PDF and SVG instead of becoming paths.
    """
    tw = _tw(scene, s, size, font)
    a, d = _th(scene, s, size, font)
    ox = -tw / 2.0 if ha == "center" else (-tw if ha == "right" else 0.0)
    if va == "bottom":
        oy = -d
    elif va == "top":
        oy = a
    elif va == "center":
        oy = (a - d) / 2.0
    else:  # baseline
        oy = 0.0
    if not rotation:
        _text(scene, dx + ox, dy + oy, s, size, color, font)
        return
    # Rotate about the anchor: translate to it, rotate, then lay the text out
    # in the rotated frame. Device y runs downward, so a positive (visually
    # counter-clockwise) angle is a negative rotation in these coordinates.
    th = math.radians(-rotation)
    cos_t, sin_t = math.cos(th), math.sin(th)
    scene.begin_group(cos_t, sin_t, -sin_t, cos_t, dx, dy, None, 1.0)
    _text(scene, ox, oy, s, size, color, font)
    scene.end_group()


def _draw_arrow(scene, x0: float, y0: float, x1: float, y1: float, color,
                width: float, head_len: float = 8.0, head_w: float = 3.2) -> None:
    """Stroke a line from ``(x0, y0)`` to ``(x1, y1)`` with a filled triangular
    arrowhead at the second point."""
    ang = math.atan2(y1 - y0, x1 - x0)
    # Shorten the shaft so it meets the back of the head, not the tip.
    bx = x1 - head_len * math.cos(ang)
    by = y1 - head_len * math.sin(ang)
    scene.add_path([(x0, y0), (bx, by)], stroke_color=color, stroke_width=width, cap="round")
    px, py = -math.sin(ang), math.cos(ang)  # unit perpendicular
    scene.add_path(
        [(x1, y1), (bx + head_w * px, by + head_w * py), (bx - head_w * px, by - head_w * py)],
        fill_color=color, close=True,
    )


def _measure_legend(scene, entries, theme=None, opts=None):
    """Size a legend box for ``entries``. Returns ``(box_w, box_h, metrics)``
    where ``metrics`` is a dict reused by ``_draw_legend_box`` so the box is
    measured and drawn from one source of truth (lets the figure layout reserve
    exactly the column width the box will occupy).

    ``opts`` carries the per-legend overrides (``ncol``/``title``/``frameon``/
    ``fontsize``); the measurement has to know all of them, since each changes
    the box the layout must reserve room for.
    """
    t = _theme.get(theme)
    opts = opts or {}
    size = float(opts.get("fontsize") or t.legend_size)
    ncol = max(1, int(opts.get("ncol") or 1))
    title = opts.get("title")
    a, desc, _ = scene.font_vmetrics(size)
    row_h = a + desc
    row_gap = row_h * 0.55
    glyph_w = 22.0
    glyph_gap = 5.0
    col_gap = 12.0
    pad = 6.0
    # Columns are filled down-then-across, so the row count is the tallest
    # column and every column is sized to the widest label it actually holds.
    ncol = min(ncol, len(entries))
    nrow = -(-len(entries) // ncol)  # ceil
    col_ws = []
    for c in range(ncol):
        chunk = entries[c * nrow:(c + 1) * nrow]
        widest = max((_tw(scene, m["label"], size) for m in chunk), default=0.0)
        col_ws.append(glyph_w + glyph_gap + widest)
    box_w = pad * 2.0 + sum(col_ws) + col_gap * (ncol - 1)
    box_h = pad * 2.0 + nrow * row_h + (nrow - 1) * row_gap
    title_h = 0.0
    if title:
        title_h = row_h + row_gap
        box_h += title_h
        box_w = max(box_w, pad * 2.0 + _tw(scene, title, size))
    mt = {
        "size": size, "ascent": a, "row_h": row_h, "row_gap": row_gap,
        "glyph_w": glyph_w, "glyph_gap": glyph_gap, "pad": pad,
        "col_gap": col_gap, "col_ws": col_ws, "ncol": ncol, "nrow": nrow,
        "title": title, "title_h": title_h, "frameon": opts.get("frameon", True),
        "box_w": box_w, "box_h": box_h,
        "bg": t.legend_facecolor, "border": t.legend_edgecolor, "text_color": t.text_color,
    }
    return box_w, box_h, mt


def _draw_legend_box(scene, entries, bx: float, by: float, mt: dict) -> None:
    """Draw the legend frame, glyphs and labels with top-left corner ``(bx, by)``."""
    box_w, box_h, pad = mt["box_w"], mt["box_h"], mt["pad"]
    if mt.get("frameon", True):
        scene.add_path(
            [(bx, by), (bx + box_w, by), (bx + box_w, by + box_h), (bx, by + box_h)],
            fill_color=mt["bg"], close=True,
            stroke_color=mt["border"], stroke_width=0.8,
        )
    top = by + pad
    if mt.get("title"):
        _text(scene, bx + pad, top + mt["ascent"], mt["title"], mt["size"],
              mt["text_color"])
        top += mt["title_h"]
    nrow = mt.get("nrow") or len(entries)
    x = bx + pad
    for c, col_w in enumerate(mt.get("col_ws") or [box_w - 2 * pad]):
        y = top
        for m in entries[c * nrow:(c + 1) * nrow]:
            gx1 = x + mt["glyph_w"]
            _draw_legend_glyph(scene, m, x, gx1, y + mt["row_h"] / 2.0, mt["size"])
            _text(scene, gx1 + mt["glyph_gap"], y + mt["ascent"], m["label"],
                  mt["size"], mt["text_color"])
            y += mt["row_h"] + mt["row_gap"]
        x += col_w + mt["col_gap"]


def _draw_legend_glyph(scene, m: dict, x0: float, x1: float, cy: float,
                       size: float) -> None:
    """Draw one legend key. ``size`` is the theme's legend type size, so the
    swatch scales with the box the caller measured (they used to disagree: the
    box was measured at ``theme.legend_size`` and the swatch drawn at a fixed
    9 pt, which showed up under ``themes.presentation``)."""
    kind = m["kind"]
    color = m["color"]
    cx = (x0 + x1) / 2.0
    if kind in _LEGEND_SWATCH_KINDS:
        h = size * 0.85
        # Only the kinds that keep ``alpha`` beside an unfolded color need it
        # applied here; the rest already carry it inside their RGBA, and
        # ``image`` stores an ``alpha`` for its LUT that must not double-apply.
        fill = (_with_alpha(color, m["alpha"]) if kind in ("fill", "broken_barh")
                else color)
        scene.add_path(
            [(x0 + 2.0, cy - h / 2.0), (x1 - 2.0, cy - h / 2.0),
             (x1 - 2.0, cy + h / 2.0), (x0 + 2.0, cy + h / 2.0)],
            fill_color=fill, close=True,
        )
    elif kind == "scatter":
        _draw_marker(scene, cx, cy, m["markersize"], m["marker"],
                     facecolor=color, edgecolor=m["edgecolor"], edgewidth=m["edgewidth"])
    elif kind == "errorbar":
        if _draws_line(m["linestyle"]):
            scene.add_path([(x0 + 1.0, cy), (x1 - 1.0, cy)], stroke_color=color,
                           stroke_width=m["linewidth"], cap="round")
        scene.add_path([(cx, cy - 3.0), (cx, cy + 3.0)], stroke_color=color, stroke_width=m["linewidth"])
        if m["marker"]:
            _draw_marker(scene, cx, cy, m["markersize"], m["marker"], facecolor=color)
    else:  # line, and any future kind that carries a stroke
        # ``.get`` rather than ``[]``: an unknown kind should degrade to a plain
        # rule, never raise mid-render. ``barh`` used to land here and die on
        # the missing "linestyle" key.
        linestyle = m.get("linestyle", "solid")
        if _draws_line(linestyle):
            scene.add_path([(x0 + 1.0, cy), (x1 - 1.0, cy)], stroke_color=color,
                           stroke_width=m.get("linewidth", 1.5), cap="round",
                           dash=_dash_for(linestyle))
        if m.get("marker"):
            _draw_marker(scene, cx, cy, m.get("markersize", 5.0), m["marker"],
                         facecolor=color)
