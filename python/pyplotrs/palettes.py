"""Built-in categorical/qualitative palettes: short lists of colors meant to
be *distinct*, unlike a [`pyplotrs.colormaps`][pyplotrs.colormaps] continuous map.

Curated from matplotlib (``tab10``/``tab20``/``tab20b``/``tab20c``, the
ColorBrewer qualitative sets ``Set1``-``Set3``/``Pastel1``-``Pastel2``/
``Dark2``/``Accent``/``Paired``, and ``okabe_ito``), colorcet's ``glasbey``
family (``cet_glasbey*`` - large, maximally-distinct sets for many
categories), and seaborn's named palettes (``sns_deep``/``sns_muted``/
``sns_bright``/``sns_pastel``/``sns_dark``/``sns_colorblind``)::

    from pyplotrs import palettes, themes

    palettes.available()          # ['Accent', 'Dark2', ..., 'tab20c']
    palettes.get("tab10")         # ((31, 119, 180, 255), (255, 127, 14, 255), ...)

    # Use directly as a theme's cycling palette:
    mine = themes.default.with_(palette=palettes.get("tab10"))

The theme's own default cycle (Okabe-Ito, colorblind-safe by construction) is
unaffected - see [`Theme`][pyplotrs.theme.Theme].
"""

from __future__ import annotations

from . import _pyplotrs_core as _core

#: The public surface of this module. Without it, `from ... import *`
#: and every editor's completion list also offer `Sequence`, `math` and
#: `annotations` - names that are imported here, not exported from here.
__all__ = [
    "available",
    "get",
]


_RGBA = tuple[int, int, int, int]


def get(name: str) -> tuple[_RGBA, ...]:
    """The colors of a built-in palette, as opaque RGBA tuples."""
    colors = _core.categorical_palette(name)
    if colors is None:
        raise ValueError(f"unknown palette {name!r}; see pyplotrs.palettes.available()")
    return tuple((r, g, b, 255) for r, g, b in colors)


def available() -> list[str]:
    """Names of every built-in categorical/qualitative palette."""
    return sorted(_core.list_palettes())
