"""Built-in colormaps.

A :class:`Colormap` maps a scalar in ``[0, 1]`` to an ``(r, g, b, a)`` byte
tuple. This is the LUT machinery behind ``Axes.imshow`` / ``Figure.colorbar``.

Two kinds of map are supported:

* **table-backed** — an exact 256-entry lookup table, indexed directly. The
  perceptually-uniform maps (viridis/plasma/inferno/magma/cividis) use the
  canonical CC0 tables from matplotlib (see :mod:`pyplotrs._colormap_data`), so
  they are bit-for-bit faithful, not approximations.
* **stop-backed** — a short list of ``(position, (r, g, b))`` stops with linear
  interpolation between them. Used for the simple analytic maps (``grays``,
  ``coolwarm``) and for any map a user constructs via ``Colormap(name, stops)``.
"""

from __future__ import annotations

from typing import Sequence

from ._colormap_data import _TABLES

_RGBA = tuple[int, int, int, int]
_RGB = tuple[int, int, int]
_Stop = tuple[float, _RGB]


class Colormap:
    """A colormap.

    Construct either from interpolated ``stops`` (the public, ergonomic path)::

        Colormap("warm", [(0.0, (0, 0, 0)), (1.0, (255, 128, 0))])

    or from an exact 256-entry ``table`` of ``(r, g, b)`` byte triples::

        Colormap("viridis", table=viridis_lut)
    """

    def __init__(
        self,
        name: str,
        stops: Sequence[_Stop] | None = None,
        *,
        table: Sequence[_RGB] | None = None,
    ) -> None:
        if (stops is None) == (table is None):
            raise ValueError("provide exactly one of `stops` or `table`")
        self.name = name
        if table is not None:
            self._table: tuple[_RGB, ...] | None = tuple(
                (int(r), int(g), int(b)) for r, g, b in table
            )
            if len(self._table) < 2:
                raise ValueError("a colormap table needs at least two entries")
            self._stops: list[_Stop] | None = None
        else:
            assert stops is not None
            s = [(float(p), (int(r), int(g), int(b))) for p, (r, g, b) in stops]
            if len(s) < 2:
                raise ValueError("a colormap needs at least two stops")
            self._stops = s
            self._table = None

    def __call__(self, t: float) -> _RGBA:
        """Sample the map at ``t`` (clamped to ``[0, 1]``; NaN -> low end)."""
        if self._table is not None:
            tbl = self._table
            n = len(tbl)
            if t != t or t <= 0.0:  # NaN or low
                r, g, b = tbl[0]
            elif t >= 1.0:
                r, g, b = tbl[-1]
            else:
                r, g, b = tbl[int(t * (n - 1) + 0.5)]
            return (r, g, b, 255)

        stops = self._stops
        assert stops is not None
        if t != t or t <= 0.0:
            r, g, b = stops[0][1]
            return (r, g, b, 255)
        if t >= 1.0:
            r, g, b = stops[-1][1]
            return (r, g, b, 255)
        for i in range(1, len(stops)):
            p1, c1 = stops[i]
            if t <= p1:
                p0, c0 = stops[i - 1]
                f = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
                r = int(round(c0[0] + (c1[0] - c0[0]) * f))
                g = int(round(c0[1] + (c1[1] - c0[1]) * f))
                b = int(round(c0[2] + (c1[2] - c0[2]) * f))
                return (r, g, b, 255)
        r, g, b = stops[-1][1]
        return (r, g, b, 255)

    def reversed(self) -> "Colormap":
        if self._table is not None:
            return Colormap(self.name + "_r", table=tuple(reversed(self._table)))
        assert self._stops is not None
        rev = [(1.0 - p, c) for p, c in reversed(self._stops)]
        return Colormap(self.name + "_r", rev)


def _even_stops(colors: Sequence[_RGB]) -> list[_Stop]:
    """Spread ``colors`` evenly over ``[0, 1]``."""
    n = len(colors)
    return [(i / (n - 1), c) for i, c in enumerate(colors)]


# -- bundled maps -----------------------------------------------------------

# Perceptually-uniform maps: exact 256-entry CC0 tables.
_PERCEPTUAL = ("viridis", "plasma", "inferno", "magma", "cividis")

# grays: exact black->white.
_GRAYS = [(0.0, (0, 0, 0)), (1.0, (255, 255, 255))]

# coolwarm: exact diverging blue->light->red (matplotlib endpoints).
_COOLWARM = [(0.0, (59, 76, 192)), (0.5, (221, 221, 221)), (1.0, (180, 4, 38))]


_CMAPS: dict[str, Colormap] = {
    name: Colormap(name, table=_TABLES[name]) for name in _PERCEPTUAL
}
_CMAPS["grays"] = Colormap("grays", _GRAYS)
_CMAPS["coolwarm"] = Colormap("coolwarm", _COOLWARM)
# Convenience aliases.
_CMAPS["gray"] = _CMAPS["grays"]


def get_cmap(name) -> Colormap:
    """Look up a colormap by name. A ``_r`` suffix reverses it
    (e.g. ``"viridis_r"``). Passing a :class:`Colormap` returns it unchanged."""
    if isinstance(name, Colormap):
        return name
    key = str(name)
    if key.endswith("_r"):
        base = _CMAPS.get(key[:-2])
        if base is not None:
            return base.reversed()
    cm = _CMAPS.get(key)
    if cm is None:
        raise ValueError(
            f"unknown colormap {name!r}; available: {', '.join(sorted(_CMAPS))}"
        )
    return cm


def available() -> list[str]:
    """Names of all bundled colormaps."""
    return sorted(_CMAPS)
