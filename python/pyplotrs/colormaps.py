"""Built-in colormaps.

A :class:`Colormap` maps a scalar in ``[0, 1]`` to an ``(r, g, b, a)`` byte
tuple. This is the LUT machinery behind ``Axes.imshow`` / ``Figure.colorbar``.

Every :class:`Colormap` is backed by an exact 256-entry RGB table, indexed
directly - so sampling is always O(1), never interpolation math on the hot
path. That table comes from one of two places:

* **built-in name** - an exact table sourced from upstream (matplotlib,
  colorcet, or cmocean - see :func:`available`), bit-for-bit faithful, not an
  approximation. A trailing ``"_r"`` reverses it.
* **custom stops** - ``Colormap(name, stops=[(0.0, (0, 0, 0)), ...])``
  resamples your control colors to 256 entries in **Oklab** space by default
  (see :mod:`pyplotrs.color`), so gradients look perceptually smooth rather
  than banding the way a naive sRGB lerp does.

Both the table data and all interpolation math run in Rust
(:mod:`pyplotrs._pyplotrs_core`, backed by the ``pyplotrs-color`` crate).
"""

from __future__ import annotations

from typing import Sequence

from . import _pyplotrs_core as _core

_RGBA = tuple[int, int, int, int]
_RGB = tuple[int, int, int]
_Stop = tuple[float, _RGB]

#: The categories a built-in continuous colormap can be filtered to via
#: ``available(category=...)``.
CATEGORIES = (
    "perceptually_uniform",
    "sequential",
    "diverging",
    "cyclic",
    "miscellaneous",
)


class Colormap:
    """A colormap: 256 exact RGB entries, sampled by nearest index.

    Construct either from interpolated ``stops`` (the public, ergonomic
    path)::

        Colormap("warm", [(0.0, (0, 0, 0)), (1.0, (255, 128, 0))])

    or from an exact 256-entry ``table`` of ``(r, g, b)`` byte triples - the
    form every built-in name uses internally::

        Colormap("viridis", table=viridis_table)

    ``space`` selects the color space ``stops`` are interpolated in:
    ``"oklab"`` (default), ``"lab"``, ``"linear"`` (linear-light RGB), or
    ``"srgb"`` (naive gamma-space lerp, kept for parity with pre-1.0
    behavior).
    """

    def __init__(
        self,
        name: str,
        stops: Sequence[_Stop] | None = None,
        *,
        table: Sequence[_RGB] | None = None,
        space: str = "oklab",
    ) -> None:
        if (stops is None) == (table is None):
            raise ValueError("provide exactly one of `stops` or `table`")
        self.name = name
        if table is not None:
            t = tuple((int(r), int(g), int(b)) for r, g, b in table)
            if len(t) != 256:
                raise ValueError(f"a colormap table needs exactly 256 entries, got {len(t)}")
            self._table: tuple[_RGB, ...] = t
        else:
            assert stops is not None
            s = [(float(p), (int(r), int(g), int(b))) for p, (r, g, b) in stops]
            if len(s) < 2:
                raise ValueError("a colormap needs at least two stops")
            self._table = tuple(_core.colormap_table_from_stops(s, space))

    def __call__(self, t: float) -> _RGBA:
        """Sample the map at ``t`` (clamped to ``[0, 1]``; NaN -> low end)."""
        tbl = self._table
        if t != t or t <= 0.0:  # NaN or low
            r, g, b = tbl[0]
        elif t >= 1.0:
            r, g, b = tbl[-1]
        else:
            r, g, b = tbl[int(t * 255.0 + 0.5)]
        return (r, g, b, 255)

    def reversed(self) -> "Colormap":
        return Colormap(self.name + "_r", table=tuple(reversed(self._table)))


_CMAP_CACHE: dict[str, Colormap] = {}


def get_cmap(name) -> Colormap:
    """Look up a colormap by name. A ``_r`` suffix reverses it
    (e.g. ``"viridis_r"``). Passing a :class:`Colormap` returns it unchanged."""
    if isinstance(name, Colormap):
        return name
    key = str(name)
    hit = _CMAP_CACHE.get(key)
    if hit is not None:
        return hit
    table = _core.colormap_table(key)
    if table is None:
        raise ValueError(
            f"unknown colormap {name!r}; see pyplotrs.colormaps.available()"
        )
    cm = Colormap(key, table=table)
    _CMAP_CACHE[key] = cm
    return cm


def available(category: str | None = None) -> list[str]:
    """Names of built-in continuous colormaps (each also usable with a
    ``"_r"`` suffix to reverse it), optionally filtered to one ``category``
    (see :data:`CATEGORIES`)."""
    if category is not None and category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}; choose from {CATEGORIES}")
    return sorted(_core.list_colormaps(category))
