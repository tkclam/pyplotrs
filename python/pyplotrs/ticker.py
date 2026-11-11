"""Tick label formatters.

Anything that turns a number into a label works as a formatter:

* a format string: ``"{x:.1f} ms"``
* any callable: ``lambda v: f"{v / 1000:g}k"``
* one of the classes here: ``Percent()``, ``Eng("Hz")``, ``Scientific()``,
  ``Date("%b %Y")``.

Labels may contain ``$...$`` math.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from typing import ClassVar

__all__ = ["MINUS", "Date", "Eng", "Formatter", "Percent", "Scientific", "get"]

MINUS = "−"

FormatterLike = str | Callable[[float], str]


def fix_minus(s: str, minus: bool = True) -> str:
    """Sign a numeric label with U+2212 rather than a hyphen."""
    return s.replace("-", MINUS) if minus else s


def compact(v: float) -> str:
    """An integer without ``.0``, otherwise ``%g``. ASCII-signed."""
    return str(int(v)) if v == int(v) and abs(v) < 1e16 else f"{v:g}"


def plain(v: float, minus: bool = True) -> str:
    """A tick value without an exponent, trailing zeros trimmed."""
    if math.isfinite(v) and v == int(v) and abs(v) < 1e16:
        return fix_minus(str(int(v)), minus)
    if math.isfinite(v) and 0.0 < abs(v) < 1e-10:
        k = math.floor(math.log10(abs(v)))
        m = f"{v / 10.0**k:.6f}".rstrip("0").rstrip(".")
        return f"$10^{{{k}}}$" if m == "1" else f"${m}\\times10^{{{k}}}$"
    s = f"{v:.10f}".rstrip("0").rstrip(".")
    return fix_minus(s, minus) if s else "0"


class Formatter:
    """Base class for the built-in formatters."""

    def __call__(self, value: float, minus: bool = True) -> str:
        return fix_minus(compact(value), minus)

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in vars(self).items())
        return f"{type(self).__name__}({args})"


class Template(Formatter):
    """``fmt.format(x=value)``, e.g. ``"{x:.2f}"``."""

    def __init__(self, fmt: str) -> None:
        self.fmt = fmt

    def __call__(self, value: float, minus: bool = True) -> str:
        return self.fmt.format(value, x=value)


class Scientific(Formatter):
    """Values outside ``10**lo .. 10**hi`` as ``m × 10^k``."""

    def __init__(self, limits: tuple[int, int] = (-3, 4)) -> None:
        self.limits = limits

    def __call__(self, value: float, minus: bool = True) -> str:
        if value == 0 or not math.isfinite(value):
            return fix_minus(compact(value), minus)
        k = math.floor(math.log10(abs(value)))
        if self.limits[0] <= k < self.limits[1]:
            return fix_minus(compact(value), minus)
        m = compact(round(value / 10.0**k, 6))
        return f"$10^{{{k}}}$" if m == "1" else f"${m}\\times10^{{{k}}}$"


class Percent(Formatter):
    """``value / xmax`` as a percentage."""

    def __init__(self, xmax: float = 1.0, decimals: int | None = None, symbol: str = "%") -> None:
        self.xmax, self.decimals, self.symbol = float(xmax), decimals, symbol

    def __call__(self, value: float, minus: bool = True) -> str:
        pct = value / self.xmax * 100.0
        s = compact(round(pct, 3)) if self.decimals is None else f"{pct:.{self.decimals}f}"
        return fix_minus(s, minus) + self.symbol


class Eng(Formatter):
    """Engineering notation with an SI prefix: ``1.5 kHz``, ``20 µs``."""

    _PREFIXES: ClassVar[dict[int, str]] = {
        -8: "y",
        -7: "z",
        -6: "a",
        -5: "f",
        -4: "p",
        -3: "n",
        -2: "µ",
        -1: "m",
        0: "",
        1: "k",
        2: "M",
        3: "G",
        4: "T",
        5: "P",
        6: "E",
        7: "Z",
        8: "Y",
    }

    def __init__(self, unit: str = "", places: int | None = None, sep: str = " ") -> None:
        self.unit, self.places, self.sep = unit, places, sep

    def __call__(self, value: float, minus: bool = True) -> str:
        e = 0 if value == 0 else max(-8, min(8, math.floor(math.log10(abs(value)) / 3)))
        mant = value / 10.0 ** (3 * e)
        m = compact(round(mant, 6)) if self.places is None else f"{mant:.{self.places}f}"
        suffix = self._PREFIXES[e] + self.unit
        return fix_minus(m, minus) + (self.sep + suffix if suffix else "")


class Date(Formatter):
    """A day-number tick (see `pyplotrs.scales.date2num`) via ``strftime``."""

    def __init__(self, fmt: str = "%Y-%m-%d") -> None:
        self.fmt = fmt

    def __call__(self, value: float, minus: bool = True) -> str:
        from .scales import num2date

        return num2date(value).strftime(self.fmt)


def get(formatter: FormatterLike | None) -> Callable[..., str] | None:
    """A formatter from a format string, a callable, or ``None``."""
    if formatter is None or callable(formatter):
        return formatter
    if isinstance(formatter, str):
        return Template(formatter)
    raise TypeError(f"expected a format string or callable, got {type(formatter).__name__}")


def format_ticks(formatter: Callable[..., str], values: list[float], minus: bool) -> list[str]:
    if isinstance(formatter, Formatter):
        return [formatter(v, minus) for v in values]
    return [str(formatter(v)) for v in values]


# -- shared offset / multiplier ------------------------------------------------
#
# Ticks crowded far from zero (1000000.00, 1000000.05, ...) or very large/small
# are labeled relative to a shared term written once at the end of the axis.

_OFFSET_DIGITS = 4
_POWER_LIMITS = (-5, 6)


def _decade(v: float) -> int:
    v = abs(v)
    return math.floor(math.log10(v)) if v > 0 and math.isfinite(v) else 0


def factor_out(values: list[float]) -> tuple[float, int]:
    """A shared ``(offset, exponent)`` to lift out of tick values; ``(0, 0)`` for none."""
    vals = [v for v in values if math.isfinite(v)]
    if len(vals) < 2 or max(vals) == min(vals):
        return 0.0, 0
    lo, hi = min(vals), max(vals)
    offset = 0.0
    if (lo > 0 or hi < 0) and _decade(max(abs(lo), abs(hi))) - _decade(hi - lo) >= _OFFSET_DIGITS:
        step = 10.0 ** (_decade(hi - lo) + 1)
        offset = math.floor(lo / step) * step
    exponent = _decade(max(abs(lo - offset), abs(hi - offset)))
    if _POWER_LIMITS[0] <= exponent < _POWER_LIMITS[1]:
        exponent = 0
    return offset, exponent


def offset_text(offset: float, exponent: int, minus: bool = True) -> str:
    """The corner label for a shared offset/exponent."""
    parts = []
    if exponent:
        parts.append(f"$\\times10^{{{exponent}}}$")
    if offset:
        sign = "+" if offset > 0 else (MINUS if minus else "-")
        k = _decade(offset)
        if _POWER_LIMITS[0] <= k < _POWER_LIMITS[1]:
            parts.append(sign + compact(abs(offset)))
        else:
            m = compact(round(abs(offset) / 10.0**k, 6))
            body = f"10^{{{k}}}" if m == "1" else f"{m}\\times10^{{{k}}}"
            parts.append(f"${sign}{body}$")
    return " ".join(parts)


def relative_labels(
    values: list[float], offset: float, exponent: int, minus: bool = True
) -> list[str]:
    """Labels for ``values`` with the offset and exponent removed, sharing one
    number of decimal places."""
    scale = 10.0**exponent
    res = [(v - offset) / scale for v in values]
    steps = [abs(b - a) for a, b in itertools.pairwise(res) if b != a]
    places = 0
    if steps:
        step = min(steps)
        places = max(0, -_decade(step))
        if round(step, places) == 0.0:
            places += 1
    out = []
    for v in res:
        s = f"{v:.{places}f}"
        if s.startswith("-") and set(s[1:]) <= {"0", "."}:
            s = s[1:]
        out.append(fix_minus(s, minus))
    return out
