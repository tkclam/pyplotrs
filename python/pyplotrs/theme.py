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

# Print-safe categorical greys (distinguishable on white without colour); pair
# with distinct line styles / markers for fully grey-scale-robust figures.
_GREYS: tuple[RGBA, ...] = (
    (0, 0, 0, 255),
    (120, 120, 120, 255),
    (60, 60, 60, 255),
    (165, 165, 165, 255),
    (30, 30, 30, 255),
    (95, 95, 95, 255),
)


def parse_color(color, palette: tuple[RGBA, ...]) -> RGBA:
    """Resolve a colour spec to RGBA against ``palette``.

    ``"C0".."Cn"`` index ``palette`` (cycling); a 3- or 4-tuple is taken as
    literal RGB/RGBA. This is the one place colour strings are interpreted, so
    ``"C3"`` means *this theme's* fourth colour, not a fixed global one.
    """
    if isinstance(color, str):
        if len(color) >= 2 and color[0] == "C" and color[1:].isdigit():
            return palette[int(color[1:]) % len(palette)]
        raise ValueError(f"unknown color string {color!r}")
    if len(color) == 3:
        r, g, b = color
        return (int(r), int(g), int(b), 255)
    r, g, b, a = color
    return (int(r), int(g), int(b), int(a))


@dataclass(frozen=True)
class Theme:
    """An immutable set of style choices. Use :meth:`with_` to derive variants."""

    palette: tuple[RGBA, ...] = _OKABE_ITO
    text_color: RGBA = (0, 0, 0, 255)
    spine_color: RGBA = (89, 89, 89, 255)
    # Which of "left"/"right"/"top"/"bottom" spines (and their ticks) to draw.
    spines: tuple[str, ...] = ("left", "bottom")
    spine_width: float = 1.0

    tick_label_size: float = 9.0
    axis_label_size: float = 10.0
    title_size: float = 11.0
    suptitle_size: float = 13.0
    legend_size: float = 9.0

    line_width: float = 1.5  # default width of a `line` mark

    grid: bool = False
    grid_color: RGBA = (221, 221, 221, 255)
    grid_width: float = 0.6

    axes_facecolor: RGBA | None = None  # plot-area background fill
    legend_facecolor: RGBA = (255, 255, 255, 255)
    legend_edgecolor: RGBA = (179, 179, 179, 255)

    def resolve(self, color) -> RGBA:
        """Resolve a colour spec against this theme's palette (see
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

#: Print-safe grey-scale preset: monochrome palette, black spines/text.
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
