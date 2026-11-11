"""Axis scales: how data values map onto an axis, and where its ticks go.

Pass a name or an instance to ``Axes.set``::

    ax.set(yscale="log")
    ax.set(xscale=pp.scales.Symlog(linthresh=1e-3))

Each scale's ``code`` names the same transform in the Rust engine, so drawing
never calls back into Python per point.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from typing import ClassVar

from . import ticker

__all__ = [
    "Categorical",
    "Date",
    "Linear",
    "Log",
    "Logit",
    "Scale",
    "Symlog",
    "date2num",
    "get",
    "nice_ticks",
    "num2date",
]

Tick = tuple[float, str]

_NICE_STEPS = (1.0, 2.0, 2.5, 5.0)


def nice_step(lo: float, hi: float, max_ticks: int) -> float:
    """The smallest step from {1, 2, 2.5, 5} x 10^n giving at most ``max_ticks`` ticks."""
    span = abs(hi - lo)
    if span == 0.0 or not math.isfinite(span):
        return 1.0
    max_ticks = max(max_ticks, 2)
    mag = 10.0 ** math.floor(math.log10(span / max_ticks))
    for mult in _NICE_STEPS:
        if span / (mult * mag) <= max_ticks - 1 + 1e-9:
            return mult * mag
    return 10.0 * mag


def _round_sig(v: float, digits: int = 12) -> float:
    """Erase float noise relative to the value's own magnitude."""
    if v == 0.0 or not math.isfinite(v):
        return v
    return round(v, digits - 1 - math.floor(math.log10(abs(v))))


def _decimals(step: float) -> int:
    for d in range(18):
        scaled = abs(step) * 10.0**d
        if scaled >= 1.0 - 1e-9 and abs(scaled - round(scaled)) < 1e-6 * scaled:
            return d
    return 17


def nice_ticks(lo: float, hi: float, max_ticks: int = 7, minus: bool = True) -> list[Tick]:
    """Round-number ticks covering ``[lo, hi]``, labeled to the step's precision."""
    lo, hi = min(lo, hi), max(lo, hi)
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo == hi:
        return [(lo, ticker.plain(lo, minus))]
    step = nice_step(lo, hi, max_ticks)
    eps = step * 1e-9
    first, last = math.ceil((lo - eps) / step), math.floor((hi + eps) / step)
    places = _decimals(step)
    out = []
    for k in range(first, last + 1):
        v = _round_sig(k * step) + 0.0  # + 0.0 turns -0.0 into 0.0
        s = f"{v:.{places}f}"
        if s.lstrip("-").strip("0.") == "":
            s = s.lstrip("-")
        out.append((v, ticker.fix_minus(s, minus)))
    return out


class Scale:
    """An axis scale. Subclasses define the transform and the tick locator."""

    name: ClassVar[str] = "linear"
    #: Allow the shared offset/exponent to be lifted out of tick labels.
    offset_labels: ClassVar[bool] = False

    @property
    def code(self) -> str:
        """The transform's name in the Rust engine."""
        return "linear"

    def transform(self, v: float) -> float:
        return v

    def inverse(self, t: float) -> float:
        return t

    def ticks(self, lo: float, hi: float, max_ticks: int = 7, minus: bool = True) -> list[Tick]:
        return nice_ticks(lo, hi, max_ticks, minus)

    def minor_ticks(self, lo: float, hi: float) -> list[float]:
        return []

    def default_range(self) -> tuple[float, float]:
        """The view shown when there is no data."""
        return (0.0, 1.0)

    def fixed_range(self) -> tuple[float, float] | None:
        """A view that ignores the data, if the scale has one."""
        return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} scale>"


class Linear(Scale):
    name = "linear"
    offset_labels = True


def _pow10(k: int) -> str:
    return f"$10^{{{k}}}$"


def _decade_range(lo: float, hi: float) -> range:
    lo = max(lo, 1e-300)
    return range(math.floor(math.log10(lo) - 1e-9), math.ceil(math.log10(max(hi, lo)) + 1e-9) + 1)


class Log(Scale):
    """Base-10 logarithmic. Non-positive values are not drawn."""

    name = "log"

    @property
    def code(self) -> str:
        return "log"

    def transform(self, v: float) -> float:
        return math.log10(v) if v > 0 else math.nan

    def inverse(self, t: float) -> float:
        return 10.0**t

    def default_range(self) -> tuple[float, float]:
        return (0.1, 1.0)

    def ticks(self, lo: float, hi: float, max_ticks: int = 7, minus: bool = True) -> list[Tick]:
        lo, hi = min(lo, hi), max(lo, hi)
        lo_e, hi_e = lo * (1 - 1e-9), hi * (1 + 1e-9)
        majors = [k for k in _decade_range(lo, hi) if lo_e <= 10.0**k <= hi_e]
        if len(majors) >= 2:
            step = max(1, math.ceil(len(majors) / max_ticks))
            return [(10.0**k, _pow10(k)) for k in majors[::step]]
        # Under two decades: label the 1-2-5 subdivisions.
        out = [
            (m * 10.0**k, ticker.plain(m * 10.0**k, minus))
            for k in _decade_range(lo, hi)
            for m in (1, 2, 5)
            if lo_e <= m * 10.0**k <= hi_e
        ]
        return out or nice_ticks(lo, hi, max_ticks, minus)

    def minor_ticks(self, lo: float, hi: float) -> list[float]:
        lo, hi = min(lo, hi), max(lo, hi)
        return [
            m * 10.0**k
            for k in _decade_range(lo, hi)
            for m in range(2, 10)
            if lo <= m * 10.0**k <= hi
        ]


class Symlog(Scale):
    """Linear within ``±linthresh`` and logarithmic beyond, so zero and negative
    values can be shown. Choose ``linthresh`` to match the data's small scale."""

    name = "symlog"
    _ADJ = 1.0 / (1.0 - 1.0 / 10.0)

    def __init__(self, linthresh: float = 1.0) -> None:
        if not (math.isfinite(linthresh) and linthresh > 0):
            raise ValueError(f"linthresh must be positive and finite, got {linthresh!r}")
        self.linthresh = float(linthresh)

    @property
    def code(self) -> str:
        return f"symlog:{self.linthresh!r}"

    def transform(self, v: float) -> float:
        t, a = self.linthresh, abs(v)
        if a <= t:
            return v * self._ADJ
        return math.copysign(t * (self._ADJ + math.log10(a / t)), v)

    def inverse(self, t: float) -> float:
        u = t
        t, a = self.linthresh, abs(u)
        if a <= t * self._ADJ:
            return u / self._ADJ
        return math.copysign(t * 10.0 ** (a / t - self._ADJ), u)

    def default_range(self) -> tuple[float, float]:
        return (-self.linthresh, self.linthresh)

    def _decades(self, lo: float, hi: float, mults: Sequence[int]) -> set[float]:
        top = max(abs(lo), abs(hi), self.linthresh)
        ks = range(math.floor(math.log10(self.linthresh)), math.ceil(math.log10(top)) + 1)
        return {
            s * m * 10.0**k
            for s in (1.0, -1.0)
            for k in ks
            for m in mults
            if m * 10.0**k >= self.linthresh and lo <= s * m * 10.0**k <= hi
        }

    def ticks(self, lo: float, hi: float, max_ticks: int = 7, minus: bool = True) -> list[Tick]:
        lo, hi = min(lo, hi), max(lo, hi)
        vals = self._decades(lo, hi, (1,))
        if len(vals) < 2:
            return nice_ticks(lo, hi, max_ticks, minus)
        if len(vals) < max_ticks - 1:
            vals |= self._decades(lo, hi, (1, 2, 5))
        vals |= {v for v in (0.0, self.linthresh, -self.linthresh) if lo <= v <= hi}

        def label(v: float) -> str:
            a = abs(v)
            if v != 0 and (a >= 1000 or a < 1e-3):
                k = round(math.log10(a))
                return f"$-10^{{{k}}}$" if v < 0 else _pow10(k)
            return ticker.plain(v, minus)

        return [(v, label(v)) for v in sorted(vals)]

    def minor_ticks(self, lo: float, hi: float) -> list[float]:
        lo, hi = min(lo, hi), max(lo, hi)
        return sorted(self._decades(lo, hi, range(2, 10)))


class Logit(Scale):
    """``log10(p / (1 - p))`` for probabilities in (0, 1)."""

    name = "logit"

    @property
    def code(self) -> str:
        return "logit"

    def transform(self, v: float) -> float:
        return math.log10(v / (1.0 - v)) if 0.0 < v < 1.0 else math.nan

    def inverse(self, t: float) -> float:
        e = 10.0**t
        return e / (1.0 + e)

    def default_range(self) -> tuple[float, float]:
        return (0.01, 0.99)

    def ticks(self, lo: float, hi: float, max_ticks: int = 7, minus: bool = True) -> list[Tick]:
        lo, hi = min(lo, hi), max(lo, hi)
        std = (0.001, 0.01, 0.1, 0.5, 0.9, 0.99, 0.999)
        return [(v, ticker.plain(v, minus)) for v in std if lo <= v <= hi]

    def minor_ticks(self, lo: float, hi: float) -> list[float]:
        sub = (0.002, 0.005, 0.02, 0.05, 0.2, 0.25, 0.75, 0.8, 0.95, 0.98, 0.995, 0.998)
        return [v for v in sub if min(lo, hi) <= v <= max(lo, hi)]


class Categorical(Scale):
    """Discrete categories at positions 0, 1, 2, ... in first-seen order. Set
    automatically when string data is plotted."""

    name = "categorical"

    def __init__(self, categories: Sequence[str] = ()) -> None:
        self.categories: list[str] = []
        self.index: dict[str, int] = {}
        for c in categories:
            self.position(c)

    def position(self, category: object) -> float:
        key = str(category)
        if key not in self.index:
            self.index[key] = len(self.categories)
            self.categories.append(key)
        return float(self.index[key])

    def fixed_range(self) -> tuple[float, float]:
        return (-0.5, max(len(self.categories), 1) - 0.5)

    def ticks(self, lo: float, hi: float, max_ticks: int = 7, minus: bool = True) -> list[Tick]:
        lo, hi = min(lo, hi), max(lo, hi)
        return [(float(i), c) for i, c in enumerate(self.categories) if lo - 1e-9 <= i <= hi + 1e-9]


# -- dates ------------------------------------------------------------------

_EPOCH = dt.datetime(1970, 1, 1)


def is_datetime(v: object) -> bool:
    return (
        isinstance(v, (dt.datetime, dt.date))
        or hasattr(v, "to_pydatetime")
        or type(v).__name__ == "datetime64"
    )


def date2num(v) -> float:
    """A datetime as float days since 1970-01-01."""
    if hasattr(v, "to_pydatetime"):  # pandas Timestamp
        v = v.to_pydatetime()
    if isinstance(v, dt.datetime):
        if v.tzinfo is not None:
            v = v.astimezone(dt.UTC).replace(tzinfo=None)
        return (v - _EPOCH).total_seconds() / 86400.0
    if isinstance(v, dt.date):
        return float((v - _EPOCH.date()).days)
    if type(v).__name__ == "datetime64":
        import numpy as np

        return float(np.datetime64(v, "us").astype("int64")) / 86400e6
    return float(v)


def num2date(x: float) -> dt.datetime:
    """The inverse of `date2num`."""
    return _EPOCH + dt.timedelta(days=float(x))


def _first_at_least(target: float, options: Sequence[int]) -> int:
    return next((o for o in options if o >= target), options[-1])


def _date_ticks(lo: float, hi: float, max_ticks: int) -> list[Tick]:
    if hi <= lo:
        return [(lo, num2date(lo).strftime("%Y-%m-%d"))]
    span, d0, d1 = hi - lo, num2date(lo), num2date(hi)
    times: list[dt.datetime] = []
    if span > 730:
        step = _first_at_least((d1.year - d0.year) / max_ticks, (1, 2, 5, 10, 20, 50, 100))
        times = [dt.datetime(y, 1, 1) for y in range(d0.year // step * step, d1.year + 2, step)]
        fmt = "%Y"
    elif span > 60:
        step = _first_at_least(span / 30.0 / max_ticks, (1, 2, 3, 6))
        y, m = d0.year, d0.month
        while date2num(dt.datetime(y, m, 1)) <= hi:
            times.append(dt.datetime(y, m, 1))
            y, m = y + (m - 1 + step) // 12, (m - 1 + step) % 12 + 1
        fmt = "%b %Y"
    else:
        if span > 2:
            unit, steps, fmt = 1.0, (1, 2, 5, 10, 15), "%b %d"
            t = d0.replace(hour=0, minute=0, second=0, microsecond=0)
        elif span > 2 / 24:
            unit, steps, fmt = 1 / 24, (1, 2, 3, 6, 12), "%H:%M"
            t = d0.replace(minute=0, second=0, microsecond=0)
        else:
            unit, steps, fmt = 1 / 1440, (1, 5, 10, 15, 30), "%H:%M"
            t = d0.replace(second=0, microsecond=0)
        delta = dt.timedelta(days=unit * _first_at_least(span / unit / max_ticks, steps))
        while date2num(t) <= hi and len(times) < 1000:
            times.append(t)
            t += delta
    return [(date2num(t), t.strftime(fmt)) for t in times if lo - 1e-9 <= date2num(t) <= hi + 1e-9]


class Date(Scale):
    """Time on float day numbers (see `date2num`), ticked on calendar
    boundaries. Set automatically when datetime data is plotted."""

    name = "date"

    def ticks(self, lo: float, hi: float, max_ticks: int = 7, minus: bool = True) -> list[Tick]:
        return _date_ticks(min(lo, hi), max(lo, hi), max_ticks)


_BY_NAME: dict[str, type[Scale]] = {
    "linear": Linear,
    "log": Log,
    "symlog": Symlog,
    "logit": Logit,
    "date": Date,
}


def get(scale: Scale | str) -> Scale:
    """A scale from an instance or a name: linear, log, symlog, logit or date."""
    if isinstance(scale, Scale):
        return scale
    try:
        return _BY_NAME[scale]()
    except (KeyError, TypeError):
        raise ValueError(f"unknown scale {scale!r}; expected one of {sorted(_BY_NAME)}") from None
