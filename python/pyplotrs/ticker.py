"""Tick-label formatters.

A :class:`Formatter` turns a tick's numeric position into its label string. Pass
an instance to :meth:`pyplotrs.Axes.set` via ``xformatter=``/``yformatter=`` (or
to a colorbar); the active :class:`~pyplotrs.scales.Scale` locates the tick
*positions* and the formatter decides how each is written. Labels may contain
``$...$`` math (e.g. :class:`LogFormatter` emits ``$10^{k}$``), which flows
through the same editable-text pipeline as every other label.
"""

from __future__ import annotations

import math
from typing import Callable

__all__ = [
    "Formatter", "ScalarFormatter", "FuncFormatter", "StrMethodFormatter",
    "PercentFormatter", "EngFormatter", "LogFormatter", "FixedFormatter",
    "DateFormatter",
]


def _fmt_g(value: float) -> str:
    """A compact number: integers without a trailing ``.0``, else ``%g``."""
    if value == int(value) and abs(value) < 1e16:
        return str(int(value))
    return f"{value:g}"


class Formatter:
    """Base formatter: subclasses implement :meth:`__call__`. Calling a formatter
    with a tick value (and optional integer position) returns its label."""

    def __call__(self, value: float, pos: int | None = None) -> str:
        return _fmt_g(value)

    def format_ticks(self, values) -> list[str]:
        """Label a whole sequence of tick positions (some formatters use the set,
        e.g. to choose a shared offset/exponent)."""
        return [self(v, i) for i, v in enumerate(values)]


class ScalarFormatter(Formatter):
    """Plain decimal formatting. With ``scientific=True`` values outside
    ``10**-power_limits[0] .. 10**power_limits[1]`` render in ``$m×10^{k}$``
    mantissa/exponent form."""

    def __init__(self, scientific: bool = False,
                 power_limits: tuple[int, int] = (-5, 6)) -> None:
        self.scientific = scientific
        self.power_limits = power_limits

    def __call__(self, value: float, pos: int | None = None) -> str:
        if value == 0:
            return "0"
        if self.scientific:
            exp = math.floor(math.log10(abs(value)))
            if exp < self.power_limits[0] or exp >= self.power_limits[1]:
                mant = value / (10.0 ** exp)
                m = _fmt_g(round(mant, 6))
                return f"${m}\\times10^{{{exp}}}$" if m != "1" else f"$10^{{{exp}}}$"
        return _fmt_g(value)


class FixedFormatter(Formatter):
    """Return labels from a fixed list by tick index (a fallback ``""`` past the
    end). Used to back ``set(xticklabels=...)``."""

    def __init__(self, labels) -> None:
        self.labels = [str(s) for s in labels]

    def __call__(self, value: float, pos: int | None = None) -> str:
        if pos is not None and 0 <= pos < len(self.labels):
            return self.labels[pos]
        return ""


class FuncFormatter(Formatter):
    """Delegate to ``func(value, pos)`` (or ``func(value)``)."""

    def __init__(self, func: Callable) -> None:
        self.func = func

    def __call__(self, value: float, pos: int | None = None) -> str:
        try:
            return str(self.func(value, pos))
        except TypeError:
            return str(self.func(value))


class StrMethodFormatter(Formatter):
    """Format via ``fmt.format(x=value, pos=pos)`` (e.g. ``"{x:.2f}"``)."""

    def __init__(self, fmt: str) -> None:
        self.fmt = fmt

    def __call__(self, value: float, pos: int | None = None) -> str:
        return self.fmt.format(value, x=value, pos=pos)


class PercentFormatter(Formatter):
    """Format as a percentage: ``value / xmax * 100`` with ``symbol`` appended.
    ``decimals=None`` auto-picks a sensible precision."""

    def __init__(self, xmax: float = 1.0, decimals: int | None = None,
                 symbol: str = "%") -> None:
        self.xmax = float(xmax)
        self.decimals = decimals
        self.symbol = symbol

    def __call__(self, value: float, pos: int | None = None) -> str:
        pct = value / self.xmax * 100.0
        if self.decimals is None:
            s = _fmt_g(round(pct, 3))
        else:
            s = f"{pct:.{self.decimals}f}"
        return f"{s}{self.symbol}"


class EngFormatter(Formatter):
    """Engineering notation: scale by a power of 1000 and append an SI prefix
    (``k``, ``M``, ``m``, ``µ`` …), then ``unit``."""

    _PREFIX = {
        -8: "y", -7: "z", -6: "a", -5: "f", -4: "p", -3: "n", -2: "µ", -1: "m",
        0: "", 1: "k", 2: "M", 3: "G", 4: "T", 5: "P", 6: "E", 7: "Z", 8: "Y",
    }

    def __init__(self, unit: str = "", places: int | None = None,
                 sep: str = " ") -> None:
        self.unit = unit
        self.places = places
        self.sep = sep

    def __call__(self, value: float, pos: int | None = None) -> str:
        if value == 0:
            exp3 = 0
        else:
            exp3 = int(math.floor(math.log10(abs(value)) / 3.0))
        exp3 = max(-8, min(8, exp3))
        mant = value / (10.0 ** (3 * exp3))
        if self.places is None:
            m = _fmt_g(round(mant, 6))
        else:
            m = f"{mant:.{self.places}f}"
        prefix = self._PREFIX[exp3]
        tail = f"{self.sep}{prefix}{self.unit}" if (prefix or self.unit) else ""
        return f"{m}{tail}"


class LogFormatter(Formatter):
    """Label decades as ``$10^{k}$`` math; non-decade ticks get ``""`` (unless
    ``label_minor`` is set, which writes them plainly)."""

    def __init__(self, base: float = 10.0, label_minor: bool = False) -> None:
        self.base = base
        self.label_minor = label_minor

    def __call__(self, value: float, pos: int | None = None) -> str:
        if value <= 0:
            return ""
        exp = math.log(value, self.base)
        rexp = round(exp)
        if abs(exp - rexp) < 1e-6:
            return f"$10^{{{rexp}}}$" if self.base == 10.0 else f"${_fmt_g(self.base)}^{{{rexp}}}$"
        return _fmt_g(value) if self.label_minor else ""


class DateFormatter(Formatter):
    """Format a day-number tick (see :func:`pyplotrs.scales.date2num`) with a
    :func:`~datetime.datetime.strftime` pattern, e.g. ``DateFormatter("%Y-%m")``."""

    def __init__(self, fmt: str = "%Y-%m-%d") -> None:
        self.fmt = fmt

    def __call__(self, value: float, pos: int | None = None) -> str:
        from . import scales as _scales
        return _scales.num2date(value).strftime(self.fmt)


def get(formatter):
    """Resolve a formatter argument: a :class:`Formatter`, a ``str`` format
    template (``"{x:.2f}"``), a callable, or ``None``."""
    if formatter is None or isinstance(formatter, Formatter):
        return formatter
    if isinstance(formatter, str):
        return StrMethodFormatter(formatter)
    if callable(formatter):
        return FuncFormatter(formatter)
    raise TypeError(f"expected a Formatter, format string, callable, or None; "
                    f"got {type(formatter).__name__}")
