"""Axis scales: the data-space -> transformed-space mapping that sits between
raw data and the device transform.

A :class:`Scale` owns three things an axis needs: a monotonic ``transform`` (and
its ``inverse``) used to position data, a tick *locator+formatter* (``ticks``),
and an optional set of ``minor_ticks``. The figure draws marks by composing the
scale transform with an affine device map, so the Rust fast paths stay valid:
they only ever see an affine map over *transformed* space (see
``Axes._draw``/``_draw_mark`` in :mod:`pyplotrs.figure`).

:class:`LinearScale` is the default and is bit-for-bit identical to the previous
linear-only behavior (its ``transform`` is the identity and its ``ticks`` defer
to the Rust ``nice_ticks`` locator). Nonlinear scales (log, symlog, ...) override
``transform``/``inverse``/``ticks`` and set ``is_identity = False`` so the figure
knows to pre-transform mark coordinates before the affine fast path.
"""

from __future__ import annotations

import math
from typing import Sequence

from . import _pyplotrs_core as _core
from .ticker import fix_minus

Tick = tuple[float, str]

# Symlog parameters — must stay numerically identical to the Rust constants in
# ``apply_scale`` (crates/pyplotrs-py/src/lib.rs).
_SYMLOG_LINTHRESH = 1.0
_SYMLOG_LINSCALE_ADJ = 1.0 / (1.0 - 1.0 / 10.0)
_LN10 = math.log(10.0)


def nice_ticks(lo: float, hi: float, max_ticks: int) -> list[Tick]:
    """The Rust "nice numbers" auto-locator, signed for display.

    Every caller of the locator goes through here rather than
    ``_core.nice_ticks``: the Rust side formats with an ASCII hyphen (it is a
    pure function with no view of the display setting) and this is where that
    becomes a real :data:`~pyplotrs.ticker.MINUS`. Doing it before the labels
    reach the layout engine keeps the pre-measured extents honest - a minus is
    nearly twice the width of a hyphen.
    """
    return [(v, fix_minus(s)) for v, s in _core.nice_ticks(lo, hi, max_ticks)]


class Scale:
    """Base axis scale. Subclasses override ``transform``/``inverse``/``ticks``.

    ``is_identity`` is a fast-path flag: when ``True`` the figure may skip the
    per-point ``transform`` pass entirely (the device map is already affine in
    data space), preserving the Rust polyline/marker fast paths. ``code`` names
    the transform for the Rust fast paths (``add_line_xform``/
    ``add_markers_xform``), which apply it per point in Rust — see
    ``apply_scale`` in ``crates/pyplotrs-py/src/lib.rs``.
    """

    #: Human-readable scale name, mirroring matplotlib's ``set_xscale`` strings.
    name = "scale"
    #: Rust ``apply_scale`` selector. Must equal a branch handled there.
    code = "linear"
    #: Whether ``transform`` is the identity (lets the figure skip transforming).
    is_identity = False

    def transform(self, v: float) -> float:
        return v

    def inverse(self, t: float) -> float:
        return t

    def data_limits(self, values: Sequence[float]) -> tuple[float, float]:
        """Padded ``(lo, hi)`` view limits, in *data* space, for finite data on
        this scale. Only consulted for non-linear scales (the linear path keeps
        the figure's existing mark-aware autoscaling). Default: linear pad."""
        finite = [v for v in values if math.isfinite(v)]
        if not finite:
            return (0.0, 1.0)
        lo, hi = min(finite), max(finite)
        if lo == hi:
            lo, hi = lo - 0.5, hi + 0.5
        span = hi - lo
        return (lo - span * 0.05, hi + span * 0.05)

    def ticks(self, lo: float, hi: float, max_ticks: int) -> list[Tick]:
        """Major ticks as ``(value, label)`` pairs, value in *data* space."""
        raise NotImplementedError

    def minor_ticks(self, lo: float, hi: float) -> list[float]:
        """Minor-tick *values* (data space). Default: none."""
        return []


class LinearScale(Scale):
    """The default linear scale: identity transform, ``nice_ticks`` locator."""

    name = "linear"
    code = "linear"
    is_identity = True

    def transform(self, v: float) -> float:
        return v

    def inverse(self, t: float) -> float:
        return t

    def ticks(self, lo: float, hi: float, max_ticks: int = 7) -> list[Tick]:
        return nice_ticks(lo, hi, max_ticks)


def _fmt_plain(v: float) -> str:
    """Format a tick value without an exponent, trimming trailing zeros
    (e.g. ``2.0 -> "2"``, ``0.005 -> "0.005"``, ``-3.0 -> "−3"``)."""
    if v == int(v) and abs(v) < 1e16:
        return fix_minus(str(int(v)))
    s = f"{v:.10f}".rstrip("0").rstrip(".")
    return fix_minus(s) if s else "0"


def _fmt_pow10(k: int) -> str:
    """A power-of-ten tick label as mathtext (rendered as ``10`` with a real
    superscript by the math engine)."""
    return f"$10^{{{k}}}$"


class LogScale(Scale):
    """Base-10 logarithmic scale. Non-positive data is dropped (becomes a gap),
    matching matplotlib; the per-point transform runs in Rust."""

    name = "log"
    code = "log"
    is_identity = False

    def transform(self, v: float) -> float:
        return math.log10(v) if v > 0 else -math.inf

    def inverse(self, t: float) -> float:
        return 10.0 ** t

    def data_limits(self, values: Sequence[float]) -> tuple[float, float]:
        pos = [v for v in values if v > 0 and math.isfinite(v)]
        if not pos:
            return (0.1, 1.0)
        lo, hi = min(pos), max(pos)
        llo, lhi = math.log10(lo), math.log10(hi)
        if llo == lhi:
            llo, lhi = llo - 0.5, lhi + 0.5
        pad = (lhi - llo) * 0.05
        return (10.0 ** (llo - pad), 10.0 ** (lhi + pad))

    def ticks(self, lo: float, hi: float, max_ticks: int = 7) -> list[Tick]:
        lo = max(lo, 1e-300)
        if hi <= lo:
            return [(lo, _fmt_plain(lo))]
        k0 = math.floor(math.log10(lo) - 1e-9)
        k1 = math.ceil(math.log10(hi) + 1e-9)
        lo_e, hi_e = lo * (1 - 1e-9), hi * (1 + 1e-9)
        majors = [k for k in range(k0, k1 + 1) if lo_e <= 10.0 ** k <= hi_e]
        if len(majors) >= 2:
            step = max(1, math.ceil(len(majors) / max_ticks))
            return [(10.0 ** k, _fmt_pow10(k)) for k in majors[::step]]
        # Narrow span (<2 decades): label the 1-2-3-5 subdivisions in range.
        out: list[Tick] = []
        for k in range(k0, k1 + 1):
            for mult in (1, 2, 3, 5):
                v = mult * 10.0 ** k
                if lo_e <= v <= hi_e:
                    out.append((v, _fmt_plain(v)))
        return out or [(lo, _fmt_plain(lo)), (hi, _fmt_plain(hi))]

    def minor_ticks(self, lo: float, hi: float) -> list[float]:
        lo = max(lo, 1e-300)
        if hi <= lo:
            return []
        k0 = math.floor(math.log10(lo) - 1e-9)
        k1 = math.ceil(math.log10(hi) + 1e-9)
        out: list[float] = []
        for k in range(k0, k1 + 1):
            for mult in range(2, 10):
                v = mult * 10.0 ** k
                if lo <= v <= hi:
                    out.append(v)
        return out


class SymlogScale(Scale):
    """Symmetric log: linear within ``[-1, 1]`` (linthresh) and logarithmic
    beyond, so zero and negative values are representable."""

    name = "symlog"
    code = "symlog"
    is_identity = False

    def transform(self, v: float) -> float:
        a = abs(v)
        if a <= _SYMLOG_LINTHRESH:
            return v * _SYMLOG_LINSCALE_ADJ
        return math.copysign(1.0, v) * _SYMLOG_LINTHRESH * (
            _SYMLOG_LINSCALE_ADJ + math.log(a / _SYMLOG_LINTHRESH) / _LN10
        )

    def inverse(self, t: float) -> float:
        a = abs(t)
        lin_edge = _SYMLOG_LINTHRESH * _SYMLOG_LINSCALE_ADJ
        if a <= lin_edge:
            return t / _SYMLOG_LINSCALE_ADJ
        return math.copysign(1.0, t) * _SYMLOG_LINTHRESH * 10.0 ** (
            a / _SYMLOG_LINTHRESH - _SYMLOG_LINSCALE_ADJ
        )

    def data_limits(self, values: Sequence[float]) -> tuple[float, float]:
        finite = [v for v in values if math.isfinite(v)]
        if not finite:
            return (-1.0, 1.0)
        lo, hi = min(finite), max(finite)
        tlo, thi = self.transform(lo), self.transform(hi)
        if tlo == thi:
            tlo, thi = tlo - 0.5, thi + 0.5
        pad = (thi - tlo) * 0.05
        return (self.inverse(tlo - pad), self.inverse(thi + pad))

    def ticks(self, lo: float, hi: float, max_ticks: int = 7) -> list[Tick]:
        vals: set[float] = set()
        if lo <= 0.0 <= hi:
            vals.add(0.0)
        for sign in (1.0, -1.0):
            for k in range(-10, 11):
                v = sign * 10.0 ** k
                if abs(v) >= _SYMLOG_LINTHRESH and lo <= v <= hi:
                    vals.add(v)
        if len(vals) < 2:
            return nice_ticks(lo, hi, max_ticks)
        ordered = sorted(vals)
        return [(v, _fmt_symlog(v)) for v in ordered]


def _fmt_symlog(v: float) -> str:
    if v == 0.0:
        return "0"
    a = abs(v)
    if a >= 1000 or a < 1e-3:
        k = round(math.log10(a))
        return ("$-10^{%d}$" % k) if v < 0 else _fmt_pow10(k)
    return _fmt_plain(v)


class LogitScale(Scale):
    """Logit scale for probabilities in ``(0, 1)``: ``log10(p / (1 - p))``."""

    name = "logit"
    code = "logit"
    is_identity = False

    def transform(self, v: float) -> float:
        return math.log10(v / (1.0 - v)) if 0.0 < v < 1.0 else math.copysign(math.inf, v - 0.5)

    def inverse(self, t: float) -> float:
        e = 10.0 ** t
        return e / (1.0 + e)

    def data_limits(self, values: Sequence[float]) -> tuple[float, float]:
        inside = [v for v in values if 0.0 < v < 1.0 and math.isfinite(v)]
        if not inside:
            return (0.01, 0.99)
        lo, hi = min(inside), max(inside)
        tlo, thi = self.transform(lo), self.transform(hi)
        if tlo == thi:
            tlo, thi = tlo - 0.5, thi + 0.5
        pad = (thi - tlo) * 0.05
        return (self.inverse(tlo - pad), self.inverse(thi + pad))

    def ticks(self, lo: float, hi: float, max_ticks: int = 7) -> list[Tick]:
        # Conventional logit gridline positions, symmetric about 0.5; kept sparse
        # so labels don't collide in the compressed mid-range.
        std = [0.001, 0.01, 0.1, 0.5, 0.9, 0.99, 0.999]
        return [(v, _fmt_plain(v)) for v in std if lo <= v <= hi]

    def minor_ticks(self, lo: float, hi: float) -> list[float]:
        sub = [0.002, 0.005, 0.02, 0.05, 0.2, 0.25, 0.75, 0.8, 0.95, 0.98, 0.995, 0.998]
        return [v for v in sub if lo <= v <= hi]


class CategoricalScale(Scale):
    """A discrete axis: string categories occupy integer positions ``0..n-1``.

    Data are mapped to their category index before plotting (see
    ``Axes._categorize``); the transform is the identity in that index space, so
    the Rust affine fast paths are untouched (``code = "linear"``). Ticks are one
    per category, centered on its position; the view spans ``-0.5 .. n-0.5``."""

    name = "categorical"
    code = "linear"
    is_identity = False  # so the figure uses ``data_limits`` for the view range

    def __init__(self, categories: Sequence) -> None:
        self.categories = [str(c) for c in categories]
        self.index = {c: i for i, c in enumerate(self.categories)}

    def transform(self, v: float) -> float:
        return v

    def inverse(self, t: float) -> float:
        return t

    def data_limits(self, values: Sequence[float]) -> tuple[float, float]:
        n = len(self.categories)
        return (-0.5, (n - 1) + 0.5) if n else (-0.5, 0.5)

    def ticks(self, lo: float, hi: float, max_ticks: int = 7) -> list[Tick]:
        return [(float(i), c) for i, c in enumerate(self.categories)
                if lo - 1e-9 <= i <= hi + 1e-9]


# -- datetime axis ----------------------------------------------------------

import datetime as _dt

#: Epoch for pyplotrs' day-number convention (float days since this instant).
_EPOCH = _dt.datetime(1970, 1, 1)


def is_datetime_like(v) -> bool:
    """Whether ``v`` is a datetime we can place on a :class:`DateScale`
    (``datetime``/``date``, pandas ``Timestamp``, or NumPy ``datetime64``)."""
    if isinstance(v, (_dt.datetime, _dt.date)):
        return True
    if hasattr(v, "to_pydatetime"):  # pandas Timestamp
        return True
    return type(v).__name__ == "datetime64"  # numpy


def date2num(v) -> float:
    """Convert a datetime-like value to float **days since 1970-01-01**."""
    if isinstance(v, _dt.datetime):
        return (v - _EPOCH).total_seconds() / 86400.0
    if isinstance(v, _dt.date):
        return (_dt.datetime(v.year, v.month, v.day) - _EPOCH).total_seconds() / 86400.0
    if hasattr(v, "to_pydatetime"):  # pandas Timestamp
        return date2num(v.to_pydatetime())
    if type(v).__name__ == "datetime64":  # numpy datetime64
        import numpy as _np  # local: numpy is optional
        ns = _np.datetime64(v, "ns").astype("int64")
        return ns / 1e9 / 86400.0
    return float(v)


def num2date(x: float) -> _dt.datetime:
    """Inverse of :func:`date2num`: a float day-number back to a ``datetime``."""
    return _EPOCH + _dt.timedelta(days=float(x))


def _nice_step(target: float, options: Sequence[int]) -> int:
    for o in options:
        if o >= target:
            return o
    return options[-1]


def _date_ticks(lo: float, hi: float, max_ticks: int) -> list[Tick]:
    """An auto date locator: pick a year/month/day/hour/minute granularity from
    the visible span and emit calendar-aligned ``(day_number, label)`` ticks."""
    if hi <= lo:
        return [(lo, num2date(lo).strftime("%Y-%m-%d"))]
    span = hi - lo
    d0, d1 = num2date(lo), num2date(hi)
    out: list[_dt.datetime] = []
    if span > 365 * 2:  # years
        step = _nice_step((d1.year - d0.year) / max_ticks, [1, 2, 5, 10, 20, 50, 100])
        y = (d0.year // step) * step
        while y <= d1.year + 1:
            out.append(_dt.datetime(y, 1, 1))
            y += step
        fmt = "%Y"
    elif span > 60:  # months
        step = _nice_step(span / 30.0 / max_ticks, [1, 2, 3, 6])
        y, m = d0.year, d0.month
        for _ in range(400):
            t = _dt.datetime(y, m, 1)
            if date2num(t) > hi + 31:
                break
            out.append(t)
            m += step
            while m > 12:
                m -= 12
                y += 1
        fmt = "%b %Y"
    elif span > 2:  # days
        step = _nice_step(span / max_ticks, [1, 2, 5, 10, 15])
        t = _dt.datetime(d0.year, d0.month, d0.day)
        for _ in range(2000):
            if date2num(t) > hi:
                break
            out.append(t)
            t += _dt.timedelta(days=step)
        fmt = "%b %d"
    elif span > 2.0 / 24.0:  # hours
        step = _nice_step(span * 24.0 / max_ticks, [1, 2, 3, 6, 12])
        t = d0.replace(minute=0, second=0, microsecond=0)
        for _ in range(2000):
            if date2num(t) > hi:
                break
            out.append(t)
            t += _dt.timedelta(hours=step)
        fmt = "%H:%M"
    else:  # minutes
        step = _nice_step(span * 1440.0 / max_ticks, [1, 5, 10, 15, 30])
        t = d0.replace(second=0, microsecond=0)
        for _ in range(2000):
            if date2num(t) > hi:
                break
            out.append(t)
            t += _dt.timedelta(minutes=step)
        fmt = "%H:%M"
    return [(date2num(t), t.strftime(fmt)) for t in out
            if lo - 1e-9 <= date2num(t) <= hi + 1e-9]


class DateScale(Scale):
    """A time axis over float **day numbers** (:func:`date2num`, days since
    1970-01-01). Datetime inputs are converted on the way in; ticks fall on
    calendar boundaries (year/month/day/hour) chosen from the visible span."""

    name = "date"
    code = "linear"  # already numeric day-space, so the Rust fast paths apply
    is_identity = False

    def transform(self, v: float) -> float:
        return v

    def inverse(self, t: float) -> float:
        return t

    def ticks(self, lo: float, hi: float, max_ticks: int = 7) -> list[Tick]:
        return _date_ticks(lo, hi, max_ticks)


def get(scale) -> Scale:
    """Resolve ``scale`` (a :class:`Scale`, a name string, or ``None``) to a
    concrete :class:`Scale`. ``None``/``"linear"`` -> :class:`LinearScale`."""
    if scale is None:
        return LinearScale()
    if isinstance(scale, Scale):
        return scale
    if isinstance(scale, str):
        try:
            return _BY_NAME[scale]()
        except KeyError:
            raise ValueError(
                f"unknown scale {scale!r}; expected one of {sorted(_BY_NAME)}"
            )
    raise TypeError(f"expected a Scale, scale name, or None; got {type(scale).__name__}")


# Registry of scale-name -> constructor. Categorical/date scales register here as
# they are added in later phases.
_BY_NAME: dict[str, type[Scale]] = {
    "linear": LinearScale,
    "log": LogScale,
    "symlog": SymlogScale,
    "logit": LogitScale,
    "date": DateScale,
}
