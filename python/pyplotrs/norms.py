"""Normalizations: how values map onto a colormap.

``norm(v)`` gives a value's position in ``[0, 1]``. Pass one as ``norm=`` to
colormapped marks, or the shorthand ``"log"``::

    ax.imshow(z, norm="log")
    ax.imshow(anomaly, cmap="RdBu_r", norm=pp.norms.TwoSlopeNorm(0))
"""

from __future__ import annotations

import copy
import itertools
import math
from collections.abc import Sequence

from . import _core
from .colormaps import Colormap
from .scales import Log, Tick, nice_ticks
from .ticker import plain

__all__ = ["BoundaryNorm", "LogNorm", "Norm", "TwoSlopeNorm", "get"]


class Norm:
    """Linear between ``vmin`` and ``vmax``. Limits left as ``None`` are taken
    from the data."""

    #: The matching transform in the Rust engine; None for a piecewise norm,
    #: which is folded into the color table instead.
    code: str | None = "linear"

    def __init__(self, vmin: float | None = None, vmax: float | None = None) -> None:
        self.vmin = None if vmin is None else float(vmin)
        self.vmax = None if vmax is None else float(vmax)

    def autoscale(self, values) -> Norm:
        """A copy with any missing limit taken from ``values``."""
        out = copy.copy(self)
        if out.vmin is None or out.vmax is None:
            lo, hi = _core.finite_range(values, self.code or "linear") or self._empty
            out.vmin = lo if out.vmin is None else out.vmin
            out.vmax = hi if out.vmax is None else out.vmax
        out._fix_singular()
        return out

    _empty = (0.0, 1.0)

    def _fix_singular(self) -> None:
        if self.vmin == self.vmax:
            self.vmax = self.limits[0] + 1.0

    @property
    def limits(self) -> tuple[float, float]:
        if self.vmin is None or self.vmax is None:
            raise ValueError("this norm has no limits yet; call autoscale(values) first")
        return self.vmin, self.vmax

    def __call__(self, v: float) -> float:
        lo, hi = self.limits
        return min(1.0, max(0.0, (v - lo) / ((hi - lo) or 1.0)))

    def ticks(self, max_ticks: int = 6, minus: bool = True) -> list[Tick]:
        return nice_ticks(*self.limits, max_ticks, minus)

    def lut(self, cmap: Colormap, alpha: float = 1.0) -> tuple[bytes, str]:
        """``(lut, code)`` for the Rust colormapper."""
        if self.code is not None:
            return cmap.lut(alpha), self.code
        lo, hi = self.limits
        a = min(255, max(0, round(alpha * 255)))
        out = bytearray()
        for i in range(256):
            r, g, b, _ = cmap(self(lo + (hi - lo) * i / 255))
            out += bytes((r, g, b, a))
        return bytes(out), "linear"

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in vars(self).items())
        return f"{type(self).__name__}({args})"


class LogNorm(Norm):
    """Logarithmic, for positive data."""

    code = "log"
    _empty = (1.0, 10.0)

    def _fix_singular(self) -> None:
        if self.vmin == self.vmax:
            self.vmax = self.limits[0] * 10.0

    def __call__(self, v: float) -> float:
        lo, hi = self.limits
        if v <= 0:
            return 0.0
        return min(1.0, max(0.0, math.log10(v / lo) / (math.log10(hi / lo) or 1.0)))

    def ticks(self, max_ticks: int = 6, minus: bool = True) -> list[Tick]:
        return Log().ticks(*self.limits, max_ticks, minus)


class TwoSlopeNorm(Norm):
    """Diverging: ``vcenter`` maps to the middle of the colormap and each side
    is scaled on its own."""

    code = None

    def __init__(
        self, vcenter: float = 0.0, vmin: float | None = None, vmax: float | None = None
    ) -> None:
        super().__init__(vmin, vmax)
        self.vcenter = float(vcenter)

    def _fix_singular(self) -> None:
        lo, hi = self.limits
        c = self.vcenter
        self.vmin, self.vmax = (lo if lo < c else c - 1.0), (hi if hi > c else c + 1.0)

    def __call__(self, v: float) -> float:
        lo, hi = self.limits
        c = self.vcenter
        if v < c:
            return max(0.0, 0.5 * (v - lo) / (c - lo))
        return min(1.0, 0.5 + 0.5 * (v - c) / (hi - c))


class BoundaryNorm(Norm):
    """Discrete bins between ``boundaries``, one color each."""

    code = None

    def __init__(self, boundaries: Sequence[float]) -> None:
        b = tuple(float(v) for v in boundaries)
        if len(b) < 2 or any(y <= x for x, y in itertools.pairwise(b)):
            raise ValueError("boundaries must be at least two increasing values")
        super().__init__(b[0], b[-1])
        self.boundaries = b

    def __call__(self, v: float) -> float:
        n = len(self.boundaries) - 1
        i = sum(1 for x in self.boundaries[1:-1] if v >= x)
        return (i + 0.5) / n

    def ticks(self, max_ticks: int = 6, minus: bool = True) -> list[Tick]:
        return [(v, plain(v, minus)) for v in self.boundaries]


def get(norm: Norm | str | None, vmin: float | None = None, vmax: float | None = None) -> Norm:
    """A norm from an instance, ``"linear"``, ``"log"`` or ``None``;
    ``vmin``/``vmax`` fill limits the norm leaves unset."""
    if norm is None or norm == "linear":
        return Norm(vmin, vmax)
    if norm == "log":
        return LogNorm(vmin, vmax)
    if isinstance(norm, Norm):
        out = copy.copy(norm)
        out.vmin = out.vmin if out.vmin is not None else (None if vmin is None else float(vmin))
        out.vmax = out.vmax if out.vmax is not None else (None if vmax is None else float(vmax))
        return out
    raise ValueError(f"unknown norm {norm!r}; expected 'linear', 'log' or a Norm")
