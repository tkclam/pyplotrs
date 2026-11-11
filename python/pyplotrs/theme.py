"""Themes: every style default a figure is drawn with, in one immutable object.

Pass a theme to a figure, or set the default for new figures::

    fig, ax = pp.subplots(theme="dark")
    pp.set_theme(font_family=("Helvetica",), grid=True)

Derive variants with ``replace``::

    big = pp.themes.default.replace(tick_label_size=10, axis_label_size=11)
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Literal

from .colors import RGBA, ColorLike, to_rgba

__all__ = ["Theme", "dark", "default", "get_theme", "grayscale", "set_theme"]

# Okabe & Ito (2008): distinguishable under the common color-vision deficiencies.
_OKABE_ITO: tuple[RGBA, ...] = (
    (0, 0, 0, 255),
    (230, 159, 0, 255),
    (86, 180, 233, 255),
    (0, 158, 115, 255),
    (240, 228, 66, 255),
    (0, 114, 178, 255),
    (213, 94, 0, 255),
    (204, 121, 167, 255),
)

# The same hues re-aimed at a dark page: black becomes off-white and the blue
# is lifted to keep 4.5:1 contrast.
_OKABE_ITO_DARK: tuple[RGBA, ...] = (
    (235, 235, 235, 255),
    *_OKABE_ITO[1:5],
    (33, 130, 195, 255),
    *_OKABE_ITO[6:],
)

# Ordered by bisection, so any prefix is as spread out as possible.
_GRAYS: tuple[RGBA, ...] = (
    (0, 0, 0, 255),
    (120, 120, 120, 255),
    (60, 60, 60, 255),
    (165, 165, 165, 255),
    (30, 30, 30, 255),
    (95, 95, 95, 255),
)

Weight = Literal["normal", "bold"]


@dataclass(frozen=True)
class Theme:
    """Style defaults for a figure. Sizes are in points.

    The defaults are tuned for a single journal column (~3.5 in wide): compact
    type, thin rules, no grid, and only the left and bottom spines.
    """

    # Fonts. `font_family` is tried in order; the bundled Liberation Sans
    # (metric-compatible with Arial) is always the last resort. Whichever face
    # is used is embedded in saved files.
    font_family: tuple[str, ...] = ("Arial", "Helvetica", "Liberation Sans")
    math_fontset: Literal["sans", "stix"] = "sans"
    # Sign negative tick labels with U+2212 MINUS rather than a hyphen.
    unicode_minus: bool = True

    tick_label_size: float = 8.0
    axis_label_size: float = 9.0
    title_size: float = 10.0
    suptitle_size: float = 11.0
    legend_size: float = 8.0
    title_weight: Weight = "normal"
    suptitle_weight: Weight = "normal"
    axis_label_weight: Weight = "normal"

    palette: tuple[RGBA, ...] = _OKABE_ITO
    text_color: RGBA = (0, 0, 0, 255)
    spine_color: RGBA = (0, 0, 0, 255)
    spines: tuple[str, ...] = ("left", "bottom")
    spine_width: float = 0.8
    tick_length: float = 2.5
    tick_direction: Literal["out", "in"] = "out"

    line_width: float = 1.2
    marker_size: float = 5.0

    grid: bool = False
    grid_color: RGBA = (221, 221, 221, 255)
    grid_width: float = 0.6

    # `None` paints nothing: PDF/SVG stay transparent and PNG is white.
    figure_facecolor: RGBA | None = None
    axes_facecolor: RGBA | None = None
    legend_facecolor: RGBA = (255, 255, 255, 255)
    legend_edgecolor: RGBA = (179, 179, 179, 255)

    def __post_init__(self) -> None:
        if isinstance(self.font_family, str):
            object.__setattr__(self, "font_family", (self.font_family,))
        if self.math_fontset not in ("sans", "stix"):
            raise ValueError(f"math_fontset must be 'sans' or 'stix', got {self.math_fontset!r}")
        if self.tick_direction not in ("in", "out"):
            raise ValueError(f"tick_direction must be 'in' or 'out', got {self.tick_direction!r}")
        bad = set(self.spines) - {"left", "right", "top", "bottom"}
        if bad:
            raise ValueError(f"unknown spines {sorted(bad)}")
        # Accept any color spelling and store bytes.
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if f.name.endswith("color") and value is not None:
                object.__setattr__(self, f.name, to_rgba(value))
        object.__setattr__(self, "palette", tuple(to_rgba(c) for c in self.palette))

    def color(self, spec: ColorLike) -> RGBA:
        """Resolve a color, with ``"C0"``, ``"C1"``, ... taken from this theme's palette."""
        return to_rgba(spec, self.palette)

    def replace(self, **changes) -> Theme:
        """A copy of this theme with ``changes`` applied."""
        return dataclasses.replace(self, **changes)

    @property
    def background(self) -> RGBA:
        """What shows behind the plot: used for hairlines between filled shapes."""
        return self.axes_facecolor or self.figure_facecolor or (255, 255, 255, 255)

    def __repr__(self) -> str:
        for name, preset in PRESETS.items():
            if self == preset:
                return f"<Theme {name!r}>"
        return "<Theme (custom)>"


default = Theme()
grayscale = Theme(palette=_GRAYS)
dark = Theme(
    palette=_OKABE_ITO_DARK,
    text_color=(235, 235, 235, 255),
    spine_color=(235, 235, 235, 255),
    figure_facecolor=(18, 18, 18, 255),
    grid_color=(45, 45, 45, 255),
    legend_facecolor=(18, 18, 18, 255),
    legend_edgecolor=(73, 73, 73, 255),
)

PRESETS: dict[str, Theme] = {"default": default, "grayscale": grayscale, "dark": dark}

_current = default


def resolve(theme: Theme | str | None) -> Theme:
    """A theme from a ``Theme``, a preset name, or ``None`` (the current default)."""
    if theme is None:
        return _current
    if isinstance(theme, Theme):
        return theme
    try:
        return PRESETS[theme]
    except KeyError:
        raise ValueError(f"unknown theme {theme!r}; choose from {sorted(PRESETS)}") from None


def set_theme(theme: Theme | str | None = None, **changes) -> Theme:
    """Set the theme new figures use, optionally with changes. Returns it.

    ``set_theme()`` with no arguments restores the built-in default::

        pp.set_theme("dark")
        pp.set_theme(font_family=("Helvetica",), tick_direction="in")
    """
    global _current
    base = default if theme is None and not changes else resolve(theme)
    _current = base.replace(**changes) if changes else base
    return _current


def get_theme() -> Theme:
    """The theme new figures use."""
    return _current
