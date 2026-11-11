"""Colormaps and categorical palettes.

About 125 built-in colormaps (from matplotlib, colorcet and cmocean) and 25
palettes (matplotlib, ColorBrewer, seaborn). Any name takes an ``_r`` suffix
to reverse it::

    ax.imshow(z, cmap="magma_r")
    pp.colormaps.names("diverging")
    cmap = pp.Colormap.from_colors(["navy", "white", "firebrick"])
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import cache

from . import _core
from .colors import RGBA, ColorLike, to_rgba

__all__ = ["Colormap", "get", "names", "palette", "palette_names"]


class Colormap:
    """A 256-entry color table. Call it with a position in ``[0, 1]``."""

    __slots__ = ("_lut", "name", "table")

    def __init__(self, name: str, table: bytes) -> None:
        if len(table) != 768:
            raise ValueError("a colormap table is 256 RGB entries (768 bytes)")
        self.name = name
        self.table = bytes(table)
        self._lut: dict[float, bytes] = {}

    @classmethod
    def from_colors(
        cls,
        colors: Sequence[ColorLike],
        name: str = "custom",
        *,
        positions: Sequence[float] | None = None,
        space: str = "oklab",
    ) -> Colormap:
        """Interpolate between colors (evenly spaced unless ``positions`` is
        given) in a perceptual color space: ``"oklab"`` (default), ``"lab"``,
        ``"linear"`` or ``"srgb"``."""
        if len(colors) < 2:
            raise ValueError("a colormap needs at least two colors")
        if positions is None:
            positions = [i / (len(colors) - 1) for i in range(len(colors))]
        if len(positions) != len(colors):
            raise ValueError("positions and colors must have the same length")
        stops = [(float(p), to_rgba(c)[:3]) for p, c in zip(positions, colors, strict=True)]
        return cls(name, _core.colormap_from_stops(stops, space))

    def __call__(self, t: float) -> RGBA:
        i = 3 * min(255, max(0, round(t * 255.0))) if t == t else 0
        return (self.table[i], self.table[i + 1], self.table[i + 2], 255)

    def reversed(self) -> Colormap:
        rows = [self.table[i : i + 3] for i in range(0, 768, 3)]
        name = self.name[:-2] if self.name.endswith("_r") else self.name + "_r"
        return Colormap(name, b"".join(reversed(rows)))

    def lut(self, alpha: float = 1.0) -> bytes:
        """The table as 256 RGBA entries (1024 bytes) with uniform ``alpha``."""
        hit = self._lut.get(alpha)
        if hit is None:
            a = min(255, max(0, round(alpha * 255)))
            t = self.table
            hit = bytes(v for i in range(0, 768, 3) for v in (t[i], t[i + 1], t[i + 2], a))
            self._lut[alpha] = hit
        return hit

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Colormap) and self.table == other.table

    def __hash__(self) -> int:
        return hash(self.table)

    def __repr__(self) -> str:
        return f"<Colormap {self.name!r}>"


@cache
def _builtin(name: str) -> Colormap | None:
    table = _core.colormap_table(name)
    return None if table is None else Colormap(name, table)


def get(cmap: str | Colormap) -> Colormap:
    """A colormap by name, or the colormap itself."""
    if isinstance(cmap, Colormap):
        return cmap
    found = _builtin(cmap)
    if found is None:
        raise ValueError(f"unknown colormap {cmap!r}; see pyplotrs.colormaps.names()")
    return found


def names(category: str | None = None) -> list[str]:
    """Built-in colormap names, optionally one category: ``"sequential"``,
    ``"diverging"``, ``"cyclic"``, ``"perceptually_uniform"`` or
    ``"miscellaneous"``."""
    return list(_core.colormap_names(category))


def palette(name: str) -> tuple[RGBA, ...]:
    """A built-in categorical palette, e.g. ``"tab10"``, ``"Set2"``."""
    colors = _core.palette(name)
    if colors is None:
        raise ValueError(f"unknown palette {name!r}; see pyplotrs.colormaps.palette_names()")
    return tuple((r, g, b, 255) for r, g, b in colors)


def palette_names() -> list[str]:
    return list(_core.palette_names())
