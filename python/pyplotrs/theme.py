"""Themes: the single bundle of style choices a figure is drawn with.

A :class:`Theme` is an immutable dataclass holding the genuinely *style*-varying
knobs (palette, type scale, spine/grid/background, default line weights). There
is **no global "current theme"** - a theme is passed to :func:`pyplotrs.subplots`
(or :class:`pyplotrs.Figure`) and flows to its axes, matching the library's
no-global-state philosophy.

Built-in presets are module attributes, so ``pyplotrs.themes.nature`` etc. work::

    fig, ax = pyplotrs.subplots(theme=pyplotrs.themes.presentation)

Derive your own with :meth:`Theme.with_`::

    mine = pyplotrs.themes.default.with_(grid=True, line_width=2.0)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

RGBA = tuple[int, int, int, int]

# Okabe-Ito colorblind-safe categorical palette (C0-C7).
_OKABE_ITO: tuple[RGBA, ...] = (
    (0, 114, 178, 255),    # C0 blue
    (230, 159, 0, 255),    # C1 orange
    (0, 158, 115, 255),    # C2 green
    (204, 121, 167, 255),  # C3 pink
    (86, 180, 233, 255),   # C4 sky blue
    (213, 94, 0, 255),     # C5 vermillion
    (240, 228, 66, 255),   # C6 yellow
    (0, 0, 0, 255),        # C7 black
)

# Print-safe categorical grays (distinguishable on white without color); pair
# with distinct line styles / markers for fully grayscale-robust figures.
_GREYS: tuple[RGBA, ...] = (
    (0, 0, 0, 255),
    (120, 120, 120, 255),
    (60, 60, 60, 255),
    (165, 165, 165, 255),
    (30, 30, 30, 255),
    (95, 95, 95, 255),
)


#: The CSS Color Module Level 4 named colors, which are also matplotlib's
#: ``xkcd``-free named set. Kept as a plain dict so no table is built at import.
_CSS_COLORS: dict[str, tuple[int, int, int]] = {
    "aliceblue": (240, 248, 255), "antiquewhite": (250, 235, 215),
    "aqua": (0, 255, 255), "aquamarine": (127, 255, 212), "azure": (240, 255, 255),
    "beige": (245, 245, 220), "bisque": (255, 228, 196), "black": (0, 0, 0),
    "blanchedalmond": (255, 235, 205), "blue": (0, 0, 255),
    "blueviolet": (138, 43, 226), "brown": (165, 42, 42), "burlywood": (222, 184, 135),
    "cadetblue": (95, 158, 160), "chartreuse": (127, 255, 0),
    "chocolate": (210, 105, 30), "coral": (255, 127, 80),
    "cornflowerblue": (100, 149, 237), "cornsilk": (255, 248, 220),
    "crimson": (220, 20, 60), "cyan": (0, 255, 255), "darkblue": (0, 0, 139),
    "darkcyan": (0, 139, 139), "darkgoldenrod": (184, 134, 11),
    "darkgray": (169, 169, 169), "darkgreen": (0, 100, 0), "darkgrey": (169, 169, 169),
    "darkkhaki": (189, 183, 107), "darkmagenta": (139, 0, 139),
    "darkolivegreen": (85, 107, 47), "darkorange": (255, 140, 0),
    "darkorchid": (153, 50, 204), "darkred": (139, 0, 0),
    "darksalmon": (233, 150, 122), "darkseagreen": (143, 188, 143),
    "darkslateblue": (72, 61, 139), "darkslategray": (47, 79, 79),
    "darkslategrey": (47, 79, 79), "darkturquoise": (0, 206, 209),
    "darkviolet": (148, 0, 211), "deeppink": (255, 20, 147),
    "deepskyblue": (0, 191, 255), "dimgray": (105, 105, 105),
    "dimgrey": (105, 105, 105), "dodgerblue": (30, 144, 255),
    "firebrick": (178, 34, 34), "floralwhite": (255, 250, 240),
    "forestgreen": (34, 139, 34), "fuchsia": (255, 0, 255),
    "gainsboro": (220, 220, 220), "ghostwhite": (248, 248, 255),
    "gold": (255, 215, 0), "goldenrod": (218, 165, 32), "gray": (128, 128, 128),
    "green": (0, 128, 0), "greenyellow": (173, 255, 47), "grey": (128, 128, 128),
    "honeydew": (240, 255, 240), "hotpink": (255, 105, 180),
    "indianred": (205, 92, 92), "indigo": (75, 0, 130), "ivory": (255, 255, 240),
    "khaki": (240, 230, 140), "lavender": (230, 230, 250),
    "lavenderblush": (255, 240, 245), "lawngreen": (124, 252, 0),
    "lemonchiffon": (255, 250, 205), "lightblue": (173, 216, 230),
    "lightcoral": (240, 128, 128), "lightcyan": (224, 255, 255),
    "lightgoldenrodyellow": (250, 250, 210), "lightgray": (211, 211, 211),
    "lightgreen": (144, 238, 144), "lightgrey": (211, 211, 211),
    "lightpink": (255, 182, 193), "lightsalmon": (255, 160, 122),
    "lightseagreen": (32, 178, 170), "lightskyblue": (135, 206, 250),
    "lightslategray": (119, 136, 153), "lightslategrey": (119, 136, 153),
    "lightsteelblue": (176, 196, 222), "lightyellow": (255, 255, 224),
    "lime": (0, 255, 0), "limegreen": (50, 205, 50), "linen": (250, 240, 230),
    "magenta": (255, 0, 255), "maroon": (128, 0, 0),
    "mediumaquamarine": (102, 205, 170), "mediumblue": (0, 0, 205),
    "mediumorchid": (186, 85, 211), "mediumpurple": (147, 112, 219),
    "mediumseagreen": (60, 179, 113), "mediumslateblue": (123, 104, 238),
    "mediumspringgreen": (0, 250, 154), "mediumturquoise": (72, 209, 204),
    "mediumvioletred": (199, 21, 133), "midnightblue": (25, 25, 112),
    "mintcream": (245, 255, 250), "mistyrose": (255, 228, 225),
    "moccasin": (255, 228, 181), "navajowhite": (255, 222, 173),
    "navy": (0, 0, 128), "oldlace": (253, 245, 230), "olive": (128, 128, 0),
    "olivedrab": (107, 142, 35), "orange": (255, 165, 0),
    "orangered": (255, 69, 0), "orchid": (218, 112, 214),
    "palegoldenrod": (238, 232, 170), "palegreen": (152, 251, 152),
    "paleturquoise": (175, 238, 238), "palevioletred": (219, 112, 147),
    "papayawhip": (255, 239, 213), "peachpuff": (255, 218, 185),
    "peru": (205, 133, 63), "pink": (255, 192, 203), "plum": (221, 160, 221),
    "powderblue": (176, 224, 230), "purple": (128, 0, 128),
    "rebeccapurple": (102, 51, 153), "red": (255, 0, 0),
    "rosybrown": (188, 143, 143), "royalblue": (65, 105, 225),
    "saddlebrown": (139, 69, 19), "salmon": (250, 128, 114),
    "sandybrown": (244, 164, 96), "seagreen": (46, 139, 87),
    "seashell": (255, 245, 238), "sienna": (160, 82, 45), "silver": (192, 192, 192),
    "skyblue": (135, 206, 235), "slateblue": (106, 90, 205),
    "slategray": (112, 128, 144), "slategrey": (112, 128, 144),
    "snow": (255, 250, 250), "springgreen": (0, 255, 127),
    "steelblue": (70, 130, 180), "tan": (210, 180, 140), "teal": (0, 128, 128),
    "thistle": (216, 191, 216), "tomato": (255, 99, 71),
    "turquoise": (64, 224, 208), "violet": (238, 130, 238),
    "wheat": (245, 222, 179), "white": (255, 255, 255),
    "whitesmoke": (245, 245, 245), "yellow": (255, 255, 0),
    "yellowgreen": (154, 205, 50),
}


def _parse_hex(spec: str) -> RGBA | None:
    """Parse ``#rgb``/``#rgba``/``#rrggbb``/``#rrggbbaa``; ``None`` if not hex."""
    body = spec[1:]
    if len(body) in (3, 4):
        body = "".join(c * 2 for c in body)  # #f00 -> #ff0000
    if len(body) not in (6, 8):
        return None
    try:
        vals = [int(body[i:i + 2], 16) for i in range(0, len(body), 2)]
    except ValueError:
        return None
    r, g, b = vals[:3]
    return (r, g, b, vals[3] if len(vals) == 4 else 255)


def _channel(v) -> int:
    """One RGB channel to 0-255.

    Both conventions are accepted and told apart the way matplotlib's users
    expect: an *all-float* tuple in 0-1 is scaled, anything else is already in
    bytes. See :func:`parse_color` for why the distinction has to be made on the
    whole tuple rather than per channel.
    """
    return max(0, min(255, int(round(v))))


def _is_unit_float_tuple(values) -> bool:
    """True when every component is a ``float`` within 0-1 inclusive.

    Deciding per *tuple* rather than per *channel* is what makes the two
    conventions unambiguous: ``(1, 0, 0)`` is byte red (ints), ``(1.0, 0.0, 0.0)``
    is float red. Only a tuple that is entirely floats in range is scaled, so a
    mixed tuple like ``(255, 0.5, 0)`` is treated as bytes rather than guessed at.
    """
    return all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in values)


def parse_color(color, palette: tuple[RGBA, ...]) -> RGBA:
    """Resolve a color spec to RGBA against ``palette``.

    Accepts, in order:

    * ``"C0".."Cn"`` - index ``palette`` (cycling). This is the one place color
      strings are interpreted, so ``"C3"`` means *this theme's* fourth color,
      not a fixed global one.
    * ``"#rgb"``, ``"#rgba"``, ``"#rrggbb"``, ``"#rrggbbaa"`` hex.
    * A CSS color name (``"red"``, ``"steelblue"``), case-insensitive.
    * A 3- or 4-component tuple. **All-float tuples in 0-1 are treated as
      matplotlib-style fractions** and scaled to bytes; anything else is taken as
      literal 0-255 bytes. Alpha follows the same convention as its tuple.
    """
    if isinstance(color, str):
        if len(color) >= 2 and color[0] == "C" and color[1:].isdigit():
            return palette[int(color[1:]) % len(palette)]
        if color.startswith("#"):
            parsed = _parse_hex(color)
            if parsed is not None:
                return parsed
            raise ValueError(f"malformed hex color {color!r}")
        named = _CSS_COLORS.get(color.lower())
        if named is not None:
            return (*named, 255)
        raise ValueError(f"unknown color string {color!r}")

    values = tuple(color)
    if len(values) not in (3, 4):
        raise ValueError(f"color tuple must have 3 or 4 components, got {len(values)}")
    if _is_unit_float_tuple(values):
        scaled = [_channel(v * 255.0) for v in values]
        return (scaled[0], scaled[1], scaled[2], scaled[3] if len(scaled) == 4 else 255)
    r, g, b = (_channel(v) for v in values[:3])
    return (r, g, b, _channel(values[3]) if len(values) == 4 else 255)


@dataclass(frozen=True)
class Theme:
    """An immutable set of style choices. Use :meth:`with_` to derive variants."""

    palette: tuple[RGBA, ...] = _OKABE_ITO
    text_color: RGBA = (0, 0, 0, 255)
    spine_color: RGBA = (0, 0, 0, 255)
    # Which of "left"/"right"/"top"/"bottom" spines (and their ticks) to draw.
    spines: tuple[str, ...] = ("left", "bottom")
    spine_width: float = 1.0

    tick_label_size: float = 9.0
    axis_label_size: float = 10.0
    title_size: float = 11.0
    suptitle_size: float = 13.0
    legend_size: float = 9.0

    # Weight of the figure's chrome text: "normal" or "bold". Bold panel titles
    # are near-universal in multi-panel journal figures, and are a theme choice
    # rather than a per-call one - the same reason sizes live here. Free text
    # (`Axes.text`, `Axes.annotate`) takes weight/style arguments of its own.
    title_weight: str = "normal"
    suptitle_weight: str = "normal"
    axis_label_weight: str = "normal"

    line_width: float = 1.5  # default width of a `line` mark

    grid: bool = False
    grid_color: RGBA = (221, 221, 221, 255)
    grid_width: float = 0.6

    axes_facecolor: RGBA | None = None  # plot-area background fill
    legend_facecolor: RGBA = (255, 255, 255, 255)
    legend_edgecolor: RGBA = (179, 179, 179, 255)

    @property
    def separator_color(self) -> RGBA:
        """The hairline drawn between adjacent filled shapes - histogram bins,
        pie wedges.

        The intent is "the plot background showing through", so it follows
        :attr:`axes_facecolor` and falls back to white when that is ``None``
        (a transparent plot area over a white page). Hardcoding white here is
        what made histogram bins grow white outlines under a dark theme.
        """
        return self.axes_facecolor if self.axes_facecolor is not None else (255, 255, 255, 255)

    def resolve(self, color) -> RGBA:
        """Resolve a color spec against this theme's palette (see
        :func:`parse_color`)."""
        return parse_color(color, self.palette)

    def with_(self, **changes) -> "Theme":
        """A copy of this theme with ``changes`` applied."""
        return replace(self, **changes)


# -- built-in presets -------------------------------------------------------

#: The zero-config publication default (Okabe-Ito, despined, no grid).
default = Theme()

#: Compact journal preset: smaller type and thinner rules for dense, two-column
#: figures (e.g. ~3.3in wide).
nature = Theme(
    tick_label_size=8.0,
    axis_label_size=9.0,
    title_size=10.0,
    suptitle_size=11.0,
    legend_size=8.0,
    spine_width=0.8,
    line_width=1.2,
)

#: Print-safe grayscale preset: monochrome palette, black spines/text.
grayscale = Theme(
    palette=_GREYS,
    spine_color=(0, 0, 0, 255),
    line_width=1.3,
    legend_edgecolor=(120, 120, 120, 255),
)
bw = grayscale  # alias

#: Large type and heavy strokes with a light grid, tuned for slides/posters.
presentation = Theme(
    tick_label_size=12.0,
    axis_label_size=14.0,
    title_size=16.0,
    suptitle_size=19.0,
    legend_size=12.0,
    spine_width=1.4,
    line_width=2.5,
    grid=True,
    grid_color=(228, 228, 228, 255),
    grid_width=0.8,
)

#: All presets keyed by name (for `get(...)`).
_PRESETS = {
    "default": default,
    "nature": nature,
    "grayscale": grayscale,
    "bw": bw,
    "presentation": presentation,
}


def get(theme) -> Theme:
    """Coerce ``theme`` (a :class:`Theme`, a preset name, or ``None``) to a
    :class:`Theme`. ``None`` -> :data:`default`."""
    if theme is None:
        return default
    if isinstance(theme, Theme):
        return theme
    if isinstance(theme, str) and theme in _PRESETS:
        return _PRESETS[theme]
    raise ValueError(f"unknown theme {theme!r}; choose from {sorted(_PRESETS)}")
