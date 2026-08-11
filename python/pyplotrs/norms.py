"""Normalizations: map data values into ``[0, 1]`` for colormap lookup.

A ``Normalize`` (and its subclasses) is the colorbar/colormap analog of a
[`Scale`][pyplotrs.scales.Scale]: ``norm(value)`` returns the position in ``[0, 1]``
a value occupies on the color axis, and ``norm.colorbar_ticks()`` locates labeled
ticks for a colorbar. Used by [`Axes.scatter`][pyplotrs.axes.Axes.scatter] (``c=``) and
[`Axes.imshow`][pyplotrs.axes.Axes.imshow] (``norm=``).
"""

from __future__ import annotations

import math
from array import array
from typing import Sequence

from . import _pyplotrs_core as _core
from . import scales as _scales
from . import ticker as _ticker
from ._util import _auto_repr


def _as_f64(values) -> "array":
    """Coerce to a contiguous ``array("d")`` so the Rust reductions can read it
    as a buffer. Mirrors ``figure._to_f64``; kept local to avoid a circular
    import between this module and ``figure``."""
    if type(values) is array and values.typecode == "d":
        return values
    try:
        return array("d", values)
    except (TypeError, ValueError):
        return array("d", [float(v) for v in values])

_Tick = tuple[float, str]


class Normalize:
    """Linear normalization between ``vmin`` and ``vmax`` (clamped to ``[0, 1]``).
    ``vmin``/``vmax`` left ``None`` are filled from the data by ``autoscale``."""

    def __repr__(self) -> str:
        return _auto_repr(self)


    #: Rust ``apply_scale`` selector, mirroring [`pyplotrs.scales.Scale.code`][pyplotrs.scales.Scale.code].
    #: When set, bulk color mapping runs in Rust via ``_core.map_colors``;
    #: ``None`` means this norm has no Rust equivalent and each value must go
    #: through ``__call__`` in Python. Must name a branch ``apply_scale`` handles.
    code: str | None = "linear"

    def __init__(self, vmin: float | None = None, vmax: float | None = None) -> None:
        self.vmin = None if vmin is None else float(vmin)
        self.vmax = None if vmax is None else float(vmax)

    def autoscale(self, values: Sequence[float]) -> "Normalize":
        """Fill any unset ``vmin``/``vmax`` from the finite members of ``values``."""
        if self.vmin is None or self.vmax is None:
            lo, hi = _core.data_range(_as_f64(values)) or (0.0, 1.0)
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
        return _scales.nice_ticks(self.vmin, self.vmax, max_ticks)


class LogNorm(Normalize):
    """Logarithmic normalization (positive data). Colorbar ticks fall on decades."""

    code = "log"

    def autoscale(self, values: Sequence[float]) -> "LogNorm":
        if self.vmin is None or self.vmax is None:
            lo, hi = _core.positive_range(_as_f64(values)) or (1.0, 10.0)
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

    code = None  # piecewise: no single Rust scale transform matches it

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

    code = None  # discrete binning: no Rust scale transform matches it

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
        return [(b, _ticker.fix_minus(f"{b:g}") if b != int(b) else _scales._fmt_plain(b))
                for b in self.boundaries]


def get(norm, vmin: float | None, vmax: float | None) -> Normalize:
    """Resolve a ``norm`` argument (a ``Normalize``, the string ``"log"``,
    or ``None``) plus optional ``vmin``/``vmax`` into a ``Normalize``."""
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
