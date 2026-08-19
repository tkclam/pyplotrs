"""Tick-label formatters.

A ``Formatter`` turns a tick's numeric position into its label string. Pass
an instance to [`Axes.set`][pyplotrs.axes.Axes.set] via ``xformatter=``/``yformatter=`` (or
to a colorbar); the active [`Scale`][pyplotrs.scales.Scale] locates the tick
*positions* and the formatter decides how each is written. Labels may contain
``$...$`` math (e.g. ``LogFormatter`` emits ``$10^{k}$``), which flows
through the same editable-text pipeline as every other label.

Formatters that render a *number* sign it with ``MINUS`` (see
``fix_minus``). The ones that hand back a string you supplied -
``FixedFormatter``, ``FuncFormatter``, ``StrMethodFormatter``,
``DateFormatter`` - pass it through untouched, so ``"%Y-%m-%d"`` keeps its
hyphens.
"""

from __future__ import annotations

import math
from typing import Callable, ClassVar

from ._util import _auto_repr

__all__ = [
    "Formatter", "ScalarFormatter", "FuncFormatter", "StrMethodFormatter",
    "PercentFormatter", "EngFormatter", "LogFormatter", "FixedFormatter",
    "DateFormatter", "fix_minus", "MINUS",
]

#: U+2212 MINUS SIGN: the sign a negative number is set with. Unlike the ASCII
#: hyphen-minus it is drawn on the math axis and is as wide as ``+`` (and about
#: as wide as a digit), so negative labels line up in a tick column instead of
#: carrying a short, low dash. The math engine already writes every binary minus
#: this way, so plain tick labels using ``-`` would read differently from the
#: ``$10^{-3}$`` labels on a log axis.
MINUS = "−"

_UNICODE_MINUS = True


def fix_minus(s: str) -> str:
    """Replace the sign in a *numeric* label with a real ``MINUS``.

    Only apply this to strings pyplotrs formatted from a number - never to user
    text, category names, or ``strftime`` output, where a hyphen is a hyphen.
    Math (``$...$``) is likewise left alone: the math engine maps ``-`` to
    U+2212 itself, and feeding it a pre-substituted glyph would lose the binary
    operator's spacing. Disabled by [`pyplotrs.set_unicode_minus`][pyplotrs.set_unicode_minus].
    """
    return s.replace("-", MINUS) if _UNICODE_MINUS else s


def _fmt_g(value: float) -> str:
    """A compact number: integers without a trailing ``.0``, else ``%g``.

    ASCII-signed - callers that emit the result as plain text pass it through
    ``fix_minus``; callers that embed it in math must not.
    """
    if value == int(value) and abs(value) < 1e16:
        return str(int(value))
    return f"{value:g}"


class Formatter:
    """Base formatter: subclasses implement ``__call__``. Calling a formatter
    with a tick value (and optional integer position) returns its label."""

    def __repr__(self) -> str:
        return _auto_repr(self)


    def __call__(self, value: float, pos: int | None = None) -> str:
        return fix_minus(_fmt_g(value))

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
                m = _fmt_g(round(mant, 6))  # math: the engine signs it itself
                return f"${m}\\times10^{{{exp}}}$" if m != "1" else f"$10^{{{exp}}}$"
        return fix_minus(_fmt_g(value))


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
        return f"{fix_minus(s)}{self.symbol}"


class EngFormatter(Formatter):
    """Engineering notation: scale by a power of 1000 and append an SI prefix
    (``k``, ``M``, ``m``, ``µ`` …), then ``unit``."""

    #: Shared lookup, not per-instance state - `ClassVar` says so, and keeps a
    #: type checker from reading it as a mutable default on every instance.
    _PREFIX: ClassVar[dict[int, str]] = {
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
        return f"{fix_minus(m)}{tail}"


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
        return fix_minus(_fmt_g(value)) if self.label_minor else ""


class DateFormatter(Formatter):
    """Format a day-number tick (see [`pyplotrs.scales.date2num`][pyplotrs.scales.date2num]) with a
    ``strftime`` pattern, e.g. ``DateFormatter("%Y-%m")``."""

    def __init__(self, fmt: str = "%Y-%m-%d") -> None:
        self.fmt = fmt

    def __call__(self, value: float, pos: int | None = None) -> str:
        from . import scales as _scales
        return _scales.num2date(value).strftime(self.fmt)


def get(formatter):
    """Resolve a formatter argument: a ``Formatter``, a ``str`` format
    template (``"{x:.2f}"``), a callable, or ``None``."""
    if formatter is None or isinstance(formatter, Formatter):
        return formatter
    if isinstance(formatter, str):
        return StrMethodFormatter(formatter)
    if callable(formatter):
        return FuncFormatter(formatter)
    raise TypeError(f"expected a Formatter, format string, callable, or None; "
                    f"got {type(formatter).__name__}")


# -- shared offset / multiplier ---------------------------------------------

#: Extra decimal digits a tick label may carry before an axis is better served
#: by factoring a common term out of every label. Four is the point at which
#: "0.0000002" and "1000000.05" stop being readable as numbers.
_OFFSET_DIGITS = 4

#: Decade range left as plain decimals. Outside it, a common power of ten is
#: factored out into the axis' corner text. Matches ``ScalarFormatter``'s
#: default ``power_limits``.
_POWER_LIMITS = (-5, 6)


def _decade(v: float) -> int:
    """``floor(log10(|v|))``, and 0 for a value with no magnitude to speak of."""
    v = abs(v)
    if v == 0.0 or not math.isfinite(v):
        return 0
    return int(math.floor(math.log10(v)))


def factor_out(values) -> tuple[float, int]:
    """A shared ``(offset, exponent)`` to lift out of a set of tick values.

    Returns the additive offset and the power of ten that, removed from every
    tick, leave labels a reader can take in at a glance. ``(0.0, 0)`` means
    leave them alone, which is the answer for any ordinary axis.

    Two independent decisions:

    * **Offset** - when the ticks are crowded far from zero, so that almost
      every digit printed is the same on every label. ``1000000.00``,
      ``1000000.05``, ``1000000.10`` carry two digits of information and eight
      of noise; factoring out ``1000000`` leaves ``0.00 0.05 0.10`` and puts
      the constant in the corner once.
    * **Exponent** - when what remains is very large or very small, so the
      labels would be a run of zeros either way.

    This is what an axis has always needed and never had. Its absence is why a
    nanometre axis could only be labelled by printing ten decimal places, and
    why a long tick label ran off the page instead of being short.
    """
    vals = [float(v) for v in values if math.isfinite(v)]
    if len(vals) < 2:
        return 0.0, 0
    lo, hi = min(vals), max(vals)
    span = hi - lo
    if span <= 0.0:
        return 0.0, 0

    offset = 0.0
    # An offset only helps when every tick sits on the same side of zero: a set
    # straddling zero already has zero as its natural reference, and shifting
    # it would make the labels harder to read, not easier.
    if lo > 0.0 or hi < 0.0:
        span_dec = _decade(span)
        far_dec = _decade(max(abs(lo), abs(hi)))
        if far_dec - span_dec >= _OFFSET_DIGITS:
            # Round the offset itself to the span's own decade, so the corner
            # text is a round number and the residual labels stay small.
            step = 10.0 ** (span_dec + 1)
            offset = math.floor(lo / step) * step

    residual = max(abs(lo - offset), abs(hi - offset))
    exponent = _decade(residual)
    if _POWER_LIMITS[0] <= exponent < _POWER_LIMITS[1]:
        exponent = 0
    return offset, exponent


def offset_label(offset: float, exponent: int) -> str:
    """The corner text for a ``(offset, exponent)`` pair, or ``""`` for none.

    Written as math so the exponent is a real superscript and shares the
    typesetting of a ``$10^{-9}$`` log label. The sign of the offset is
    explicit - a reader has to know whether to add or subtract it.
    """
    parts = []
    if exponent:
        parts.append(f"$\\times10^{{{exponent}}}$")
    if offset:
        sign = "+" if offset > 0 else MINUS
        mag = abs(offset)
        dec = _decade(mag)
        if _POWER_LIMITS[0] <= dec < _POWER_LIMITS[1]:
            parts.append(f"{sign}{_fmt_g(mag)}")
        else:
            mant = mag / (10.0 ** dec)
            m = _fmt_g(round(mant, 6))
            body = f"10^{{{dec}}}" if m == "1" else f"{m}\\times10^{{{dec}}}"
            parts.append(f"${sign}{body}$")
    return " ".join(parts)


def apply_offset(values, offset: float, exponent: int) -> list[str]:
    """Label ``values`` with ``offset`` and ``10**exponent`` already removed.

    The residuals share a decimal place count, chosen from the *step* between
    them, so the column lines up the way a table of numbers should.
    """
    scale = 10.0 ** exponent
    res = [(float(v) - offset) / scale for v in values]
    if len(res) >= 2:
        steps = [abs(b - a) for a, b in zip(res, res[1:]) if b != a]
        step = min(steps) if steps else 0.0
    else:
        step = 0.0
    decimals = 0
    if step > 0.0:
        # Enough places to tell one tick from the next, and no more.
        decimals = max(0, -_decade(step))
        if round(step, decimals) == 0.0:
            decimals += 1
    out = []
    for v in res:
        s = f"{v:.{decimals}f}"
        if s.startswith("-") and all(c in "0." for c in s[1:]):
            s = s[1:]  # no "-0.00"
        out.append(fix_minus(s))
    return out
