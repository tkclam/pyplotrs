"""The drawing surface: a Rust scene plus text layout on top of it.

Device coordinates are points with y pointing down. Every label goes through
`Canvas.measure` before it is drawn, so measurements are cached per canvas.
"""

from __future__ import annotations

import math
import re
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal, NamedTuple

from . import _core
from .colors import RGBA
from .text import Label, Span, flatten
from .theme import Theme

HAlign = Literal["left", "center", "right"]
VAlign = Literal["baseline", "top", "center", "bottom"]

Affine = tuple[float, float, float, float, float, float]
IDENTITY: Affine = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

DASHES: dict[str, list[float] | None] = {
    "solid": None,
    "-": None,
    "dashed": [4.0, 3.0],
    "--": [4.0, 3.0],
    "dotted": [1.0, 2.5],
    ":": [1.0, 2.5],
    "dashdot": [5.0, 2.0, 1.0, 2.0],
    "-.": [5.0, 2.0, 1.0, 2.0],
}
NO_LINE = ("none", "None", "", " ")


def dash(linestyle: str) -> list[float] | None:
    """The dash pattern for a line style name."""
    try:
        return DASHES[linestyle]
    except KeyError:
        names = ", ".join(repr(k) for k in DASHES)
        raise ValueError(
            f"unknown linestyle {linestyle!r}; expected one of {names} or 'none'"
        ) from None


def check_linestyle(linestyle: str) -> str:
    if linestyle not in NO_LINE:
        dash(linestyle)
    return linestyle


MARKERS = ("o", "s", "^", "v", "D", "+", "x", "|", "_")


def check_marker(marker: str | None) -> str | None:
    if marker is not None and marker not in MARKERS:
        raise ValueError(f"unknown marker {marker!r}; expected one of {', '.join(MARKERS)}")
    return marker


class MathTextWarning(UserWarning):
    """A label uses a TeX command pyplotrs does not implement, or a character
    no available font can draw. The label still renders, but not as intended."""


_warned: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key not in _warned:
        _warned.add(key)
        warnings.warn(message, MathTextWarning, stacklevel=5)


class Extent(NamedTuple):
    width: float
    ascent: float
    depth: float

    @property
    def height(self) -> float:
        return self.ascent + self.depth


@dataclass(frozen=True, slots=True)
class _Run:
    text: str
    size: float
    bold: bool
    italic: bool
    color: RGBA | None
    bgcolor: RGBA | None
    underline: bool
    strike: bool


_MATH_COLOR = re.compile(r"\\(textcolor|colorbox)\{([^{}]*)\}")
_PAD_X, _PAD_Y = 0.18, 0.10  # highlight panel padding, as a fraction of size


class Canvas:
    """A figure being drawn."""

    def __init__(self, width: float, height: float, theme: Theme) -> None:
        self.width, self.height, self.theme = width, height, theme
        self.scene = _core.Scene(width, height, list(theme.font_family), theme.math_fontset)
        self._extents: dict[tuple, Extent] = {}
        self._metrics: dict[tuple, tuple[float, ...]] = {}
        s = self.scene
        self.path, self.segments, self.rects = s.path, s.segments, s.rects
        self.colored_line = s.colored_line
        self.polygons, self.band, self.markers = s.polygons, s.band, s.markers
        self.image, self.colormapped_image = s.image, s.colormapped_image

    # -- text --------------------------------------------------------------

    def font_metrics(
        self, size: float, bold: bool = False, italic: bool = False
    ) -> tuple[float, ...]:
        """``(ascent, descent, underline_offset, underline_width, strike_offset, strike_width)``."""
        key = (size, bold, italic)
        if key not in self._metrics:
            self._metrics[key] = self.scene.font_metrics(size, bold=bold, italic=italic)
        return self._metrics[key]

    def line_height(self, size: float) -> tuple[float, float]:
        """The body font's ``(ascent, descent)`` at ``size``."""
        a, d, *_ = self.font_metrics(size)
        return a, d

    def _math_colors(self, s: str) -> str:
        if "\\textcolor" not in s and "\\colorbox" not in s:
            return s

        def sub(m: re.Match) -> str:
            try:
                r, g, b, a = self.theme.color(m.group(2))
            except (ValueError, TypeError):
                return m.group(0)
            return f"\\{m.group(1)}{{#{r:02x}{g:02x}{b:02x}{a:02x}}}"

        return _MATH_COLOR.sub(sub, s)

    def _measure_plain(self, s: str, size: float, bold: bool, italic: bool) -> Extent:
        key = (s, size, bold, italic)
        hit = self._extents.get(key)
        if hit is not None:
            return hit
        if "$" in s and "\\" in s:
            for name in self.scene.unknown_commands(s, size):
                _warn_once(name, f"unknown TeX command \\{name} in {s!r} is drawn as plain letters")
        if not s.isascii():
            for ch in self.scene.missing_glyphs(s):
                _warn_once(
                    f"glyph:{ch}",
                    f"no font can draw {ch!r} (U+{ord(ch):04X}) in {s!r}; "
                    "it is drawn as a box. Add a font that covers it to the theme's font_family.",
                )
        ext = Extent(*self.scene.measure(s, size, bold=bold, italic=italic))
        self._extents[key] = ext
        return ext

    def _runs(self, s: Span, size: float, bold: bool, italic: bool) -> list[_Run]:
        runs = []
        for text, st in flatten(s):
            run_size = float(st["size"]) if "size" in st else size * float(st.get("scale", 1.0))
            runs.append(
                _Run(
                    self._math_colors(text),
                    run_size,
                    bold if "weight" not in st else st["weight"] == "bold",
                    italic if "style" not in st else st["style"] == "italic",
                    None if st.get("color") is None else self.theme.color(st["color"]),
                    None if st.get("bgcolor") is None else self.theme.color(st["bgcolor"]),
                    bool(st.get("underline")),
                    bool(st.get("strike")),
                )
            )
        return runs

    def _layout(
        self, s: Span, size: float, bold: bool, italic: bool
    ) -> tuple[list[_Run], list[float], Extent]:
        runs = self._runs(s, size, bold, italic)
        widths, ascent, depth, pad = [], 0.0, 0.0, 0.0
        for r in runs:
            e = self._measure_plain(r.text, r.size, r.bold, r.italic)
            widths.append(e.width)
            ascent, depth = max(ascent, e.ascent), max(depth, e.depth)
            if r.bgcolor is not None:
                pad = max(pad, r.size * _PAD_Y)
        return runs, widths, Extent(sum(widths), ascent + pad, depth + pad)

    def measure(
        self, s: Label, size: float, weight: str = "normal", style: str = "normal"
    ) -> Extent:
        """``(width, ascent, depth)`` of a label in points."""
        bold, italic = weight == "bold", style == "italic"
        if isinstance(s, Span):
            return self._layout(s, size, bold, italic)[2]
        return self._measure_plain(self._math_colors(str(s)), size, bold, italic)

    def text(
        self,
        x: float,
        y: float,
        s: Label,
        size: float,
        color: RGBA | None = None,
        *,
        weight: str = "normal",
        style: str = "normal",
        ha: HAlign = "left",
        va: VAlign = "baseline",
        rotation: float = 0.0,
    ) -> Extent:
        """Draw a label anchored at ``(x, y)``; ``rotation`` is degrees
        counter-clockwise about the anchor. Returns its extent."""
        color = self.theme.text_color if color is None else color
        ext = self.measure(s, size, weight, style)
        dx = {"left": 0.0, "center": -ext.width / 2, "right": -ext.width}[ha]
        dy = {
            "baseline": 0.0,
            "top": ext.ascent,
            "center": (ext.ascent - ext.depth) / 2,
            "bottom": -ext.depth,
        }[va]
        if rotation:
            t = math.radians(rotation)
            c, s_ = math.cos(t), math.sin(t)
            with self.group((c, -s_, s_, c, x, y)):
                self._draw_label(dx, dy, s, size, color, weight, style)
        else:
            self._draw_label(x + dx, y + dy, s, size, color, weight, style)
        return ext

    def _draw_label(
        self, x: float, y: float, s: Label, size: float, color: RGBA, weight: str, style: str
    ) -> None:
        bold, italic = weight == "bold", style == "italic"
        if not isinstance(s, Span):
            self.scene.text(x, y, self._math_colors(str(s)), size, color, bold=bold, italic=italic)
            return
        runs, widths, ext = self._layout(s, size, bold, italic)
        # Panels first, then glyphs, then rules, so later runs never cover
        # earlier ones.
        cursor = x
        for r, w in zip(runs, widths, strict=True):
            if r.bgcolor is not None:
                px = r.size * _PAD_X
                self.rects(
                    [cursor - px],
                    [y - ext.ascent],
                    [cursor + w + px],
                    [y + ext.depth],
                    fill=r.bgcolor,
                )
            cursor += w
        cursor = x
        for r, w in zip(runs, widths, strict=True):
            self.scene.text(
                cursor, y, r.text, r.size, r.color or color, bold=r.bold, italic=r.italic
            )
            cursor += w
        cursor = x
        for r, w in zip(runs, widths, strict=True):
            if r.underline or r.strike:
                _, _, uo, uw, so, sw = self.font_metrics(r.size, r.bold, r.italic)
                for on, off, width in ((r.underline, uo, uw), (r.strike, so, sw)):
                    if on:
                        self.segments(
                            [cursor],
                            [y + off],
                            [cursor + w],
                            [y + off],
                            color=r.color or color,
                            width=width,
                        )
            cursor += w

    # -- groups and helpers --------------------------------------------------

    @contextmanager
    def group(
        self,
        transform: Affine = IDENTITY,
        *,
        clip: tuple[float, float, float, float] | None = None,
        clip_circle: tuple[float, float, float] | None = None,
        clip_path: tuple[list[float], list[float]] | None = None,
        opacity: float = 1.0,
    ) -> Iterator[None]:
        """Draw inside a transformed, clipped and/or translucent group."""
        self.scene.begin_group(
            transform, clip=clip, clip_circle=clip_circle, clip_path=clip_path, opacity=opacity
        )
        try:
            yield
        finally:
            self.scene.end_group()

    def arrow(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        color: RGBA,
        width: float,
        head_length: float = 8.0,
        head_width: float = 3.2,
    ) -> None:
        """A line from ``(x0, y0)`` to ``(x1, y1)`` with a filled head at the end."""
        length = math.hypot(x1 - x0, y1 - y0)
        if length == 0.0:
            return
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        if width > 0:
            head_length = min(head_length, length)
        bx, by = x1 - head_length * ux, y1 - head_length * uy
        if width > 0:
            self.path([x0, bx], [y0, by], stroke=color, width=width, cap="round")
        px, py = -uy * head_width, ux * head_width
        self.path([x1, bx + px, bx - px], [y1, by + py, by - py], fill=color, close=True)

    def hatch(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        pattern: str,
        color: RGBA,
        width: float = 0.6,
        spacing: float = 6.0,
        outline: tuple[list[float], list[float]] | None = None,
    ) -> None:
        """Fill a device rectangle (or the polygon ``outline`` inside it) with
        hatch lines: any of ``/ \\ | - + x``."""
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        a, b, c, d = [], [], [], []

        def seg(p: float, q: float, r: float, s: float) -> None:
            a.append(p)
            b.append(q)
            c.append(r)
            d.append(s)

        if "|" in pattern or "+" in pattern:
            for i in range(int((x1 - x0) / spacing) + 1):
                seg(x0 + i * spacing, y0, x0 + i * spacing, y1)
        if "-" in pattern or "+" in pattern:
            for i in range(int((y1 - y0) / spacing) + 1):
                seg(x0, y0 + i * spacing, x1, y0 + i * spacing)
        diag = spacing * math.sqrt(2.0)
        n = int((x1 - x0 + y1 - y0) / diag) + 1
        if "/" in pattern or "x" in pattern:
            for i in range(n):
                k = x0 + y0 + i * diag  # lines of constant x + y
                seg(k - y0, y0, k - y1, y1)
        if "\\" in pattern or "x" in pattern:
            for i in range(n):
                k = x0 - y1 + i * diag  # lines of constant x - y
                seg(k + y0, y0, k + y1, y1)
        if a:
            with self.group(clip=(x0, y0, x1 - x0, y1 - y0), clip_path=outline):
                self.segments(a, b, c, d, color=color, width=width)
