"""Normalizations: map data values into ``[0, 1]`` for colormap lookup.

A :class:`Normalize` (and its subclasses) is the colorbar/colormap analogue of a
:class:`~pyplotrs.scales.Scale`: ``norm(value)`` returns the position in ``[0, 1]``
a value occupies on the color axis, and ``norm.colorbar_ticks()`` locates labelled
ticks for a colorbar. Used by :meth:`pyplotrs.Axes.scatter` (``c=``) and
:meth:`pyplotrs.Axes.imshow` (``norm=``).
"""

from __future__ import annotations

import math
from typing import Sequence

from . import _pyplotrs_core as _core
from . import scales as _scales

_Tick = tuple[float, str]


class Normalize:
    """Linear normalization between ``vmin`` and ``vmax`` (clamped to ``[0, 1]``).
    ``vmin``/``vmax`` left ``None`` are filled from the data by :meth:`autoscale`."""

    def __init__(self, vmin: float | None = None, vmax: float | None = None) -> None:
        self.vmin = None if vmin is None else float(vmin)
        self.vmax = None if vmax is None else float(vmax)

    def autoscale(self, values: Sequence[float]) -> "Normalize":
        """Fill any unset ``vmin``/``vmax`` from the finite members of ``values``."""
        if self.vmin is None or self.vmax is None:
            finite = [v for v in values if math.isfinite(v)]
            lo, hi = (min(finite), max(finite)) if finite else (0.0, 1.0)
            if self.vmin is None:
                self.vmin = lo
            if self.vmax is None:
                self.vmax = hi
        if self.vmin == self.vmax:  # avoid a zero-width range
            self.vmax = self.vmin + 1.0
        return self

    def __call__(self, value: float) -> float:
        span = (self.vmax - self.vmin) or 1.0
        return min(1.0, max(0.0, (value - self.vmin) / span))

    def colorbar_ticks(self, max_ticks: int = 6) -> list[_Tick]:
        return _core.nice_ticks(self.vmin, self.vmax, max_ticks)


class LogNorm(Normalize):
    """Logarithmic normalization (positive data). Colorbar ticks fall on decades."""

    def autoscale(self, values: Sequence[float]) -> "LogNorm":
        if self.vmin is None or self.vmax is None:
            pos = [v for v in values if v > 0 and math.isfinite(v)]
            lo, hi = (min(pos), max(pos)) if pos else (1.0, 10.0)
            if self.vmin is None:
                self.vmin = lo
            if self.vmax is None:
                self.vmax = hi
        if self.vmin == self.vmax:
            self.vmax = self.vmin * 10.0
        return self

    def __call__(self, value: float) -> float:
        if value <= 0.0:
            return 0.0
        lo, hi = math.log10(self.vmin), math.log10(self.vmax)
        span = (hi - lo) or 1.0
        return min(1.0, max(0.0, (math.log10(value) - lo) / span))

    def colorbar_ticks(self, max_ticks: int = 6) -> list[_Tick]:
        return _scales.LogScale().ticks(self.vmin, self.vmax, max_ticks)


class TwoSlopeNorm(Normalize):
    """Diverging normalization: ``vcenter`` maps to ``0.5`` with independent
    slopes on each side (for asymmetric data around a meaningful midpoint)."""

    def __init__(self, vcenter: float, vmin: float | None = None,
                 vmax: float | None = None) -> None:
        super().__init__(vmin, vmax)
        self.vcenter = float(vcenter)

    def autoscale(self, values: Sequence[float]) -> "TwoSlopeNorm":
        super().autoscale(values)
        # Keep the center strictly inside the range.
        if self.vmin >= self.vcenter:
            self.vmin = self.vcenter - 1.0
        if self.vmax <= self.vcenter:
            self.vmax = self.vcenter + 1.0
        return self

    def __call__(self, value: float) -> float:
        if value < self.vcenter:
            return max(0.0, 0.5 * (value - self.vmin) / (self.vcenter - self.vmin))
        return min(1.0, 0.5 + 0.5 * (value - self.vcenter) / (self.vmax - self.vcenter))


class BoundaryNorm(Normalize):
    """Map values into discrete bins defined by ``boundaries`` (monotone), each
    bin getting an evenly-spaced color position (for stepped colorbars)."""

    def __init__(self, boundaries: Sequence[float]) -> None:
        bnd = [float(b) for b in boundaries]
        super().__init__(bnd[0], bnd[-1])
        self.boundaries = bnd
        self.nbins = len(bnd) - 1

    def autoscale(self, values: Sequence[float]) -> "BoundaryNorm":
        return self  # boundaries are explicit

    def __call__(self, value: float) -> float:
        # Index of the bin containing `value`, mapped to the bin's center in [0,1].
        idx = 0
        for i in range(self.nbins):
            if value >= self.boundaries[i]:
                idx = i
        return min(1.0, max(0.0, (idx + 0.5) / self.nbins))

    def colorbar_ticks(self, max_ticks: int = 6) -> list[_Tick]:
        return [(b, _scales._fmt_plain(b) if b == int(b) else f"{b:g}")
                for b in self.boundaries]


def get(norm, vmin: float | None, vmax: float | None) -> Normalize:
    """Resolve a ``norm`` argument (a :class:`Normalize`, the string ``"log"``,
    or ``None``) plus optional ``vmin``/``vmax`` into a :class:`Normalize`."""
    if norm is None:
        return Normalize(vmin, vmax)
    if isinstance(norm, Normalize):
        if vmin is not None and norm.vmin is None:
            norm.vmin = float(vmin)
        if vmax is not None and norm.vmax is None:
            norm.vmax = float(vmax)
        return norm
    if isinstance(norm, str):
        if norm == "log":
            return LogNorm(vmin, vmax)
        if norm == "linear":
            return Normalize(vmin, vmax)
        raise ValueError(f"unknown norm {norm!r}; expected 'linear', 'log', or a Normalize")
    raise TypeError(f"expected a Normalize, 'log'/'linear', or None; got {type(norm).__name__}")
