"""Polar axes: marks at ``(theta, r)`` on a circular grid.

    fig, ax = pp.subplots(projection="polar")
    ax.line(theta, r)
    ax.set(theta_zero="N", theta_direction=-1, rmax=2)

Angles are radians, counter-clockwise from east unless set otherwise.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from . import _core, _legend
from . import _data as data
from ._canvas import Canvas, check_linestyle, check_marker
from ._frame import TITLE_GAP, Margins, draw_artists
from .artists import Artist, Band, Line, Scatter, View
from .axes import AxesBase, Color
from .scales import nice_ticks
from .text import Label, as_label
from .ticker import plain

__all__ = ["PolarAxes"]

_ZERO = {"E": 0.0, "N": math.pi / 2, "W": math.pi, "S": -math.pi / 2}


@dataclass
class _PolarMark:
    """A mark stored in polar coordinates, drawn through a cartesian artist."""

    artist: Artist
    theta: Any
    r: Any


@dataclass
class _Plan:
    margins: Margins
    rlim: tuple[float, float]


class PolarAxes(AxesBase):
    """Axes in polar coordinates."""

    def __init__(self, theme: Any, figure: Any = None) -> None:
        super().__init__(theme, figure)
        self._marks: list[_PolarMark] = []
        self._rmin = 0.0
        self._rmax: float | None = None
        self._rticks: list[float] | None = None
        self._thetagrids = [i * 45.0 for i in range(8)]
        self._zero = 0.0
        self._direction = 1
        self._rlabel = 22.5

    def _mark(self, artist: Artist, theta: Any, r: Any, label: Any, zorder: float) -> Any:
        theta, r = data.f64(theta), data.f64(r)
        data.same_length(type(artist).__name__.lower(), theta=theta, r=r)
        self._marks.append(_PolarMark(artist, theta, r))
        return self._add(artist, label, zorder)

    def line(
        self,
        theta: Any,
        r: Any,
        *,
        color: Color = None,
        linewidth: float | None = None,
        linestyle: str = "solid",
        marker: str | None = None,
        markersize: float | None = None,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Line:
        """A line through ``(theta, r)`` points."""
        art = Line(
            [],
            [],
            self._color(color, alpha),
            self.theme.line_width if linewidth is None else float(linewidth),
            check_linestyle(linestyle),
            check_marker(marker),
            self.theme.marker_size if markersize is None else float(markersize),
            False,
        )
        return self._mark(art, theta, r, label, zorder)

    def scatter(
        self,
        theta: Any,
        r: Any,
        *,
        color: Color = None,
        size: float | None = None,
        marker: str = "o",
        edgecolor: Color = None,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Scatter:
        """Markers at ``(theta, r)`` points."""
        art = Scatter(
            [],
            [],
            self._color(color, alpha),
            self.theme.marker_size if size is None else float(size),
            check_marker(marker) or "o",
            None if edgecolor is None else self.theme.color(edgecolor),
        )
        return self._mark(art, theta, r, label, zorder)

    def fill(
        self,
        theta: Any,
        r: Any,
        *,
        color: Color = None,
        alpha: float = 0.3,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Band:
        """Fill the region enclosed by ``(theta, r)`` (closed back to the start)."""
        art = Band([], [], [], self._color(color, alpha))
        return self._mark(art, theta, r, label, zorder)

    def set(
        self,
        *,
        title: Label | None = None,
        rmin: float | None = None,
        rmax: float | None = None,
        rticks: Sequence[float] | None = None,
        thetagrids: Sequence[float] | None = None,
        theta_zero: str | float | None = None,
        theta_direction: int | None = None,
        rlabel_angle: float | None = None,
    ) -> PolarAxes:
        """``rmin``/``rmax`` bound the radius; ``rticks`` and ``thetagrids``
        (degrees) place grid lines; ``theta_zero`` is ``"E"``, ``"N"``, ``"W"``,
        ``"S"`` or radians; ``theta_direction`` is 1 (counter-clockwise) or -1;
        ``rlabel_angle`` is where radial labels sit, in degrees."""
        if title is not None:
            self.title = as_label(title)
        if rmin is not None:
            self._rmin = float(rmin)
        if rmax is not None:
            self._rmax = float(rmax)
        if rticks is not None:
            self._rticks = [float(v) for v in rticks]
        if thetagrids is not None:
            self._thetagrids = [float(v) for v in thetagrids]
        if theta_zero is not None:
            self._zero = (
                _ZERO[theta_zero.upper()] if isinstance(theta_zero, str) else float(theta_zero)
            )
        if theta_direction is not None:
            if theta_direction not in (1, -1):
                raise ValueError("theta_direction must be 1 or -1")
            self._direction = theta_direction
        if rlabel_angle is not None:
            self._rlabel = float(rlabel_angle)
        return self

    def get_rlim(self) -> tuple[float, float]:
        rmax = self._rmax
        if rmax is None:
            hi = max((r[1] for m in self._marks if (r := _core.finite_range(m.r))), default=1.0)
            rmax = hi
        return (self._rmin, rmax if rmax > self._rmin else self._rmin + 1.0)

    # -- rendering --------------------------------------------------------------

    def _measure(self, canvas: Canvas) -> _Plan:
        m = Margins()
        if self.title:
            m.top = (
                canvas.measure(self.title, self.theme.title_size, self.theme.title_weight).height
                + TITLE_GAP
            )
        return _Plan(m, self.get_rlim())

    def _angle(self, theta: float) -> float:
        return self._zero + self._direction * theta

    def _draw(self, canvas: Canvas, plan: _Plan, rect: tuple[float, float, float, float]) -> None:
        th = canvas.theme
        x, y, w, h = rect
        cx, cy = x + w / 2, y + h / 2
        size = th.tick_label_size
        gap = size * 0.5
        labels = [(self._angle(math.radians(d)), f"{d:g}°") for d in self._thetagrids]
        radius = min(w, h) / 2
        for a, lab in labels:  # shrink until the angle labels fit
            e = canvas.measure(lab, size)
            ca, sa = abs(math.cos(a)), abs(math.sin(a))
            off = gap + e.width / 2 * ca + e.height / 2 * sa
            if ca > 1e-9:
                radius = min(radius, (w / 2 - e.width / 2 - off * ca) / ca)
            if sa > 1e-9:
                radius = min(radius, (h / 2 - e.height / 2 - off * sa) / sa)
        radius = max(radius, 1.0)
        rmin, rmax = plan.rlim
        k = radius / ((rmax - rmin) or 1.0)
        # Data are drawn in a unit frame: x = (r - rmin) cos(a), y = (r - rmin) sin(a).
        tf = _core.Transform(k, cx, -k, cy)
        view = View(tf, cx - radius, cy - radius, 2 * radius, 2 * radius, (-1, 1), (-1, 1))

        circle = [2 * math.pi * i / 128 for i in range(129)]
        rgrid = (
            [(v, plain(v, th.unicode_minus)) for v in self._rticks]
            if self._rticks is not None
            else nice_ticks(rmin, rmax, 5, th.unicode_minus)
        )
        rgrid = [(v, s) for v, s in rgrid if rmin < v <= rmax + 1e-9]
        for d in self._thetagrids:
            a = self._angle(math.radians(d))
            canvas.segments(
                [cx],
                [cy],
                [cx + radius * math.cos(a)],
                [cy - radius * math.sin(a)],
                color=th.grid_color,
                width=th.grid_width,
            )
        for v, _ in rgrid:
            rr = (v - rmin) * k
            canvas.path(
                [cx + rr * math.cos(t) for t in circle],
                [cy - rr * math.sin(t) for t in circle],
                stroke=th.grid_color,
                width=th.grid_width,
            )
        canvas.path(
            [cx + radius * math.cos(t) for t in circle],
            [cy - radius * math.sin(t) for t in circle],
            stroke=th.spine_color,
            width=th.spine_width,
        )

        for m in self._marks:
            xs, ys = [], []
            for t, r in zip(m.theta, m.r, strict=True):
                a, rr = self._angle(t), r - rmin
                xs.append(rr * math.cos(a))
                ys.append(rr * math.sin(a))
            art = m.artist
            if isinstance(art, Band):  # filled as a closed polygon below
                art.seq, art.lo = data.f64(xs), data.f64(ys)
            else:
                art.xs, art.ys = data.f64(xs), data.f64(ys)  # type: ignore[attr-defined]
        with canvas.group(clip_circle=(cx, cy, radius + th.spine_width)):
            for art in sorted(self._artists, key=lambda a: a.zorder):
                if isinstance(art, Band):
                    canvas.path(art.seq, art.lo, tf, fill=art.color, close=True)
                else:
                    draw_artists(canvas, [art], view)

        for a, lab in labels:
            e = canvas.measure(lab, size)
            out = radius + gap + e.width / 2 * abs(math.cos(a)) + e.height / 2 * abs(math.sin(a))
            canvas.text(
                cx + out * math.cos(a), cy - out * math.sin(a), lab, size, ha="center", va="center"
            )
        ra = self._angle(math.radians(self._rlabel))
        for v, lab in rgrid:
            rr = (v - rmin) * k
            canvas.text(cx + rr * math.cos(ra) + 2, cy - rr * math.sin(ra), lab, size)
        if self.title:
            e = canvas.measure(self.title, th.title_size, th.title_weight)
            canvas.text(
                x + w / 2,
                y - TITLE_GAP - e.depth,
                self.title,
                th.title_size,
                weight=th.title_weight,
                ha="center",
            )
        if self._legend is not None:
            items = _legend.entries(self._artists)
            if items:
                box = _legend.measure(canvas, items, self._legend)
                loc = "upper right" if self._legend.loc == "best" else self._legend.loc
                full = View(tf, x, y, w, h, (0, 1), (0, 1))
                _legend.draw(canvas, box, *_legend.place(box, loc, full, []))
