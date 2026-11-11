"""One axis of a 2D plot: its scale, limits and ticks."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from . import scales as _scales
from . import ticker
from .scales import Scale
from .text import Label

Range = tuple[float, float]

DEFAULT_MARGIN = 0.05


@dataclass
class Ticks:
    values: list[float]
    labels: list[Label]
    minor: list[float] = field(default_factory=list)
    #: Shared offset/multiplier lifted out of the labels ("" for none).
    offset: str = ""


@dataclass
class Axis:
    scale: Scale = field(default_factory=_scales.Linear)
    label: Label | None = None
    #: Pinned limits; either end may be None to autoscale it.
    limits: tuple[float | None, float | None] | None = None
    margin: float = DEFAULT_MARGIN
    inverted: bool = False
    ticks: list[float] | None = None
    ticklabels: list[Label] | None = None
    formatter: Callable[..., str] | None = None
    #: Minor intervals per major interval on a linear axis (0 = none).
    minor: int = 0
    max_ticks: int = 7
    #: Ranges cut out of the axis (a broken axis), sorted, each ``(lo, hi)``.
    breaks: list[Range] = field(default_factory=list)

    def pieces(self, view: Range) -> list[Range]:
        """The parts of ``view`` left after cutting out the breaks, in view
        order. Breaks not strictly inside the view are ignored."""
        v0, v1 = view
        lo, hi = min(v0, v1), max(v0, v1)
        out, start = [], lo
        for a, b in self.breaks:
            if start < a and b < hi:
                out.append((start, a))
                start = b
        out.append((start, hi))
        return out if v0 <= v1 else [(b, a) for a, b in reversed(out)]

    def locate_view(self, view: Range, minus: bool = True) -> Ticks:
        """Ticks for the whole view, located piece by piece on a broken axis."""
        return join([self.locate(*p, minus=minus) for p in self.pieces(view)], minus)

    def view(self, data: Range | None, sticky: Sequence[float] = ()) -> Range:
        """The visible range for data spanning ``data``."""
        lo_pin, hi_pin = self.limits or (None, None)
        if lo_pin is not None and hi_pin is not None:
            return (lo_pin, hi_pin)
        fixed = self.scale.fixed_range()
        if fixed is not None:
            lo, hi = fixed
        elif data is None:
            lo, hi = self.scale.default_range()
        else:
            lo, hi = self._pad(data, sticky)
        lo, hi = (lo if lo_pin is None else lo_pin), (hi if hi_pin is None else hi_pin)
        return (hi, lo) if self.inverted else (lo, hi)

    def _pad(self, data: Range, sticky: Sequence[float]) -> Range:
        """Add the margin in transformed space (so it means the same on any
        scale), but never past a value the data rests on."""
        s = self.scale
        t0, t1 = s.transform(data[0]), s.transform(data[1])
        if not (math.isfinite(t0) and math.isfinite(t1)):
            return s.default_range()
        if t0 == t1:
            d = abs(t0) * 0.05 if isinstance(s, _scales.Linear) and t0 else 0.5
            t0, t1 = t0 - d, t1 + d
        # On a broken axis the padding is a fraction of what is shown.
        cut = sum(
            s.transform(b) - s.transform(a) for a, b in self.breaks if data[0] < a and b < data[1]
        )
        pad = (t1 - t0 - cut) * self.margin
        lo, hi = s.inverse(t0 - pad), s.inverse(t1 + pad)
        tol = 1e-5 * abs(data[1] - data[0])
        below = [v for v in sticky if v <= data[0] + tol]
        above = [v for v in sticky if v >= data[1] - tol]
        if below:
            lo = max(lo, max(below))
        if above:
            hi = min(hi, min(above))
        return (lo, hi) if lo < hi else (s.inverse(t0 - pad), s.inverse(t1 + pad))

    def locate(self, lo: float, hi: float, minus: bool = True) -> Ticks:
        """Tick positions and labels for the view ``lo..hi``."""
        a, b = min(lo, hi), max(lo, hi)
        offset = ""
        if self.ticks is not None:
            eps = (b - a) * 1e-9
            values = [v for v in self.ticks if a - eps <= v <= b + eps]
            labels: list[Label] = [ticker.plain(v, minus) for v in values]
            if self.ticklabels is not None:
                by_value = dict(zip(self.ticks, self.ticklabels, strict=False))
                labels = [by_value.get(v, "") for v in values]
        else:
            pairs = self.scale.ticks(a, b, self.max_ticks, minus)
            values = [v for v, _ in pairs]
            labels = [s for _, s in pairs]
            if self.ticklabels is not None:
                labels = [
                    *self.ticklabels[: len(values)],
                    *[""] * (len(values) - len(self.ticklabels)),
                ]
            elif self.formatter is None and self.scale.offset_labels:
                shift, exponent = ticker.factor_out(values)
                if shift or exponent:
                    labels = list(ticker.relative_labels(values, shift, exponent, minus))
                    offset = ticker.offset_text(shift, exponent, minus)
        if self.formatter is not None and self.ticklabels is None:
            labels = list(ticker.format_ticks(self.formatter, values, minus))
        return Ticks(values, labels, self._minor(values, a, b), offset)

    def _minor(self, majors: list[float], lo: float, hi: float) -> list[float]:
        minor = self.scale.minor_ticks(lo, hi)
        if minor or self.minor < 2 or len(majors) < 2:
            return minor
        step = (majors[1] - majors[0]) / self.minor
        start = math.ceil((lo - majors[0]) / step - 1e-9)
        stop = math.floor((hi - majors[0]) / step + 1e-9)
        return [majors[0] + k * step for k in range(start, stop + 1) if k % self.minor]


def join(parts: list[Ticks], minus: bool = True) -> Ticks:
    """One tick list from the ticks of each piece of a broken axis."""
    if len(parts) == 1:
        return parts[0]
    values = [v for p in parts for v in p.values]
    minor = [v for p in parts for v in p.minor]
    if len({p.offset for p in parts}) == 1:
        return Ticks(values, [s for p in parts for s in p.labels], minor, parts[0].offset)
    # The pieces would need different offsets; label every tick in full.
    return Ticks(values, [ticker.plain(v, minus) for v in values], minor)
